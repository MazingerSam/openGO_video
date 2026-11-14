"""Colab 端推論管線（僅在具備 torch / diffusers 的環境使用）。

所有重型匯入（torch、diffusers）都放在函式內部，讓本機端安裝輕量依賴時
仍可 import 套件。
"""

from __future__ import annotations

import gc
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .models import DEFAULT_IMAGE2VIDEO_MODEL, DEFAULT_TEXT2VIDEO_MODEL, ModelSpec, get_model
from .utils import build_filename, get_logger

logger = get_logger("pipeline")

ProgressFn = Callable[[float, str], None]


class PipelineManager:
    """延遲載入並重複使用 GPU 管線。"""

    def __init__(self, output_dir: Path | str = "server_outputs") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._pipelines: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._gpu_lock = threading.Lock()

    # ------------------------------------------------------------------ 狀態
    def loaded_models(self) -> list[str]:
        with self._lock:
            return sorted(self._pipelines)

    def device_info(self) -> dict[str, Any]:
        try:
            import torch
        except ImportError:
            return {"device": "cpu", "cuda": False, "gpu": None, "vram_total_gb": None}
        if not torch.cuda.is_available():
            return {"device": "cpu", "cuda": False, "gpu": None, "vram_total_gb": None}
        total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return {
            "device": "cuda",
            "cuda": True,
            "gpu": torch.cuda.get_device_name(0),
            "vram_total_gb": round(total, 1),
        }

    def unload(self, key: str | None = None) -> list[str]:
        """卸載指定（或全部）管線並釋放 VRAM。"""
        with self._lock:
            keys = [key] if key else list(self._pipelines)
            for name in keys:
                self._pipelines.pop(name, None)
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        if keys:
            logger.info("已卸載管線：%s", ", ".join(keys))
        return keys

    # ------------------------------------------------------------------ 載入
    def load(self, key: str, progress: ProgressFn | None = None) -> Any:
        spec = get_model(key)
        with self._lock:
            if key in self._pipelines:
                return self._pipelines[key]
            _report(progress, 0.02, f"載入模型 {spec.key}…")
            pipe = self._build(spec)
            self._pipelines[key] = pipe
            _report(progress, 0.05, f"模型 {spec.key} 就緒")
            return pipe

    def _build(self, spec: ModelSpec) -> Any:
        import torch

        use_cuda = torch.cuda.is_available()
        dtype = torch.float16 if use_cuda else torch.float32

        if spec.key == "animatediff-v1.5":
            from diffusers import AnimateDiffPipeline, DDIMScheduler, MotionAdapter

            adapter = MotionAdapter.from_pretrained(spec.motion_adapter, torch_dtype=dtype)
            pipe = AnimateDiffPipeline.from_pretrained(
                spec.repo_id, motion_adapter=adapter, torch_dtype=dtype
            )
            pipe.scheduler = DDIMScheduler.from_config(
                pipe.scheduler.config,
                beta_schedule="linear",
                clip_sample=False,
                timestep_spacing="linspace",
                steps_offset=1,
            )
        elif spec.key == "svd-xt":
            from diffusers import StableVideoDiffusionPipeline

            pipe = StableVideoDiffusionPipeline.from_pretrained(
                spec.repo_id,
                torch_dtype=dtype,
                variant=spec.variant if use_cuda else None,
            )
        else:  # pragma: no cover - 由 registry 控制，理論上不會到這裡
            raise ValueError(f"沒有對應的載入邏輯：{spec.key}")

        if use_cuda:
            pipe.enable_model_cpu_offload()
            if hasattr(pipe, "enable_vae_slicing"):
                pipe.enable_vae_slicing()
        else:
            pipe.to("cpu")
        logger.info("已載入 %s（%s）", spec.key, "CUDA" if use_cuda else "CPU")
        return pipe

    # ------------------------------------------------------------------ 生成
    def generate_text2video(
        self,
        prompt: str,
        model: str | None = None,
        negative_prompt: str = "bad quality, blurry, distorted, lowres, watermark",
        num_frames: int | None = None,
        num_inference_steps: int | None = None,
        guidance_scale: float | None = None,
        fps: int | None = None,
        seed: int = 42,
        progress: ProgressFn | None = None,
    ) -> Path:
        spec = get_model(model or DEFAULT_TEXT2VIDEO_MODEL)
        pipe = self.load(spec.key, progress)
        frames = num_frames or spec.default_frames
        steps = num_inference_steps or spec.default_steps
        guidance = guidance_scale if guidance_scale is not None else spec.default_guidance

        with self._gpu_lock:
            import torch
            from diffusers.utils import export_to_video

            device = "cuda" if torch.cuda.is_available() else "cpu"
            generator = torch.Generator(device=device).manual_seed(seed)
            _report(progress, 0.08, "開始推論")
            output = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_frames=frames,
                num_inference_steps=steps,
                guidance_scale=guidance,
                generator=generator,
                callback_on_step_end=_step_callback(progress, steps),
            )
            output_path = self.output_dir / build_filename("t2v", prompt)
            export_to_video(output.frames[0], str(output_path), fps=fps or spec.default_fps)
        _report(progress, 1.0, "完成")
        return output_path

    def generate_image2video(
        self,
        image_bytes: bytes,
        model: str | None = None,
        num_frames: int | None = None,
        fps: int | None = None,
        motion_bucket_id: int = 127,
        decode_chunk_size: int = 8,
        seed: int = 42,
        progress: ProgressFn | None = None,
    ) -> Path:
        spec = get_model(model or DEFAULT_IMAGE2VIDEO_MODEL)
        pipe = self.load(spec.key, progress)
        frames = num_frames or spec.default_frames

        with self._gpu_lock:
            import io

            import torch
            from diffusers.utils import export_to_video
            from PIL import Image

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((1024, 576))
            generator = torch.manual_seed(seed)
            _report(progress, 0.08, "開始推論")
            result = pipe(
                image,
                num_frames=frames,
                decode_chunk_size=decode_chunk_size,
                motion_bucket_id=motion_bucket_id,
                generator=generator,
                callback_on_step_end=_step_callback(progress, 25),
            )
            output_path = self.output_dir / build_filename("i2v")
            export_to_video(result.frames[0], str(output_path), fps=fps or spec.default_fps)
        _report(progress, 1.0, "完成")
        return output_path


def _step_callback(progress: ProgressFn | None, total: int) -> Callable[..., dict[str, Any]] | None:
    if progress is None:
        return None

    def callback(pipe: Any, step: int, timestep: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        ratio = min(0.95, 0.1 + 0.85 * (step + 1) / max(1, total))
        _report(progress, ratio, f"推論 {step + 1}/{total}")
        return kwargs

    return callback


def _report(progress: ProgressFn | None, ratio: float, message: str) -> None:
    if progress:
        try:
            progress(max(0.0, min(1.0, ratio)), message)
        except Exception:  # 進度回報失敗不應中斷生成
            logger.debug("進度回報失敗", exc_info=True)


def warmup(manager: PipelineManager, models: list[str] | None = None) -> None:
    """預先載入模型（可選）。"""
    for key in models or [DEFAULT_TEXT2VIDEO_MODEL, DEFAULT_IMAGE2VIDEO_MODEL]:
        started = time.time()
        manager.load(key)
        logger.info("預載 %s 完成（%.1fs）", key, time.time() - started)
