# 🎬 openGO_video

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/MazingerSam/openGO_video/blob/main/notebooks/colab_opengovideo.ipynb)

**本機 Agent 遙控 Google Colab 免費 GPU 的開源影片生成工作流。**
用自然語言在本地下指令，Colab 端用 AnimateDiff（文字→影片）或 SVD-XT（圖片→影片）推論，MP4 自動下載回 `outputs/`。

> 本專案是 `video_test` 的 v2 重寫版：改為**非同步工作佇列 + 進度回報 + 模型註冊表**，長影片生成不再被 HTTP 逾時中斷。

---

## ✨ 與 v1 的差異

| 項目 | video_test (v1) | openGO_video (v2) |
| :--- | :--- | :--- |
| 生成請求 | 同步阻塞，長生成易逾時 | 送出即回 `job_id`，輪詢進度 |
| 模型管理 | 寫死在程式內 | `models.py` 註冊表（新增模型只需加一筆） |
| 進度 | 無 | 每步回報百分比與訊息 |
| 伺服器 | 單一 notebook 內嵌程式 | 可測試的 `src/opengovideo/server.py` |
| 客戶端 | 同步 API | 非同步工作 API + 同步相容端點 |
| CLI | `src/colab_client.py` | `python -m opengovideo`（connect / status / models / t2v / i2v / job） |

---

## 🧭 系統架構

```text
[ 本機 Agent / CLI ]
      │  1. POST /jobs/text2video  → 取得 job_id
      │  2. GET  /jobs/{id}        → 輪詢進度
      │  3. GET  /jobs/{id}/video  → 下載 MP4
      ▼
[ Cloudflare Tunnel（免註冊、免金鑰）]
      ▼
[ Google Colab（L4 / T4 GPU）+ FastAPI ]
      │  AnimateDiff / SVD-XT（CPU offload、VAE slicing）
      ▼
[ outputs/*.mp4 ]
```

---

## 🚀 快速開始

### 1. 安裝本機依賴

```powershell
cd "C:\Users\sam09\OneDrive\文件\AiAgent\openGO_video"
python -m pip install -r requirements.txt
# 或安裝成套件（可用 opengovideo 指令）
python -m pip install -e .
```

### 2. 啟動 Colab GPU 伺服器

1. 點擊上方 **Open in Colab** 徽章。
2. 選單「執行階段 ➔ 變更執行階段類型」選 **L4 GPU**（推薦）或 **T4 GPU**。
3. 「執行階段 ➔ 全部執行」（`Ctrl + F9`），等待最後一格印出：

```text
🔗 公開網址：https://xxxx-xxxx.trycloudflare.com
```

### 3. 綁定網址

```powershell
python connect.py
```

或直接：

```powershell
python -m opengovideo connect https://xxxx.trycloudflare.com
```

### 4. 生成影片

```powershell
# 文字轉影片
python -m opengovideo t2v --prompt "a cyber lion walking on a neon platform, cinematic lighting, 4k"

# 圖片轉影片
python -m opengovideo i2v --image .\input.png --frames 25
```

完成後檔案位於 `outputs/t2v_<提示詞>_<時間戳>.mp4`。

---

## 🛠️ CLI 指令

| 指令 | 說明 |
| :--- | :--- |
| `python -m opengovideo connect <URL>` | 綁定 Colab 網址並寫入 `.env` |
| `python -m opengovideo status` | 顯示 GPU、已載入模型、工作統計 |
| `python -m opengovideo models` | 列出可用模型（● 已在 Colab 載入） |
| `python -m opengovideo t2v --prompt "..."` | 文字轉影片 |
| `python -m opengovideo i2v --image path.png` | 圖片轉影片 |
| `python -m opengovideo job <job_id> --download` | 查詢並下載既有工作 |

`t2v` 常用參數：`--frames`、`--steps`、`--guidance`、`--fps`、`--seed`、`--model`、`--output`

`i2v` 常用參數：`--frames`、`--fps`、`--motion`（motion_bucket_id，建議 100~150）、`--seed`

---

## 🐍 Python SDK

```python
from opengovideo import ColabVideoClient

client = ColabVideoClient()  # 讀取 .env 的 COLAB_URL

print(client.health()["gpu"])

path = client.generate_text2video(
    prompt="a majestic cyber lion walking on a neon platform, 4k, cinematic lighting",
    num_frames=16,
    on_progress=lambda job: print(job["progress"]),
)
print("輸出：", path)
```

非同步用法：

```python
job_id = client.submit_text2video(prompt="underwater jellyfish, glowing")
client.wait(job_id, on_progress=lambda job: print(job["progress"]))
client.download(job_id)
```

---

## 🌐 伺服器 API

| 方法 | 路徑 | 說明 |
| :--- | :--- | :--- |
| GET | `/health` | GPU、VRAM、已載入模型、工作統計 |
| GET | `/models` | 模型清單與預設值 |
| POST | `/jobs/text2video` | 建立文字轉影片工作，回傳 `job_id` |
| POST | `/jobs/image2video` | 建立圖片轉影片工作（`image_base64` 或 `image_url`） |
| GET | `/jobs/{job_id}` | 工作狀態、`progress`（0~1）、`message` |
| GET | `/jobs/{job_id}/video` | 下載 MP4 |
| POST | `/generate/text2video` | 同步生成，回傳 base64（相容 v1） |
| POST | `/generate/image2video` | 同步生成，回傳 base64（相容 v1） |

FastAPI 互動文件：`<COLAB_URL>/docs`

---

## 📁 專案結構

```text
openGO_video/
├─ notebooks/
│  └─ colab_opengovideo.ipynb   # Colab 端：安裝、載入模型、啟動 Tunnel
├─ src/opengovideo/
│  ├─ config.py                 # .env 設定、筆記本網址
│  ├─ models.py                 # 模型註冊表（新增模型改這裡）
│  ├─ client.py                 # 本機客戶端（工作提交／輪詢／下載）
│  ├─ cli.py                    # python -m opengovideo
│  ├─ server.py                 # Colab 端 FastAPI + 工作佇列
│  ├─ pipeline.py               # diffusers 推論與 VRAM 管理
│  └─ utils.py                  # 檔案命名、base64、日誌
├─ tests/test_utils.py
├─ connect.py                   # 互動式重連精靈
├─ restart_colab.bat            # Windows 一鍵重連
├─ requirements.txt             # 本機（輕量）
├─ requirements-colab.txt       # Colab（torch/diffusers 由 Colab 預裝）
├─ ANTIGRAVITY.md               # Agent 工作規則（本專案入口）
├─ progress.md / CHANGELOG.md
└─ outputs/                     # 生成結果（不進 Git）
```

---

## ⚠️ 注意事項

- Colab 閒置約 90 分鐘會斷線，Tunnel 網址會失效；重新「全部執行」後再跑 `python connect.py` 即可。
- T4（16GB）建議：文字轉影片 16 幀、圖片轉影片 25 幀；L4（24GB）可連續生成。
- `outputs/`、`.env` 已被 `.gitignore` 排除，請勿把網址或個人資料推上 Git。
- 本專案只用開源模型與免費 Colab 額度，不需任何付費 API Key。

---

## 🗺️ 待辦

- [ ] 加入更多模型（LTX-Video、Wan 2.1 等）至 `models.py`
- [ ] 工作取消與 VRAM 自動回收策略
- [ ] 多段影片拼接與字幕
- [ ] GitHub Actions 執行單元測試

---

## 📜 授權

尚未指定（建議後續補上 MIT 或 Apache-2.0）。
