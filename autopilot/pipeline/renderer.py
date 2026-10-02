"""⑤ 排版渲染：markdown → 微信兼容 HTML。

微信编辑器只认 inline style：无 class / 外部 CSS / JS，结构用 <section>
嵌套。做法：mistune 自定义渲染器按主题逐块输出 inline-styled HTML，
再由 templates/ 的 Jinja2 外壳包一层容器与页脚。
"""

from __future__ import annotations

import html as html_mod

import mistune
from jinja2 import Environment, FileSystemLoader

from ..config import PROJECT_ROOT

_env = Environment(
    loader=FileSystemLoader(str(PROJECT_ROOT / "templates")),
    autoescape=False,  # 内容本身是各阶段生成/转义过的 HTML
)

THEMES: dict[str, dict[str, str]] = {
    "clean": {
        "container": (
            "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC',"
            "'Hiragino Sans GB','Microsoft YaHei',sans-serif;font-size:15px;color:#3f3f3f;"
            "line-height:1.75;letter-spacing:0.5px;word-break:break-word;"
        ),
        "p": "margin:0 0 20px;font-size:15px;color:#3f3f3f;line-height:1.75;letter-spacing:0.5px;",
        "h2": (
            "margin:30px 0 16px;padding-left:10px;border-left:3px solid #07c160;"
            "font-size:17px;font-weight:bold;color:#1a1a1a;line-height:1.5;"
        ),
        "h3": "margin:24px 0 14px;font-size:16px;font-weight:bold;color:#1a1a1a;line-height:1.5;",
        "quote": (
            "margin:20px 0;padding:12px 16px;background:#f7f7f7;border-left:3px solid #d9d9d9;"
            "font-size:14px;color:#666;line-height:1.7;"
        ),
        "pre": (
            "margin:20px 0;padding:14px 16px;background:#282c34;color:#abb2bf;"
            "font-family:Menlo,Consolas,'Courier New',monospace;font-size:13px;line-height:1.6;"
            "border-radius:6px;white-space:pre-wrap;word-break:break-word;"
        ),
        "ul": "margin:0 0 20px;padding-left:1.4em;font-size:15px;color:#3f3f3f;line-height:1.9;",
        "li": "margin:0 0 6px;font-size:15px;color:#3f3f3f;line-height:1.9;",
        "strong": "font-weight:bold;color:#07c160;",
        "em": "font-style:italic;color:#8a8a8a;",
        "codespan": (
            "background:#f0f0f0;color:#c7254e;padding:2px 5px;border-radius:3px;"
            "font-family:Menlo,Consolas,monospace;font-size:14px;"
        ),
        "hr": "margin:28px 0;border:none;border-top:1px solid #eee;",
        "img": "display:block;width:100%;border-radius:6px;margin:12px auto;",
        "link": "color:#576b95;",
        "footer": (
            "margin-top:32px;padding-top:16px;border-top:1px solid #eee;font-size:12px;color:#b0b0b0;text-align:center;"
        ),
    },
    "wenyi": {
        "container": (
            "font-family:Georgia,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',serif;"
            "font-size:15px;color:#2b2b2b;line-height:1.9;letter-spacing:1px;word-break:break-word;"
        ),
        "p": "margin:0 0 24px;font-size:15px;color:#2b2b2b;line-height:1.9;letter-spacing:1px;text-align:justify;",
        "h2": (
            "margin:34px 0 18px;text-align:center;font-size:16px;font-weight:bold;color:#4a4a4a;letter-spacing:3px;"
        ),
        "h3": "margin:28px 0 14px;font-size:15px;font-weight:bold;color:#4a4a4a;letter-spacing:2px;",
        "quote": (
            "margin:24px 0;padding:10px 18px;border-left:2px solid #c9b8a8;"
            "font-size:14px;color:#7a6a5a;line-height:1.8;font-style:italic;"
        ),
        "pre": (
            "margin:24px 0;padding:14px 16px;background:#f6f4f0;color:#444;"
            "font-family:Menlo,Consolas,'Courier New',monospace;font-size:13px;line-height:1.6;"
            "border-radius:4px;white-space:pre-wrap;word-break:break-word;"
        ),
        "ul": "margin:0 0 24px;padding-left:1.4em;font-size:15px;color:#2b2b2b;line-height:2;",
        "li": "margin:0 0 8px;font-size:15px;color:#2b2b2b;line-height:2;",
        "strong": "font-weight:bold;color:#8c6d4f;",
        "em": "font-style:italic;color:#9a8a7a;",
        "codespan": (
            "background:#f0ece5;color:#8c6d4f;padding:2px 5px;border-radius:3px;"
            "font-family:Menlo,Consolas,monospace;font-size:14px;"
        ),
        "hr": ("margin:32px auto;width:30%;border:none;border-top:1px solid #c9b8a8;"),
        "img": "display:block;width:100%;margin:16px auto;border-radius:2px;",
        "link": "color:#8c6d4f;",
        "footer": ("margin-top:36px;text-align:center;font-size:12px;color:#b3a89b;letter-spacing:2px;"),
    },
}


class WechatRenderer(mistune.HTMLRenderer):
    """逐块输出 inline-styled HTML 并收集为 block 列表。"""

    def __init__(self, theme: dict[str, str]):
        super().__init__()
        self.theme = theme
        self.blocks: list[str] = []

    def _emit(self, html_str: str) -> str:
        self.blocks.append(html_str)
        return html_str

    def paragraph(self, text, **attrs):
        return self._emit(f'<p style="{self.theme["p"]}">{text}</p>')

    def heading(self, text, level, **attrs):
        tag = "h2" if level <= 2 else "h3"
        return self._emit(f'<{tag} style="{self.theme[tag]}">{text}</{tag}>')

    def block_code(self, code, info=None, **attrs):
        escaped = html_mod.escape(code, quote=False)
        return self._emit(f'<pre style="{self.theme["pre"]}">{escaped}</pre>')

    def block_quote(self, text):
        return self._emit(f'<blockquote style="{self.theme["quote"]}">{text}</blockquote>')

    def list(self, text, ordered, **attrs):
        tag = "ol" if ordered else "ul"
        return self._emit(f'<{tag} style="{self.theme["ul"]}">{text}</{tag}>')

    def list_item(self, text, **attrs):
        return f'<li style="{self.theme["li"]}">{text}</li>'

    def thematic_break(self):
        return self._emit(f'<hr style="{self.theme["hr"]}"/>')

    def emphasis(self, text):
        return f'<em style="{self.theme["em"]}">{text}</em>'

    def strong(self, text):
        return f'<strong style="{self.theme["strong"]}">{text}</strong>'

    def codespan(self, text):
        return f'<code style="{self.theme["codespan"]}">{text}</code>'

    def linebreak(self):
        return "<br/>"

    def softbreak(self):
        return "\n"

    def link(self, text, url, title=None):
        # 公众号正文外链会被过滤，渲染成微信惯用的灰蓝色文字即可
        return f'<span style="{self.theme["link"]}">{text}</span>'

    def image(self, text, url, title=None):
        return self._emit(f'<img src="{html_mod.escape(url, quote=True)}" style="{self.theme["img"]}"/>')


def render_blocks(markdown_text: str, template_name: str) -> list[str]:
    """markdown → inline-styled HTML 块列表（图片占位由配图阶段负责）。"""
    theme = THEMES.get(template_name, THEMES["clean"])
    renderer = WechatRenderer(theme)
    # escape=True：正文中的裸 HTML（如 LLM 漏出的 <script>）一律转义，不透传
    md = mistune.create_markdown(renderer=renderer, escape=True)
    md(markdown_text)
    return renderer.blocks


def render_shell(blocks: list[str], template_name: str, footer: str = "") -> str:
    """内容块 + Jinja2 外壳（容器、页脚）→ 最终微信正文 HTML。"""
    theme = THEMES.get(template_name, THEMES["clean"])
    tpl = _env.get_template(f"{template_name}.html.j2")
    return tpl.render(content="\n".join(blocks), footer=footer, theme=theme)


def ensure_headings(markdown_text: str, llm) -> tuple[str, bool]:
    """保底分节：全文没有二级标题时，让 LLM 只插入小标题行。

    返回 (处理后的文本, 是否插入)。插入失败或结果可疑时原样返回。
    """
    import re

    from .common import strip_fence

    if re.search(r"^##\s", markdown_text, re.MULTILINE):
        return markdown_text, False
    system = (
        "你是排版编辑。给文章插入 3~5 个二级标题（## 开头，单独一行）。\n"
        "要求：标题用 6~12 字的意象式短语，克制、有画面感，不要像目录式概括"
        "（例如「凌晨一点的厨房」而非「关于沟通问题」）。\n"
        "只允许插入 ## 标题行，一个字都不许改动、删除、增加原有正文。直接输出加好标题的全文。"
    )
    try:
        out = strip_fence(llm.chat(system, markdown_text))
    except Exception:
        return markdown_text, False
    # 防篡改检查：原文去掉空白后应几乎完整保留在结果里
    original = re.sub(r"\s+", "", markdown_text)
    result = re.sub(r"\s+", "", re.sub(r"^##\s.*$", "", out, flags=re.MULTILINE))
    if len(result) < len(original) * 0.97:
        return markdown_text, False
    return out, True
