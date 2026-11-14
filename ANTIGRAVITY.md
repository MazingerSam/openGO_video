# ANTIGRAVITY.md — openGO_video

## 專案入口

- 專案名稱：openGO_video
- 專案用途：本機 Agent 遙控 Google Colab GPU 的開源影片生成工具（video_test v2）
- 工作目錄：`C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video`
- GitHub repo：`MazingerSam/openGO_video`（待建立／待 push）
- 預設 branch：`main`
- 技術棧：Python 3.10+、FastAPI、diffusers、AnimateDiff、Stable Video Diffusion XT、Cloudflare Tunnel

## Obsidian 對應筆記

- Vault：`C:\mynote`
- 專案駕駛艙：`C:\mynote\openGO_video 專案駕駛艙.md`

## 工作規則

- 回應使用繁體中文（Taiwan）。
- 涉及檔案操作時回報完整產出位置（Windows 絕對路徑）。
- 使用 PowerShell 語法；避免 `&&` 串接。
- **開工**：讀本檔 → 讀 Obsidian 駕駛艙 → 檢查 `git status` → 必要時執行 `python -m opengovideo status`。
- **收工**：更新 Obsidian 駕駛艙與 `progress.md` → 必要時更新本檔 → 檢查 diff → 只提交本次相關檔案 → 更新 `CHANGELOG.md`。
- 不把每日流水帳寫進本檔；細節放 `progress.md` 與 Obsidian。
- 生成類工作優先走非同步工作 API（`submit_*` + `wait`），避免長請求逾時。

## 常用指令

```powershell
# 本機環境
python -m pip install -r requirements.txt
python -m pytest

# 連線
python connect.py
python -m opengovideo status
python -m opengovideo models

# 生成
python -m opengovideo t2v --prompt "..."
python -m opengovideo i2v --image .\input.png
```

## 不要做

- 不要 commit `.env`、API key、token、密碼、Firebase Admin 憑證。
- 不要 commit `outputs/` 內的生成檔案或個人圖片素材。
- 不要自動納入無關 git 變更；一次 commit 只處理一個主題。
- 不要在未確認的情況下刪除 `outputs/` 或使用者素材。
- 不要在 `server.py` 寫死 Tunnel 網址；一律由 `.env`／`connect.py` 管理。
- 不要儲存學生真名；正式資料只用班級代號與座號。
