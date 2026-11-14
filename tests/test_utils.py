"""工具函式單元測試（不需要 torch / Colab）。"""

from pathlib import Path

from opengovideo.config import Settings
from opengovideo.models import get_model, list_models
from opengovideo.utils import build_filename, human_duration, is_media_file, slugify


def test_slugify_keeps_chinese_and_strips_symbols():
    assert slugify("A cyber lion, neon lights!") == "a-cyber-lion-neon-lights"
    assert slugify("太空人 漫步") == "太空人-漫步"
    assert slugify("!!!") == "video"


def test_build_filename_has_prefix_and_mp4():
    name = build_filename("t2v", "太空人漫步")
    assert name.startswith("t2v_太空人漫步_")
    assert name.endswith(".mp4")


def test_human_duration():
    assert human_duration(9) == "9s"
    assert human_duration(65) == "1m 05s"
    assert human_duration(3725) == "1h 02m 05s"


def test_media_suffix_detection():
    assert is_media_file(Path("a.MP4"))
    assert not is_media_file(Path("a.txt"))


def test_model_registry():
    assert get_model("animatediff-v1.5").task == "text2video"
    assert {spec.task for spec in list_models()} == {"text2video", "image2video"}
    try:
        get_model("does-not-exist")
    except ValueError as exc:
        assert "未知模型" in str(exc)
    else:
        raise AssertionError("應拋出 ValueError")


def test_settings_loads_without_env():
    settings = Settings.load()
    assert settings.request_timeout > 0
    assert settings.job_timeout > 0
    assert settings.output_dir.name == "outputs"
