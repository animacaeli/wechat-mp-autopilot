"""渲染器测试：微信兼容性约束（inline style、无 class、代码转义、外壳包裹）。"""

import re

from autopilot.pipeline.renderer import render_blocks, render_shell

SAMPLE = """# 主标题不该出现

这是第一段，包含**加粗**、*斜体*和`行内代码`。

## 二级小标题

- 列表项一
- 列表项二

### 三级小标题

```python
print("hello <script>")
```

> 这是一段引用。

---

结尾一段。
"""


def test_blocks_are_inline_styled_no_class():
    html = "\n".join(render_blocks(SAMPLE, "clean"))
    assert "class=" not in html
    assert "<script" not in html  # 代码块里的尖括号必须被转义
    assert 'style="' in html


def test_code_escaped():
    html = "\n".join(render_blocks(SAMPLE, "clean"))
    assert "&lt;script&gt;" in html
    assert "<pre" in html


def test_headings_rendered():
    blocks = render_blocks(SAMPLE, "clean")
    joined = "\n".join(blocks)
    assert "<h2" in joined and "<h3" in joined
    # markdown 的一级标题统一压成 h2（公众号正文标题层级从 h2 起更稳）
    assert "<h1" not in joined


def test_shell_wraps_container_and_footer():
    blocks = render_blocks("你好。", "clean")
    html = render_shell(blocks, "clean", footer="AI 辅助创作")
    assert html.startswith("<section")
    assert "AI 辅助创作" in html
    assert "font-family" in html  # 容器样式在位


def test_shell_without_footer_has_no_footer_section():
    html = render_shell(render_blocks("你好。", "wenyi"), "wenyi", footer="")
    assert "AI 辅助创作" not in html


def test_wenyi_theme_differs_from_clean():
    clean = "\n".join(render_blocks(SAMPLE, "clean"))
    wenyi = "\n".join(render_blocks(SAMPLE, "wenyi"))
    assert clean != wenyi
    assert "text-align:justify" in wenyi        # wenyi 段落两端对齐
    assert "serif" in render_shell(render_blocks("你好。", "wenyi"), "wenyi")  # 衬线字体在容器层


def test_no_external_link_tag():
    md = "看 [这个链接](https://example.com) 的说明。\n"
    html = "\n".join(render_blocks(md, "clean"))
    assert "<a " not in html  # 外链会被微信过滤，渲染为灰蓝 span
    assert "<span" in html
