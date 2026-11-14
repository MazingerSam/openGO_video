"""openGO_video 共用設定。

設定優先順序：`.env` > 環境變數 > 預設值。
每次呼叫 `Settings.load()` 都會重新讀取 `.env`，因此 connect 後可立即生效。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = Path(os.getenv("OPENGOV_ENV_FILE", BASE_DIR / ".env"))

GITHUB_REPO = "MazingerSam/openGO_video"
NOTEBOOK_PATH = "notebooks/colab_opengovideo.ipynb"
NOTEBOOK_URL = f"https://colab.research.google.com/github/{GITHUB_REPO}/blob/main/{NOTEBOOK_PATH}"

DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_JOB_TIMEOUT = 900.0


def _env_value(key: str) -> str | None:
    """先讀 .env，再讀環境變數；空字串視為未設定。"""
    value = dotenv_values(ENV_FILE).get(key)
    if value is None or value == "":
        value = os.getenv(key)
    return value or None


def _env_float(key: str, default: float) -> float:
    raw = _env_value(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    colab_url: str
    output_dir: Path
    request_timeout: float
    job_timeout: float
    env_file: Path

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            colab_url=(_env_value("COLAB_URL") or "").rstrip("/"),
            output_dir=Path(_env_value("OUTPUT_DIR") or DEFAULT_OUTPUT_DIR),
            request_timeout=_env_float("REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT),
            job_timeout=_env_float("JOB_TIMEOUT", DEFAULT_JOB_TIMEOUT),
            env_file=ENV_FILE,
        )
