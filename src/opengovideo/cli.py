"""`opengovideo` 命令列介面。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .client import ColabError, ColabVideoClient, job_progress_line
from .config import NOTEBOOK_URL
from .models import list_models
from .utils import configure_windows_console, human_duration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opengovideo",
        description="openGO_video：遙控 Google Colab GPU 生成影片",
    )
    parser.add_argument("--version", action="version", version=f"openGO_video {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    connect = sub.add_parser("connect", help="設定 Colab 橋接網址並驗證連線")
    connect.add_argument("url", nargs="?", help="Cloudflare Tunnel 網址（https://xxx.trycloudflare.com）")
    connect.set_defaults(func=_cmd_connect)

    status = sub.add_parser("status", help="檢查 Colab 連線、GPU 與已載入模型")
    status.set_defaults(func=_cmd_status)

    models = sub.add_parser("models", help="列出可用模型")
    models.set_defaults(func=_cmd_models)

    t2v = sub.add_parser("t2v", help="文字轉影片（AnimateDiff）")
    t2v.add_argument("--prompt", required=True, help="提示詞")
    t2v.add_argument("--model", help="模型 key（預設 animatediff-v1.5）")
    t2v.add_argument("--negative", default="bad quality, blurry, distorted, lowres, watermark", help="負面提示詞")
    t2v.add_argument("--frames", type=int, help="影格數（預設 16）")
    t2v.add_argument("--steps", type=int, help="推論步數（預設 25）")
    t2v.add_argument("--guidance", type=float, help="CFG 強度（預設 7.5）")
    t2v.add_argument("--fps", type=int, help="輸出 FPS（預設 8）")
    t2v.add_argument("--seed", type=int, default=42, help="隨機種子（預設 42）")
    t2v.add_argument("--output", type=Path, help="輸出資料夾（預設 ./outputs）")
    t2v.set_defaults(func=_cmd_t2v)

    i2v = sub.add_parser("i2v", help="圖片轉影片（SVD-XT）")
    i2v.add_argument("--image", required=True, help="圖片路徑或 http(s) URL")
    i2v.add_argument("--model", help="模型 key（預設 svd-xt）")
    i2v.add_argument("--frames", type=int, help="影格數（預設 25）")
    i2v.add_argument("--fps", type=int, help="輸出 FPS（預設 7）")
    i2v.add_argument("--motion", type=int, help="motion_bucket_id（預設 127，建議 100~150）")
    i2v.add_argument("--seed", type=int, default=42, help="隨機種子（預設 42）")
    i2v.add_argument("--output", type=Path, help="輸出資料夾（預設 ./outputs）")
    i2v.set_defaults(func=_cmd_i2v)

    job = sub.add_parser("job", help="查詢／下載既有工作")
    job.add_argument("job_id", help="工作 ID")
    job.add_argument("--download", action="store_true", help="完成後下載影片")
    job.add_argument("--output", type=Path, help="下載資料夾（預設 ./outputs）")
    job.set_defaults(func=_cmd_job)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_windows_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ColabError as exc:
        print(f"\n[!] {exc}", file=sys.stderr)
        if "連不上" in str(exc):
            print(f"    重新啟動 Colab：{NOTEBOOK_URL}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError) as exc:
        print(f"\n[!] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n[!] 已取消", file=sys.stderr)
        return 130


# --------------------------------------------------------------------------- 指令
def _cmd_connect(args: argparse.Namespace) -> int:
    client = ColabVideoClient()
    if not args.url:
        if not client.url:
            print("尚未設定 Colab 網址。用法：opengovideo connect https://xxx.trycloudflare.com")
            return 0
        print(f"目前網址：{client.url}")
        print(f"Colab 筆記本：{NOTEBOOK_URL}")
        return 0
    client.set_url(args.url)
    info = client.health()
    _print_health(info)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    client = ColabVideoClient()
    info = client.health()
    _print_health(info)
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    client = ColabVideoClient()
    try:
        remote = {item["key"]: item for item in client.models()}
        note = ""
    except ColabError:
        remote = {}
        note = "（未連線 Colab，顯示本機清單）"
    print(f"可用模型{note}")
    for spec in list_models():
        mark = "●" if spec.key in remote else "○"
        print(f"  {mark} {spec.key:<18} [{spec.task}] {spec.description}")
    if remote:
        print("\n● = Colab 端可即時使用，○ = 需要時自動載入")
    return 0


def _cmd_t2v(args: argparse.Namespace) -> int:
    client = ColabVideoClient(output_dir=args.output)
    started = _now()
    path = client.generate_text2video(
        prompt=args.prompt,
        model=args.model,
        negative_prompt=args.negative,
        num_frames=args.frames,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        fps=args.fps,
        seed=args.seed,
        on_progress=_progress_printer(),
    )
    print(f"\n[OK] 影片已下載（{human_duration(_now() - started)}）：{path}")
    return 0


def _cmd_i2v(args: argparse.Namespace) -> int:
    client = ColabVideoClient(output_dir=args.output)
    started = _now()
    path = client.generate_image2video(
        image=args.image,
        model=args.model,
        num_frames=args.frames,
        fps=args.fps,
        motion_bucket_id=args.motion,
        seed=args.seed,
        on_progress=_progress_printer(),
    )
    print(f"\n[OK] 影片已下載（{human_duration(_now() - started)}）：{path}")
    return 0


def _cmd_job(args: argparse.Namespace) -> int:
    client = ColabVideoClient(output_dir=args.output)
    job = client.get_job(args.job_id)
    print(job_progress_line(job))
    if args.download and job.get("status") == "succeeded":
        path = client.download(args.job_id)
        print(f"[OK] 已下載：{path}")
    return 0


# --------------------------------------------------------------------------- 輔助
def _print_health(info: dict[str, Any]) -> None:
    gpu = info.get("gpu") or "CPU（無 CUDA）"
    vram = info.get("vram_total_gb")
    gpu_line = f"{gpu}（{vram} GB）" if vram else str(gpu)
    print(f"服務   : {info.get('service', 'openGO_video')} {info.get('version', '')}")
    print(f"狀態   : {info.get('status', 'ok')}")
    print(f"GPU    : {gpu_line}")
    print(f"已載入 : {', '.join(info.get('models_loaded') or []) or '（尚未載入）'}")
    jobs = info.get("jobs") or {}
    print(f"工作   : 完成 {jobs.get('succeeded', 0)}／失敗 {jobs.get('failed', 0)}／進行中 {jobs.get('queued', 0) + jobs.get('running', 0)}")
    if info.get("uptime_seconds") is not None:
        print(f"運作   : {human_duration(info['uptime_seconds'])}")


def _progress_printer():
    state = {"last": -1.0}

    def callback(job: dict[str, Any]) -> None:
        progress = float(job.get("progress") or 0.0)
        if progress - state["last"] >= 0.05 or job.get("status") in {"succeeded", "failed"}:
            state["last"] = progress
            print(f"\r{job_progress_line(job)}", end="" if job.get("status") != "succeeded" else "\n", flush=True)

    return callback


def _now() -> float:
    import time

    return time.monotonic()


if __name__ == "__main__":
    raise SystemExit(main())
