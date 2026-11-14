# 專案進度追蹤 (Progress Tracking)

## 階段 1：專案初始化（已完成）

- [x] 建立 Git 儲存庫與 `.gitignore`（排除 `.env`、`outputs/`、影片檔）
- [x] 建立 Python 套件骨架 `src/opengovideo/`
- [x] 設定 `pyproject.toml`（`opengovideo` CLI 入口）
- [x] 撰寫 `README.md`、`ANTIGRAVITY.md`、`CHANGELOG.md`
- [x] 建立 Obsidian 專案駕駛艙
- [x] 單元測試骨架 `tests/test_utils.py`

## 階段 2：核心功能（骨架完成，待 Colab 實測）

- [x] 模型註冊表 `models.py`（AnimateDiff v1.5、SVD-XT）
- [x] 本機客戶端 `client.py`（提交／輪詢／下載／同步包裝）
- [x] CLI `python -m opengovideo`（connect / status / models / t2v / i2v / job）
- [x] Colab 伺服器 `server.py`（工作佇列、進度、下載、相容端點）
- [x] 推論管線 `pipeline.py`（延遲載入、CPU offload、VAE slicing）
- [x] Colab 筆記本 `notebooks/colab_opengovideo.ipynb`
- [ ] 在 Colab T4 / L4 實際跑通 t2v 與 i2v
- [ ] 驗證長影片（>16 幀）不被逾時中斷
- [ ] 確認程序重新載入模型時 VRAM 正常釋放

## 階段 3：發布與自動化（待辦）

- [x] 建立 GitHub repo `MazingerSam/openGO_video`（public）並 push
- [ ] 啟用 GitHub Actions 跑 `pytest`
- [ ] 補上 LICENSE
- [ ] 撰寫 Agent 技能文件 `.opencode/skills/opengovideo-bridge/SKILL.md`
- [ ] 評估新增 LTX-Video / Wan 2.1 模型
