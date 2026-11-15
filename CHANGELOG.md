# Changelog

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/) 格式，版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### Added

- 專案初始化：`src/opengovideo` 套件、`pyproject.toml`、`.gitignore`、`.env.example`。
- 模型註冊表 `models.py`，內建 `animatediff-v1.5`（文字轉影片）與 `svd-xt`（圖片轉影片）。
- 本機客戶端 `client.py`：工作提交、進度輪詢、MP4 下載、錯誤分類（離線／逾時／工作失敗）。
- CLI `python -m opengovideo`：`connect`、`status`、`models`、`t2v`、`i2v`、`job`。
- Colab 端 FastAPI 伺服器 `server.py`：`/health`、`/models`、非同步 `/jobs/*`、同步相容端點。
- 推論管線 `pipeline.py`：延遲載入、GPU 序列化、CPU offload、VAE slicing、逐步進度回報。
- Colab 筆記本 `notebooks/colab_opengovideo.ipynb`（安裝、啟動、Tunnel）。
- 互動式重連工具 `connect.py` 與 Windows 捷徑 `restart_colab.bat`。
- 單元測試 `tests/test_utils.py`。
- 模型「註冊表 + 載入器」擴充架構：`models.py` 新增 `family` 欄位，`pipeline.py` 以 `@builder()` 註冊載入器，同 family 加模型只需一筆、新 family 只需加一個載入函式。
- 完整工作流技能 `.opencode/skills/opengovideo-bridge/SKILL.md`（含 CLI/SDK、重連 SOP、如何新增模型、疑難排解）。

### Fixed

- Colab 事件迴圈下 `uvicorn.run()` 拋 `RuntimeError: asyncio.run() cannot be called from a running event loop`，改用 `Server.serve()` + `loop.run_until_complete()` 啟動。

## [0.1.0] - 2026-11-14

- 初始版本（與上方 Unreleased 同批建立）。
