"""Colab 端 FastAPI 橋接伺服器。

端點：
    GET  /health                     健康檢查（GPU、已載入模型、工作統計）
    GET  /models                     可用模型清單
    POST /jobs/text2video            建立文字轉影片工作（非同步）
    POST /jobs/image2video           建立圖片轉影片工作（非同步）
    GET  /jobs/{job_id}              查詢工作狀態與進度
    GET  /jobs/{job_id}/video         下載完成的 MP4
    POST /generate/text2video        同步生成（回傳 base64，相容舊版）
    POST /generate/image2video       同步生成（回傳 base64，相容舊版）
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__
from .models import (
    DEFAULT_IMAGE2VIDEO_MODEL,
    DEFAULT_TEXT2VIDEO_MODEL,
    get_model,
    list_models,
)
from .pipeline import PipelineManager
from .utils import b64decode_bytes, b64encode_bytes, get_logger

logger = get_logger("server")

Runner = Callable[[Callable[[float, str], None]], Path]
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


# --------------------------------------------------------------------------- 請求模型
class Text2VideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: str | None = None
    negative_prompt: str = "bad quality, blurry, distorted, lowres, watermark"
    num_frames: int | None = Field(default=None, ge=2, le=64)
    num_inference_steps: int | None = Field(default=None, ge=1, le=100)
    guidance_scale: float | None = Field(default=None, ge=1.0, le=20.0)
    fps: int | None = Field(default=None, ge=1, le=30)
    seed: int = 42


class Image2VideoRequest(BaseModel):
    image_base64: str | None = None
    image_url: str | None = None
    model: str | None = None
    num_frames: int | None = Field(default=None, ge=2, le=64)
    fps: int | None = Field(default=None, ge=1, le=30)
    motion_bucket_id: int = Field(default=127, ge=1, le=255)
    decode_chunk_size: int = Field(default=8, ge=1, le=16)
    seed: int = 42


# --------------------------------------------------------------------------- 工作佇列
@dataclass
class Job:
    id: str
    kind: str
    model: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "model": self.model,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "error": self.error,
            "params": self.params,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.result_path and self.result_path.exists():
            payload["result"] = {
                "filename": self.result_path.name,
                "size_bytes": self.result_path.stat().st_size,
                "download_url": f"/jobs/{self.id}/video",
            }
        return payload


class JobStore:
    """單一 GPU 工作佇列（同一時間只跑一件，避免 VRAM 爆掉）。"""

    def __init__(self, pipeline: PipelineManager | None = None, max_jobs: int = 50) -> None:
        self.pipeline = pipeline or PipelineManager()
        self.max_jobs = max_jobs
        self.started_at = time.time()
        self._jobs: dict[str, Job] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="opengov")

    def submit(self, kind: str, model: str, params: dict[str, Any], runner: Runner) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, model=model, params=params)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self.max_jobs:
                stale = self._order.popleft()
                stale_job = self._jobs.get(stale)
                if stale_job and stale_job.status in TERMINAL_STATUSES:
                    self._jobs.pop(stale, None)
        self._executor.submit(self._run, job.id, runner)
        logger.info("接受工作 %s（%s / %s）", job.id, kind, model)
        return job

    def _run(self, job_id: str, runner: Runner) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            job.message = "啟動中"

        def progress(ratio: float, message: str) -> None:
            with self._lock:
                current = self._jobs.get(job_id)
                if current:
                    current.progress = max(0.0, min(1.0, ratio))
                    current.message = message

        try:
            result_path = runner(progress)
            with self._lock:
                job.result_path = Path(result_path)
                job.progress = 1.0
                job.status = "succeeded"
                job.message = "完成"
        except Exception as exc:  # noqa: BLE001 - 需把錯誤回報給客戶端
            logger.exception("工作 %s 失敗", job_id)
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.message = "失敗"
        finally:
            with self._lock:
                job.finished_at = time.time()

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.to_dict()

    def counts(self) -> dict[str, int]:
        with self._lock:
            counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            return counts

    def result_path(self, job_id: str) -> Path | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.result_path

    def wait(self, job_id: str, timeout: float = 1800.0, interval: float = 2.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            data = self.snapshot(job_id)
            if data["status"] in TERMINAL_STATUSES:
                return data
            if time.monotonic() > deadline:
                raise TimeoutError(f"工作 {job_id} 逾時")
            time.sleep(interval)


# --------------------------------------------------------------------------- FastAPI
def create_app(store: JobStore | None = None) -> FastAPI:
    store = store or JobStore()
    app = FastAPI(title="openGO_video Colab GPU Bridge", version=__version__)
    app.state.store = store

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "openGO_video",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "openGO_video",
            "version": __version__,
            **store.pipeline.device_info(),
            "models_loaded": store.pipeline.loaded_models(),
            "jobs": store.counts(),
            "uptime_seconds": round(time.time() - store.started_at, 1),
        }

    @app.get("/models")
    def models() -> dict[str, Any]:
        return {
            "models": [
                {
                    "key": spec.key,
                    "task": spec.task,
                    "repo_id": spec.repo_id,
                    "description": spec.description,
                    "default_frames": spec.default_frames,
                    "default_fps": spec.default_fps,
                }
                for spec in list_models()
            ],
            "defaults": {
                "text2video": DEFAULT_TEXT2VIDEO_MODEL,
                "image2video": DEFAULT_IMAGE2VIDEO_MODEL,
            },
        }

    @app.post("/jobs/text2video", status_code=202)
    def submit_text2video(req: Text2VideoRequest) -> dict[str, Any]:
        try:
            spec = get_model(req.model or DEFAULT_TEXT2VIDEO_MODEL)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if spec.task != "text2video":
            raise HTTPException(status_code=400, detail=f"{spec.key} 不是文字轉影片模型")

        params = req.model_dump(exclude_none=True)
        params["model"] = spec.key
        params.pop("prompt", None)

        def runner(progress: Callable[[float, str], None]) -> Path:
            return store.pipeline.generate_text2video(
                prompt=req.prompt,
                model=spec.key,
                negative_prompt=req.negative_prompt,
                num_frames=req.num_frames,
                num_inference_steps=req.num_inference_steps,
                guidance_scale=req.guidance_scale,
                fps=req.fps,
                seed=req.seed,
                progress=progress,
            )

        job = store.submit("text2video", spec.key, {"prompt": req.prompt, **params}, runner)
        return {"job_id": job.id, "status": job.status, "status_url": f"/jobs/{job.id}"}

    @app.post("/jobs/image2video", status_code=202)
    def submit_image2video(req: Image2VideoRequest) -> dict[str, Any]:
        try:
            spec = get_model(req.model or DEFAULT_IMAGE2VIDEO_MODEL)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if spec.task != "image2video":
            raise HTTPException(status_code=400, detail=f"{spec.key} 不是圖片轉影片模型")

        image_bytes = _read_image(req)
        params = {
            "model": spec.key,
            "num_frames": req.num_frames,
            "fps": req.fps,
            "motion_bucket_id": req.motion_bucket_id,
            "decode_chunk_size": req.decode_chunk_size,
            "seed": req.seed,
        }

        def runner(progress: Callable[[float, str], None]) -> Path:
            return store.pipeline.generate_image2video(
                image_bytes=image_bytes,
                model=spec.key,
                num_frames=req.num_frames,
                fps=req.fps,
                motion_bucket_id=req.motion_bucket_id,
                decode_chunk_size=req.decode_chunk_size,
                seed=req.seed,
                progress=progress,
            )

        job = store.submit("image2video", spec.key, params, runner)
        return {"job_id": job.id, "status": job.status, "status_url": f"/jobs/{job.id}"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return store.snapshot(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="找不到此工作") from exc

    @app.get("/jobs/{job_id}/video")
    def get_job_video(job_id: str) -> FileResponse:
        try:
            job = store.snapshot(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="找不到此工作") from exc
        if job["status"] != "succeeded":
            raise HTTPException(status_code=409, detail=f"工作尚未完成（{job['status']}）")
        path = store.result_path(job_id)
        if not path or not path.exists():
            raise HTTPException(status_code=410, detail="影片檔已不存在，請重新生成")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    # ---------------------------------------------------------- 相容舊版同步端點
    @app.post("/generate/text2video")
    def generate_text2video_sync(req: Text2VideoRequest) -> dict[str, Any]:
        submitted = submit_text2video(req)
        return _sync_result(store, submitted["job_id"])

    @app.post("/generate/image2video")
    def generate_image2video_sync(req: Image2VideoRequest) -> dict[str, Any]:
        submitted = submit_image2video(req)
        return _sync_result(store, submitted["job_id"])

    return app


def _read_image(req: Image2VideoRequest) -> bytes:
    if bool(req.image_base64) == bool(req.image_url):
        raise HTTPException(status_code=400, detail="請提供 image_base64 或 image_url（二選一）")
    if req.image_url:
        try:
            response = requests.get(req.image_url, timeout=30)
            response.raise_for_status()
            data = response.content
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"無法下載圖片：{exc}") from exc
    else:
        try:
            data = b64decode_bytes(req.image_base64 or "")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="image_base64 解碼失敗") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="圖片超過 20MB 上限")
    return data


def _sync_result(store: JobStore, job_id: str) -> dict[str, Any]:
    try:
        job = store.wait(job_id, timeout=1800.0)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    if job["status"] != "succeeded":
        raise HTTPException(status_code=500, detail=job.get("error") or "生成失敗")
    path = store.result_path(job_id)
    if path is None:
        raise HTTPException(status_code=500, detail="找不到輸出檔案")
    return {
        "status": "success",
        "job_id": job_id,
        "video_base64": b64encode_bytes(path.read_bytes()),
        "filename": path.name,
    }


app = create_app()


def launch(
    port: int = 8000,
    host: str = "0.0.0.0",
    tunnel: bool = True,
    warmup_models: list[str] | None = None,
) -> None:
    """啟動 uvicorn，並可選擇開啟 Cloudflare Tunnel。"""
    import nest_asyncio
    import uvicorn

    nest_asyncio.apply()

    if warmup_models:
        from .pipeline import warmup

        warmup(app.state.store.pipeline, warmup_models)

    public_url = None
    if tunnel:
        from pycloudflared import try_cloudflare

        print("🌐 正在建立 Cloudflare Tunnel…")
        handle = try_cloudflare(port=port)
        public_url = getattr(handle, "tunnel", None) or getattr(handle, "url", None)
        print("=" * 68)
        print("✅ Colab GPU 伺服器已就緒")
        if public_url:
            print(f"🔗 公開網址：{public_url}")
            print("   請把這個網址貼到本機執行：python connect.py")
        else:
            print("🔗 Tunnel 已啟動，請查看上方輸出中的 trycloudflare.com 網址")
        print("=" * 68)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    launch(warmup_models=[DEFAULT_TEXT2VIDEO_MODEL, DEFAULT_IMAGE2VIDEO_MODEL])
