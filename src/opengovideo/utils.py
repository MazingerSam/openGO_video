"""openGO_video 共用工具函式。"""

from __future__ import annotations

import base64
import logging
import re
import sys
import time
from pathlib import Path

LOGGER_NAME = "opengovideo"
_MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".gif"}


def setup_logging(level: str = "INFO") -> logging.Logger:
    """設定主 logger（重複呼叫不會疊加 handler）。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(suffix: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)


def configure_windows_console() -> None:
    """讓 Windows 終端正確顯示中文與 emoji。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def is_colab() -> bool:
    """判斷目前是否執行於 Google Colab。"""
    try:
        import google.colab  # noqa: F401

        return True
    except ImportError:
        return False


def human_duration(seconds: float) -> str:
    """把秒數轉成 `1m 05s` 這種易讀格式。"""
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def slugify(text: str, max_length: int = 40) -> str:
    """把提示詞轉成安全的檔名片段。"""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return (cleaned[:max_length].rstrip("-") or "video").lower()


def build_filename(prefix: str, hint: str = "", suffix: str = ".mp4") -> str:
    """產生帶時間戳與提示詞片段的檔名。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = slugify(hint) if hint else ""
    middle = f"_{slug}" if slug else ""
    return f"{prefix}{middle}_{stamp}{suffix}"


def b64encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode_bytes(data: str) -> bytes:
    """解 base64，容忍 data URI 前綴與換行。"""
    if data.startswith("data:"):
        data = data.split(",", 1)[-1]
    return base64.b64decode(data, validate=False)


def ensure_output_dir(path: Path | None = None) -> Path:
    target = Path(path) if path else Path("outputs")
    target.mkdir(parents=True, exist_ok=True)
    return target


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in _MEDIA_SUFFIXES
