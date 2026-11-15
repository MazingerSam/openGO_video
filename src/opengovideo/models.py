"""支援的模型清單（伺服器端與客戶端共用）。

如何新增模型：
1. 若與現有模型的「載入方式」相同（family 相同）——只要在 `MODELS` 加一筆即可。
2. 若是全新類型的模型——在 `MODELS` 加一筆，並在 `pipeline.py` 用
   `@builder("<family>")` 註冊一個載入函式。

範例見本檔最下方的「新增模型範例」註解區。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    key: str
    task: str  # text2video | image2video
    family: str  # 對應 pipeline.py 中 @builder() 註冊的載入器名稱
    repo_id: str
    description: str
    motion_adapter: str | None = None
    variant: str | None = None
    default_frames: int = 16
    default_fps: int = 8
    default_steps: int = 25
    default_guidance: float = 7.5
    builder_kwargs: dict = field(default_factory=dict)  # 額外傳給 builder 的參數


MODELS: dict[str, ModelSpec] = {
    "animatediff-v1.5": ModelSpec(
        key="animatediff-v1.5",
        task="text2video",
        family="animatediff",
        repo_id="SG161222/Realistic_Vision_V5.1_noVAE",
        motion_adapter="guoyww/animatediff-motion-adapter-v1-5-2",
        description="AnimateDiff + Realistic Vision v5.1（文字轉影片，T4 可跑）",
        default_frames=16,
        default_fps=8,
        default_steps=25,
        default_guidance=7.5,
    ),
    "svd-xt": ModelSpec(
        key="svd-xt",
        task="image2video",
        family="svd",
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt",
        variant="fp16",
        description="Stable Video Diffusion XT（圖片轉影片，1024x576）",
        default_frames=25,
        default_fps=7,
    ),
}

DEFAULT_TEXT2VIDEO_MODEL = "animatediff-v1.5"
DEFAULT_IMAGE2VIDEO_MODEL = "svd-xt"


# ---------------------------------------------------------------------------
# 新增模型範例（取消註解即可用；family 需已有對應 builder）
# ---------------------------------------------------------------------------
#
# "animatediff-lightning": ModelSpec(
#     key="animatediff-lightning",
#     task="text2video",
#     family="animatediff",            # 沿用 animatediff builder，零程式碼
#     repo_id="ByteDance/AnimateDiff-Lightning",
#     motion_adapter="guoyww/animatediff-motion-adapter-v1-5-2",
#     description="AnimateDiff Lightning（4 步快速生成）",
#     default_steps=4,
# ),
#
# "svd-xt-1.1": ModelSpec(
#     key="svd-xt-1.1",
#     task="image2video",
#     family="svd",                    # 沿用 svd builder
#     repo_id="stabilityai/stable-video-diffusion-img2vid-xt-1-1",
#     variant="fp16",
#     description="SVD-XT 1.1",
#     default_frames=25,
#     default_fps=6,
# ),
#
# 全新 family 範例（例如 LTX-Video 文字轉影片）：
#   1. 在 MODELS 加一筆，family="ltx"。
#   2. 在 pipeline.py 加：
#      @builder("ltx")
#      def _build_ltx(spec, dtype, use_cuda):
#          from diffusers import LTXPipeline
#          pipe = LTXPipeline.from_pretrained(spec.repo_id, torch_dtype=dtype)
#          return pipe
#   3. 若推論參數與現有 generate_text2video 不同，在 PipelineManager
#      新增對應的 generate_* 方法並於 server.py 接上端點。


def list_models(task: str | None = None) -> list[ModelSpec]:
    specs = list(MODELS.values())
    if task:
        specs = [spec for spec in specs if spec.task == task]
    return specs


def get_model(key: str) -> ModelSpec:
    try:
        return MODELS[key]
    except KeyError as exc:
        available = ", ".join(sorted(MODELS))
        raise ValueError(f"未知模型 `{key}`，可用模型：{available}") from exc


def default_model_for(task: str) -> str:
    return DEFAULT_TEXT2VIDEO_MODEL if task == "text2video" else DEFAULT_IMAGE2VIDEO_MODEL
