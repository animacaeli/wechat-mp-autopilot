"""AI 生成封面：LLM 美术指导 + Pillow 程序化渲染。

大模型（DeepSeek Flash 等）是文本模型，不能直接输出图像；思路是让它当
「美术指导」——按标题与账号定位从图案库选型、定配色（cover.designer.md
prompt），本地 Pillow 渲染成 900×383 封面。零新增依赖、国内可达、无版权。

降级链：design 不合法/调用失败 → 内置默认设计；调用方（images.py）仍有
local 渐变兜底。同一标题种子固定，重跑不换脸。
"""

from __future__ import annotations

import math
import random
import re
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import Config
from ..llm import LLM
from .common import load_stage_instructions

COVER_SIZE = (900, 383)
PATTERN_NAMES = ["waves", "dots", "contour", "mosaic", "beams", "circuit"]
DEFAULT_PALETTE = ["#24344d", "#4d6a8f", "#aebfd6"]

# 中文字体候选：macOS / Linux 服务器 / Docker / Windows 各放几个，
# 一个都找不到时封面退化为无字纯图案
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _stable_seed(text: str) -> int:
    return abs(hash(text)) % (2**32)


def _load_font(size: int):
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return None


def _fit_line(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """标题太长时截断加省略号，保证单行放得下。"""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


# ── 图案库：全部在 RGBA overlay 上绘制，颜色带 alpha ─────────


def _pattern_waves(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    for i in range(4):
        base_y = h * (0.18 + 0.2 * i) + rng.randint(-14, 14)
        amp = rng.randint(18, 42)
        k = rng.uniform(1.2, 2.6)
        phase = rng.uniform(0, 6.28)
        color = accents[i % len(accents)]
        pts = [(x, base_y + amp * math.sin(k * x / w * 6.283 + phase)) for x in range(0, w + 8, 8)]
        d.line(pts, fill=(*color, 70 + i * 22), width=rng.randint(10, 26))


def _pattern_dots(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    fx, fy = rng.randint(0, w), rng.randint(0, h)
    max_dist = math.hypot(w, h) * 0.75
    step = 34
    for x in range(step // 2, w, step):
        for y in range(step // 2, h, step):
            r = 8 * (1 - math.hypot(x - fx, y - fy) / max_dist)
            if r < 0.7:
                continue
            color = accents[rng.randrange(len(accents))]
            d.ellipse([x - r, y - r, x + r, y + r], fill=(*color, 110))


def _pattern_contour(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    cx, cy = w * rng.uniform(0.2, 0.8), h * rng.uniform(0.3, 0.7)
    k = rng.randint(2, 4)
    phase = rng.uniform(0, 6.28)
    for ring in range(5, 24):
        r0 = ring * 26
        pts = []
        for deg in range(0, 361, 8):
            rad = math.radians(deg)
            radius = r0 + 10 * math.sin(k * rad + phase) + ring * 3 * math.sin(3 * rad + phase)
            pts.append((cx + radius * math.cos(rad), cy + radius * math.sin(rad)))
        color = accents[ring % len(accents)]
        d.line(pts, fill=(*color, 60 + ring * 3), width=2)


def _pattern_mosaic(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    colors = [bg, *accents]
    for _ in range(rng.randint(50, 80)):
        x, y = rng.randint(-40, w + 40), rng.randint(-40, h + 40)
        size = rng.randint(30, 110)
        pts = [(x + rng.randint(-size, size), y + rng.randint(-size, size)) for _ in range(3)]
        color = colors[rng.randrange(len(colors))]
        d.polygon(pts, fill=(*color, rng.randint(26, 60)))


def _pattern_beams(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    slope = rng.uniform(0.25, 0.6) * rng.choice((-1, 1))
    for i in range(rng.randint(5, 9)):
        x0 = rng.randint(-120, w + 40)
        width = rng.randint(40, 130)
        color = accents[i % len(accents)]
        d.polygon(
            [(x0, 0), (x0 + width, 0), (x0 + width - slope * h, h), (x0 - slope * h, h)],
            fill=(*color, rng.randint(30, 55)),
        )


def _pattern_circuit(d: ImageDraw.ImageDraw, bg, accents, rng, w, h):
    accent = accents[0]
    grid = 28
    for _ in range(rng.randint(7, 11)):
        x = rng.randrange(0, w, grid)
        y = rng.randrange(0, h, grid)
        pts = [(x, y)]
        for _ in range(rng.randint(2, 5)):
            if rng.random() < 0.5:
                x = min(max(x + rng.choice((-1, 1)) * grid * rng.randint(1, 4), -20), w + 20)
            else:
                y = min(max(y + rng.choice((-1, 1)) * grid * rng.randint(1, 3), -20), h + 20)
            pts.append((x, y))
        d.line(pts, fill=(*accent, 120), width=2)
        for px, py in pts:
            d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(*accent, 180))


_PATTERNS = {
    "waves": _pattern_waves,
    "dots": _pattern_dots,
    "contour": _pattern_contour,
    "mosaic": _pattern_mosaic,
    "beams": _pattern_beams,
    "circuit": _pattern_circuit,
}


# ── 设计与渲染 ────────────────────────────────────────────


def _validate_palette(raw) -> list[str] | None:
    if not isinstance(raw, list) or not 2 <= len(raw) <= 4:
        return None
    values = [str(c).lower() for c in raw]
    if not all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in values):
        return None
    return values


def generate_cover(title: str, design: dict) -> tuple[Path, dict]:
    """按设计稿渲染封面；design 不合法的部分静默回落到默认。"""
    pattern = design.get("pattern")
    if pattern not in PATTERN_NAMES:
        pattern = "waves"
    palette = _validate_palette(design.get("palette")) or DEFAULT_PALETTE
    applied = {"pattern": pattern, "palette": palette}

    bg = _hex_to_rgb(palette[0])
    accents = [_hex_to_rgb(c) for c in palette[1:]]
    rng = random.Random(_stable_seed(f"{title}|{pattern}"))
    w, h = COVER_SIZE

    img = Image.new("RGB", COVER_SIZE, bg)
    overlay = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    _PATTERNS[pattern](ImageDraw.Draw(overlay), bg, accents, rng, w, h)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 底部压暗条 + 标题白字（与图库封面同一套排版语言）
    band = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([(0, h - 130), (w, h)], fill=(10, 14, 20, 160))
    img = Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")

    draw = ImageDraw.Draw(img)
    font = _load_font(56)
    if font is not None:
        text = _fit_line(draw, title, font, w - 72)
        draw.text((36, h - 100), text, font=font, fill=(255, 255, 255))

    out = Path(tempfile.gettempdir()) / f"autopilot-gen-cover-{int(time.time() * 1000)}.jpg"
    img.save(out, "JPEG", quality=88)
    return out, applied


def design_and_generate(llm: LLM, cfg: Config, title: str) -> tuple[Path, dict]:
    """LLM 出设计稿 → 渲染。设计环节任何失败都用内置默认设计，绝不阻塞。"""
    design = None
    source_label = ""
    try:
        system, prov = load_stage_instructions("cover")
        source_label = prov["label"]
        user = f"【文章标题】{title}\n【账号领域】{cfg.niche_field}\n【写作风格】{cfg.style_preset}\n\n请给出封面设计。"
        raw = llm.chat_json(system, user)
        if isinstance(raw, dict):
            pattern = raw.get("pattern")
            palette = _validate_palette(raw.get("palette"))
            if pattern in PATTERN_NAMES and palette:
                design = {"pattern": pattern, "palette": palette, "mood": str(raw.get("mood", ""))[:60]}
    except Exception:
        design = None
    if design is None:
        design = {"pattern": "waves", "palette": DEFAULT_PALETTE, "mood": "内置默认设计（LLM 设计环节失败）"}

    path, applied = generate_cover(title, design)
    return path, {**design, **applied, "pattern_applied": applied["pattern"], "source": source_label}
