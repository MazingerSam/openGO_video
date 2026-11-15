---
name: opengovideo-bridge
description: openGO_video 專案的 Colab GPU 影片生成橋接工作流。當使用者要「生成影片」、「用 Colab 算圖」、「文字轉影片」、「圖片轉影片」、「新增模型」、或說「重啟 Colab／重新連線」時使用。包含 CLI/SDK 指令、非同步工作 API、斷線重連 SOP、如何新增模型，以及疑難排解。
---

# openGO_video 遠端 GPU 影片生成橋接

用本機 CLI / Agent 遙控 **Google Colab 免費 GPU**，以開源模型（AnimateDiff、SVD-XT）生成 MP4，自動下載回本機 `outputs/`。

- 專案路徑：`C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video`
- GitHub repo：https://github.com/MazingerSam/openGO_video（public）
- Colab 筆記本：https://colab.research.google.com/github/MazingerSam/openGO_video/blob/main/notebooks/colab_opengovideo.ipynb

## 架構

```text
本機 CLI / Agent  ──HTTP──▶  Cloudflare Tunnel  ──▶  Colab FastAPI
   POST /jobs/text2video  → job_id             AnimateDiff / SVD-XT
   GET  /jobs/{id}        → 進度               （CPU offload、VAE slicing）
   GET  /jobs/{id}/video  → 下載 MP4
```

## 快速使用

```powershell
cd "C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video"

python -m opengovideo status                    # 檢查連線 / GPU / 已載入模型
python -m opengovideo models                    # 列出可用模型
python -m opengovideo t2v --prompt "太空人漫步，電影感光線" --frames 16
python -m opengovideo i2v --image .\input.png --frames 25
```

輸出：`outputs/t2v_<提示詞>_<時間戳>.mp4`、`outputs/i2v_<時間戳>.mp4`

## 斷線重連 SOP

Colab 閒置約 90 分鐘會斷線、Tunnel 網址每次重啟都不同。重新連線三步：

1. 開筆記本：「執行階段 ➔ **重新啟動並全部執行**」（`Ctrl+F9`）——一定要重啟 runtime 才會吃到最新程式碼。
2. 等最後一格印出 `🔗 公開網址：https://xxxx.trycloudflare.com`（且出現 `Uvicorn running on http://0.0.0.0:8000` 才算真的起來）。
3. 綁定新網址：

```powershell
python -m opengovideo connect https://xxxx.trycloudflare.com
```

或執行互動精靈 `python connect.py`（`restart_colab.bat` 會呼叫它）。

## Python SDK

```python
from opengovideo import ColabVideoClient

client = ColabVideoClient()          # 讀取 .env 的 COLAB_URL

# 一次性（自動等待 + 下載）
path = client.generate_text2video(prompt="...", num_frames=16)

# 非同步（適合長影片）
job_id = client.submit_image2video(image="input.png")
client.wait(job_id, on_progress=lambda job: print(job["progress"]))
client.download(job_id)
```

## 如何新增模型（保留彈性的關鍵）

模型採「註冊表 + 載入器」兩層設計。**新增模型分兩種情況：**

### 情況 A：與現有模型同類型（family 相同）——只改 `src/opengovideo/models.py`

在 `MODELS` 加一筆即可，例如再加一個 AnimateDiff 模型：

```python
"animatediff-lightning": ModelSpec(
    key="animatediff-lightning",
    task="text2video",
    family="animatediff",            # 沿用現有載入器，零程式碼
    repo_id="ByteDance/AnimateDiff-Lightning",
    motion_adapter="guoyww/animatediff-motion-adapter-v1-5-2",
    description="AnimateDiff Lightning（4 步快速生成）",
    default_steps=4,
),
```

### 情況 B：全新類型（新 family）——加 `ModelSpec` + 一個載入器

1. `models.py`：在 `MODELS` 加一筆，`family="<新名稱>"`。
2. `pipeline.py`：用 `@builder("<新名稱>")` 註冊載入函式：

```python
@builder("ltx")
def _build_ltx(spec, dtype, use_cuda):
    from diffusers import LTXPipeline
    return LTXPipeline.from_pretrained(spec.repo_id, torch_dtype=dtype)
```

3. 若推論參數與現有 `generate_text2video` / `generate_image2video` 不同，在
   `PipelineManager` 新增對應的 `generate_*` 方法，並在 `server.py` 接上端點。

### 驗證

```powershell
python -m opengovideo models     # 應該看到新模型（● 表示 Colab 已載入）
python -m opengovideo t2v --prompt "..." --model <新key>
```

### 對照表：改什麼找哪個檔案

| 想做的事 | 改哪個檔案 |
| :--- | :--- |
| 加一個模型（同 family） | `src/opengovideo/models.py` |
| 加全新類型的載入方式 | `models.py` + `pipeline.py`（`@builder`） |
| 加全新推論邏輯 | `pipeline.py` + `server.py` |
| 加 Colab 依賴套件 | `requirements-colab.txt` |
| 改 CLI 參數 | `src/opengovideo/cli.py` |

## 疑難排解

| 症狀 | 原因與處理 |
| :--- | :--- |
| `連不上 Colab 伺服器` / DNS 找不到網域 | Tunnel 未啟動，走「斷線重連 SOP」 |
| `502 Bad Gateway`（持續） | Tunnel 活了但 uvicorn 沒起。檢查 Colab 輸出是否出現 `Uvicorn running on http://0.0.0.0:8000`；若看到 `RuntimeError: asyncio.run() cannot be called from a running event loop` 代表程式碼是舊版，重啟 runtime 再「全部執行」。 |
| `CUDA out of memory` | 減少 `--frames`（T4：t2v 16／i2v 25），或改 L4 / A100 |
| 工作卡在 `queued` | GPU 一次只跑一件，前一件還在跑 |
| `409 工作尚未完成` | 先 `python -m opengovideo job <job_id>` 看狀態 |
| 想釋放 VRAM | Colab 執行 `app.state.store.pipeline.unload()` |

## 提示詞建議

- **AnimateDiff（文字轉影片）**：`masterpiece, best quality, highly detailed, photorealistic, 4k, cinematic lighting`；加動作詞（walking、glowing、camera moving forward、gentle wind）。
- **SVD-XT（圖片轉影片）**：輸入圖建議 1024×576 橫式；`motion_bucket_id` 100~150（預設 127）。

## 安全規則

- 不把 Tunnel 網址、`.env`、`outputs/` 提交進 Git。
- 不下載或散布個資、學生真名相關素材。
- Colab 若把筆記本「儲存回 GitHub」會產生「使用 Colab 建立」commit，注意別蓋掉程式碼。
