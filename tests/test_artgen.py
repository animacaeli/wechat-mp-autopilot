"""AI 封面生成测试：图案库渲染、设计稿校验与降级。"""

import pytest
from PIL import Image

from autopilot.config import PROJECT_ROOT, load_config
from autopilot.pipeline.artgen import (
    DEFAULT_PALETTE,
    PATTERN_NAMES,
    design_and_generate,
    generate_cover,
)


class StubLLM:
    usage_tokens = 0

    def __init__(self, payload=None, boom=False):
        self.payload = payload
        self.boom = boom

    def chat_json(self, system, user):
        if self.boom:
            raise RuntimeError("api down")
        return self.payload


@pytest.fixture
def cfg():
    return load_config(PROJECT_ROOT / "config.example.toml")


@pytest.mark.parametrize("pattern", PATTERN_NAMES)
def test_every_pattern_renders_valid_jpeg(pattern):
    path, applied = generate_cover(f"标题-{pattern}", {"pattern": pattern, "palette": DEFAULT_PALETTE})
    assert applied["pattern"] == pattern
    img = Image.open(path)
    assert img.size == (900, 383)
    assert img.format == "JPEG"


def test_invalid_design_falls_back_to_default():
    path, applied = generate_cover("标题", {"pattern": "不存在", "palette": ["#fff", "#zzz"]})
    assert applied["pattern"] in PATTERN_NAMES
    assert applied["palette"] == DEFAULT_PALETTE
    assert Image.open(path).size == (900, 383)


def test_same_title_same_cover_bytes():
    design = {"pattern": "mosaic", "palette": ["#101820", "#2e5266", "#6dd5fa"]}
    p1, _ = generate_cover("同一个标题", design)
    p2, _ = generate_cover("同一个标题", design)
    assert p1.read_bytes() == p2.read_bytes()  # 种子固定，重跑不换脸


def test_design_and_generate_picks_from_candidates(cfg):
    """LLM 出 3 个候选 → 种子随机选其一；候选与最近用款全部落档。"""
    llm = StubLLM(
        {
            "candidates": [
                {"pattern": "circuit", "palette": ["#101820", "#2e5266", "#6dd5fa"], "mood": "a"},
                {"pattern": "contour", "palette": ["#1d3557", "#457b9d", "#a8dadc"], "mood": "b"},
                {"pattern": "mosaic", "palette": ["#3a2618", "#6b4f3a", "#c9b8a8"], "mood": "c"},
            ]
        }
    )
    title = "写代码十年我重新学提问"
    path, design = design_and_generate(llm, cfg, title)
    assert design["pattern"] in {"circuit", "contour", "mosaic"}
    assert len(design["candidates"]) == 3
    assert Image.open(path).size == (900, 383)
    # 同标题种子固定：重跑选同一个
    _, design2 = design_and_generate(llm, cfg, title)
    assert design2["pattern"] == design["pattern"]


def test_design_backward_compat_single_object(cfg):
    llm = StubLLM({"pattern": "beams", "palette": ["#132a13", "#31572c", "#90a955"], "mood": "x"})
    _, design = design_and_generate(llm, cfg, "旧格式兼容")
    assert design["pattern"] == "beams"


def test_design_avoids_recent_patterns(cfg, tmp_path, monkeypatch):
    """最近两篇用过的图案，本次候选里会被过滤掉。"""
    import json as _json

    from autopilot.pipeline import artgen

    monkeypatch.setattr(artgen, "PROJECT_ROOT", tmp_path)
    runs = tmp_path / "runs" / "2026-10-04-x"
    runs.mkdir(parents=True)
    (runs / "06_meta.json").write_text(_json.dumps({"cover_design": {"pattern": "waves"}}), encoding="utf-8")

    llm = StubLLM(
        {
            "candidates": [
                {"pattern": "waves", "palette": ["#24344d", "#4d6a8f", "#aebfd6"], "mood": "撞款"},
                {"pattern": "contour", "palette": ["#1d3557", "#457b9d", "#a8dadc"], "mood": "新鲜"},
            ]
        }
    )
    _, design = design_and_generate(llm, cfg, "避开 waves")
    assert design["pattern"] == "contour"
    assert design["recent_patterns"] == ["waves"]


def test_design_and_generate_llm_failure_uses_default(cfg):
    path, design = design_and_generate(StubLLM(boom=True), cfg, "标题")
    assert design["pattern"] in PATTERN_NAMES
    assert "默认" in design["mood"]
    assert Image.open(path).size == (900, 383)


def test_local_cover_gradients_rotate(tmp_path):
    """本地兜底封面：不同标题轮换不同渐变（不再每篇同款）。"""
    from autopilot.pipeline.images import _local_cover

    gradients = set()
    for title in ("标题甲", "标题乙", "标题丙", "标题丁", "标题戊"):
        path = _local_cover(title)
        img = Image.open(path)
        assert img.size == (900, 383)
        gradients.add(img.getpixel((5, 5)))  # 左端渐变起始色
    assert len(gradients) >= 2, f"5 个标题应至少覆盖 2 种渐变，实际 {gradients}"


def test_design_and_generate_bad_payload_uses_default(cfg):
    llm = StubLLM({"pattern": "hacker", "palette": ["red"]})  # 不合法设计稿
    _, design = design_and_generate(llm, cfg, "标题")
    assert design["pattern"] in PATTERN_NAMES


@pytest.mark.parametrize("pattern", PATTERN_NAMES)
def test_divider_renders_valid_jpeg(pattern):
    from autopilot.pipeline.artgen import generate_divider

    path = generate_divider({"pattern": pattern, "palette": DEFAULT_PALETTE}, index=1)
    img = Image.open(path)
    assert img.size == (900, 200)
    assert img.format == "JPEG"
