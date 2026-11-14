"""互動式 Colab 重連工具（Windows 捷徑 restart_colab.bat 會呼叫本檔）。"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from opengovideo.client import ColabError, ColabVideoClient  # noqa: E402
from opengovideo.config import NOTEBOOK_URL  # noqa: E402
from opengovideo.utils import (  # noqa: E402
    configure_windows_console,
    human_duration,
)


def _print_health(info: dict) -> None:
    gpu = info.get("gpu") or "CPU"
    vram = info.get("vram_total_gb")
    print(f"  [OK] 服務在線：{gpu}" + (f"（{vram} GB VRAM）" if vram else ""))
    print(f"      已載入模型：{', '.join(info.get('models_loaded') or []) or '（尚未載入）'}")
    print(f"      運作時間：{human_duration(info.get('uptime_seconds', 0))}")


def _open_notebook() -> None:
    print(f"  開啟筆記本：{NOTEBOOK_URL}")
    try:
        webbrowser.open(NOTEBOOK_URL)
    except Exception:
        print("  （無法自動開啟瀏覽器，請手動複製上方網址）")


def main(argv: list[str] | None = None) -> int:
    configure_windows_console()
    args = argv if argv is not None else sys.argv[1:]

    client = ColabVideoClient()
    print("=" * 68)
    print("  openGO_video — Google Colab GPU 遠端連線工具")
    print("=" * 68)

    # 1. 先檢查現有連線
    if client.url:
        print(f"\n[*] 目前網址：{client.url}")
        try:
            _print_health(client.health())
            choice = input("\n[*] 連線正常，是否仍要更換網址？(y/N)：").strip().lower()
            if choice != "y":
                return 0
        except ColabError as exc:
            print(f"\n[!] 連線失效：{exc}")

    # 2. 引導重啟 Colab
    print("\n" + "-" * 68)
    print("重啟步驟（約 1~2 分鐘）：")
    print("  1. 在 Colab 選單點選「執行階段 ➔ 全部執行」（Ctrl + F9）")
    print("  2. 等待最後一個儲存格印出 https://xxxx.trycloudflare.com")
    print("  3. 把該網址貼到下方")
    print("-" * 68 + "\n")
    if "--no-browser" not in args:
        _open_notebook()

    new_url = input("\n請貼上新的 Cloudflare Tunnel 網址：").strip()
    if not new_url:
        print("[!] 未輸入網址，已取消。")
        return 1

    try:
        client.set_url(new_url)
        print("\n[*] 網址已寫入 .env，正在驗證連線…")
        _print_health(client.health())
    except ColabError as exc:
        print(f"\n[X] 驗證失敗：{exc}")
        print("    請確認 Colab 最後一個儲存格仍在執行，且網址完整。")
        return 1

    print("\n" + "=" * 68)
    print("✅ 連線完成，可以開始生成影片")
    print("   文字轉影片：python -m opengovideo t2v --prompt \"...\"")
    print("   圖片轉影片：python -m opengovideo i2v --image input.png")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
