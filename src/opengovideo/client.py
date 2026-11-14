"""本機端 Colab 橋接客戶端。

只依賴 `requests` 與 `python-dotenv`，不匯入 torch / diffusers。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import requests
from dotenv import set_key

from . import __version__
from .config import ENV_FILE, Settings
from .utils import b64encode_bytes, build_filename, get_logger

logger = get_logger("client")

ProgressCallback = Callable[[dict[str, Any]], None]
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class ColabError(RuntimeError):
    """Colab 橋接的一般錯誤。"""


class ColabOfflineError(ColabError):
    """無法連上 Colab（通常代表 Tunnel 已失效）。"""


class JobFailedError(ColabError):
    """伺服器端生成工作失敗。"""


class ColabVideoClient:
    """遙控 Colab GPU 伺服器的客戶端。"""

    def __init__(
        self,
        url: str | None = None,
        output_dir: Path | str | None = None,
        request_timeout: float | None = None,
        job_timeout: float | None = None,
        session: requests.Session | None = None,
    ) -> None:
        settings = Settings.load()
        self._url = (url or settings.colab_url).rstrip("/")
        self.output_dir = Path(output_dir) if output_dir else settings.output_dir
        self.request_timeout = request_timeout or settings.request_timeout
        self.job_timeout = job_timeout or settings.job_timeout
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": f"openGO_video/{__version__}"})

    # ------------------------------------------------------------------ 連線設定
    @property
    def url(self) -> str:
        return self._url

    def set_url(self, url: str, persist: bool = True) -> str:
        """設定 Colab 網址，預設一併寫回 `.env`。"""
        normalized = url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("網址需以 http:// 或 https:// 開頭")
        self._url = normalized
        if persist:
            ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            ENV_FILE.touch(exist_ok=True)
            set_key(str(ENV_FILE), "COLAB_URL", normalized)
            logger.info("已將 COLAB_URL 寫入 %s", ENV_FILE)
        return normalized

    def _require_url(self) -> str:
        if not self._url:
            raise ColabOfflineError(
                "尚未設定 Colab 網址。請先執行 `python connect.py`，"
                "或在 .env 設定 COLAB_URL。"
            )
        return self._url

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        base = self._require_url()
        kwargs.setdefault("timeout", self.request_timeout)
        try:
            response = self._session.request(method, f"{base}{path}", **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise ColabOfflineError(
                "連不上 Colab 伺服器，Tunnel 可能已失效。請重新執行 Colab 筆記本後更新網址。"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ColabError(f"請求逾時：{path}") from exc
        if response.status_code >= 400:
            detail = _error_detail(response)
            raise ColabError(f"伺服器回應 {response.status_code}：{detail}")
        return response

    # ------------------------------------------------------------------ 查詢
    def health(self) -> dict[str, Any]:
        """取得伺服器健康狀態（GPU、已載入模型、工作統計）。"""
        return self._request("GET", "/health").json()

    def models(self) -> list[dict[str, Any]]:
        return self._request("GET", "/models").json().get("models", [])

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/jobs/{job_id}").json()

    # ------------------------------------------------------------------ 提交工作
    def submit_text2video(
        self,
        prompt: str,
        model: str | None = None,
        negative_prompt: str = "bad quality, blurry, distorted, lowres, watermark",
        num_frames: int | None = None,
        num_inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int = 42,
        fps: int | None = None,
    ) -> str:
        """提交文字轉影片工作，回傳 job_id。"""
        payload: dict[str, Any] = {"prompt": prompt, "negative_prompt": negative_prompt, "seed": seed}
        if model:
            payload["model"] = model
        if num_frames is not None:
            payload["num_frames"] = num_frames
        if num_inference_steps is not None:
            payload["num_inference_steps"] = num_inference_steps
        if guidance_scale is not None:
            payload["guidance_scale"] = guidance_scale
        if fps is not None:
            payload["fps"] = fps

        data = self._request("POST", "/jobs/text2video", json=payload).json()
        job_id = data["job_id"]
        logger.info("已建立文字轉影片工作：%s", job_id)
        return job_id

    def submit_image2video(
        self,
        image: str | Path | bytes,
        model: str | None = None,
        num_frames: int | None = None,
        fps: int | None = None,
        motion_bucket_id: int | None = None,
        seed: int = 42,
    ) -> str:
        """提交圖片轉影片工作。image 可為本機路徑、http(s) URL 或 bytes。"""
        payload: dict[str, Any] = {"seed": seed}
        if isinstance(image, (str, Path)) and str(image).startswith(("http://", "https://")):
            payload["image_url"] = str(image)
        else:
            raw = image if isinstance(image, bytes) else Path(image).read_bytes()
            payload["image_base64"] = b64encode_bytes(raw)
        if model:
            payload["model"] = model
        if num_frames is not None:
            payload["num_frames"] = num_frames
        if fps is not None:
            payload["fps"] = fps
        if motion_bucket_id is not None:
            payload["motion_bucket_id"] = motion_bucket_id

        data = self._request("POST", "/jobs/image2video", json=payload).json()
        job_id = data["job_id"]
        logger.info("已建立圖片轉影片工作：%s", job_id)
        return job_id

    # ------------------------------------------------------------------ 等待 / 下載
    def wait(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """輪詢工作直到完成，回傳最終狀態。"""
        deadline = time.monotonic() + (timeout or self.job_timeout)
        last_status = ""
        while True:
            job = self.get_job(job_id)
            if on_progress:
                on_progress(job)
            status = job.get("status", "")
            if status == "succeeded":
                return job
            if status in TERMINAL_STATUSES:
                raise JobFailedError(job.get("error") or f"工作狀態為 {status}")
            if status != last_status:
                logger.debug("工作 %s 狀態：%s", job_id, status)
                last_status = status
            if time.monotonic() > deadline:
                raise ColabError(f"等待工作逾時（{timeout or self.job_timeout:.0f} 秒）")
            time.sleep(poll_interval)

    def download(
        self,
        job_id: str,
        output_dir: Path | str | None = None,
        filename: str | None = None,
    ) -> Path:
        """下載已完成工作的 MP4。"""
        response = self._request("GET", f"/jobs/{job_id}/video", stream=True)
        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        name = filename or _filename_from_headers(response) or f"opengovideo_{job_id}.mp4"
        target = target_dir / name
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                if chunk:
                    handle.write(chunk)
        logger.info("影片已下載：%s", target)
        return target

    # ------------------------------------------------------------------ 一次到位
    def generate_text2video(self, prompt: str, output_dir: Path | str | None = None, **kwargs: Any) -> Path:
        """提交、等待並下載文字轉影片，回傳本機檔案路徑。"""
        on_progress = kwargs.pop("on_progress", None)
        filename = kwargs.pop("filename", None)
        job_id = self.submit_text2video(prompt=prompt, **kwargs)
        self.wait(job_id, on_progress=on_progress)
        return self.download(
            job_id,
            output_dir=output_dir,
            filename=filename or build_filename("t2v", prompt),
        )

    def generate_image2video(
        self,
        image: str | Path | bytes,
        output_dir: Path | str | None = None,
        **kwargs: Any,
    ) -> Path:
        """提交、等待並下載圖片轉影片，回傳本機檔案路徑。"""
        on_progress = kwargs.pop("on_progress", None)
        filename = kwargs.pop("filename", None)
        job_id = self.submit_image2video(image=image, **kwargs)
        self.wait(job_id, on_progress=on_progress)
        hint = Path(image).stem if isinstance(image, (str, Path)) and not str(image).startswith("http") else ""
        return self.download(
            job_id,
            output_dir=output_dir,
            filename=filename or build_filename("i2v", hint),
        )


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    return str(payload.get("detail") or payload.get("error") or payload)[:300]


def _filename_from_headers(response: requests.Response) -> str | None:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    return match.group(1) if match else None


def job_progress_line(job: Mapping[str, Any]) -> str:
    """把工作狀態格式化成 CLI 單行進度。"""
    status = job.get("status", "?")
    progress = float(job.get("progress") or 0.0)
    message = job.get("message") or ""
    return f"[{status}] {progress * 100:5.1f}% {message}".rstrip()
