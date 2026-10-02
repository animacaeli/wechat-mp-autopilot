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


def test_design_and_generate_uses_llm_choice(cfg):
    llm = StubLLM({"pattern": "circuit", "palette": ["#101820", "#2e5266", "#6dd5fa"], "mood": "科技"})
    path, design = design_and_generate(llm, cfg, "写代码十年我重新学提问")
    assert design["pattern"] == "circuit"
    assert Image.open(path).size == (900, 383)


def test_design_and_generate_llm_failure_uses_default(cfg):
    path, design = design_and_generate(StubLLM(boom=True), cfg, "标题")
    assert design["pattern"] in PATTERN_NAMES
    assert "默认" in design["mood"]
    assert Image.open(path).size == (900, 383)


def test_design_and_generate_bad_payload_uses_default(cfg):
    llm = StubLLM({"pattern": "hacker", "palette": ["red"]})  # 不合法设计稿
    _, design = design_and_generate(llm, cfg, "标题")
    assert design["pattern"] in PATTERN_NAMES
