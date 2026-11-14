---
name: opengovideo-bridge
description: openGO_video 專案的 Colab GPU 影片生成橋接工作流。當使用者要「生成影片」、「用 Colab 算圖」、「文字轉影片」、「圖片轉影片」、或說「重啟 Colab／重新連線」時使用。包含 CLI/SDK 指令、非同步工作 API、斷線重連 SOP 與疑難排解。
---

# openGO_video 遠端 GPU 影片生成橋接

本專案位於 `C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video`，用本機 CLI 遙控 Google Colab 的免費 GPU（L4 / T4）執行開源影片生成模型。

## 架構

```text
本機 CLI / Agent  ──HTTP──▶  Cloudflare Tunnel  ──▶  Colab FastAPI
   submit job                                      AnimateDiff / SVD-XT
   poll progress                                   輸出 MP4
   download  ◀──────────────────────────────────────┘
```

## 使用流程

### 1. 檢查連線

```powershell
cd "C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video"
python -m opengovideo status
```

### 2. 斷線重連 SOP（Colab 休眠／重開機／換網址）

1. 開啟筆記本：<https://colab.research.google.com/github/MazingerSam/openGO_video/blob/main/notebooks/colab_opengovideo.ipynb>
2. 「執行階段 ➔ 全部執行」（`Ctrl + F9`），等待最後一格印出 `https://xxxx.trycloudflare.com`。
3. 綁定新網址：

```powershell
python -m opengovideo connect https://xxxx.trycloudflare.com
```

或執行互動精靈 `python connect.py`（`restart_colab.bat` 會呼叫它）。

### 3. 生成影片

```powershell
# 文字轉影片（預設 16 幀）
python -m opengovideo t2v --prompt "a cyber lion walking on a neon platform, cinematic lighting, 4k"

# 圖片轉影片（預設 25 幀）
python -m opengovideo i2v --image .\input.png --frames 25
```

輸出位置：`outputs/t2v_<提示詞>_<時間戳>.mp4`、`outputs/i2v_<時間戳>.mp4`。

## Python SDK

```python
from opengovideo import ColabVideoClient

client = ColabVideoClient()

# 一次性（會自動等待並下載）
path = client.generate_text2video(prompt="...", num_frames=16)

# 非同步
job_id = client.submit_image2video(image="input.png")
client.wait(job_id, on_progress=lambda job: print(job["progress"]))
client.download(job_id)
```

## 提示詞建議

- **AnimateDiff**：`masterpiece, best quality, highly detailed, photorealistic, 4k, cinematic lighting`；加入動作詞（walking、glowing、camera moving forward）。
- **SVD-XT**：輸入圖建議 1024×576 橫式；`motion_bucket_id` 100~150（預設 127）。

## 疑難排解

| 症狀 | 處理 |
| :--- | :--- |
| `連不上 Colab 伺服器` | Tunnel 失效，執行重連 SOP |
| `CUDA out of memory` | 減少 `--frames`（T4：t2v 16 / i2v 25），或改 L4 |
| 工作卡在 `queued` | 前一個工作仍在跑，GPU 一次只處理一件 |
| `409 工作尚未完成` | 先 `python -m opengovideo job <job_id>` 確認狀態 |
| 想釋放 VRAM | 在 Colab 執行 `app.state.store.pipeline.unload()` |

## 安全規則

- 不把 Tunnel 網址、`.env`、`outputs/` 提交進 Git。
- 不下載或散布個資、學生真名相關素材。
