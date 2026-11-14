"""支援的模型清單（伺服器端與客戶端共用）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    task: str  # text2video | image2video
    repo_id: str
    description: str
    motion_adapter: str | None = None
    variant: str | None = None
    default_frames: int = 16
    default_fps: int = 8
    default_steps: int = 25
    default_guidance: float = 7.5


MODELS: dict[str, ModelSpec] = {
    "animatediff-v1.5": ModelSpec(
        key="animatediff-v1.5",
        task="text2video",
        repo_id="SG161222/Realistic_Vision_V5.1_noVAE",
        motion_adapter="guoyww/animatediff-motion-adapter-v1-5-2",
        description="AnimateDiff + Realistic Vision v5.1（文字轉影片，T4 可跑）",
        default_frames=16,
        default_fps=8,
        default_steps=25,
        default_guidance=7.5,
    ),
    "svd-xt": ModelSpec(
        key="svd-xt",
        task="image2video",
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt",
        variant="fp16",
        description="Stable Video Diffusion XT（圖片轉影片，1024x576）",
        default_frames=25,
        default_fps=7,
    ),
}

DEFAULT_TEXT2VIDEO_MODEL = "animatediff-v1.5"
DEFAULT_IMAGE2VIDEO_MODEL = "svd-xt"


def list_models(task: str | None = None) -> list[ModelSpec]:
    specs = list(MODELS.values())
    if task:
        specs = [spec for spec in specs if spec.task == task]
    return specs


def get_model(key: str) -> ModelSpec:
    try:
        return MODELS[key]
    except KeyError as exc:
        available = ", ".join(sorted(MODELS))
        raise ValueError(f"未知模型 `{key}`，可用模型：{available}") from exc


def default_model_for(task: str) -> str:
    return DEFAULT_TEXT2VIDEO_MODEL if task == "text2video" else DEFAULT_IMAGE2VIDEO_MODEL
