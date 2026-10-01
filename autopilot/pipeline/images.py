"""⑥ 配图：Pexels 取图 → Pillow 加工 → 上传微信素材。

- 封面：按选题关键词取图 → 裁 900×383 → 叠加标题字 → 永久素材 thumb_media_id
- 正文点缀：1 张 → media/uploadimg 换微信域名 URL → 插入 HTML 块列表
- 全链路失败（无结果/超时/无 key）→ fallback_plain 降级为纯文字
"""

from __future__ import annotations

import random
import re
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from ..config import Config
from ..llm import LLM
from ..wechat.client import WechatClient
from .renderer import render_shell

COVER_SIZE = (900, 383)
PEXELS_SEARCH = "https://api.pexels.com/v1/search"

# 中文字体候选：macOS / Linux 服务器 / Docker / Windows 各放几个，
# 一个都找不到时跳过封面加字，只保留裁剪后的图
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]


def run_images(cfg: Config, wechat: WechatClient, llm: LLM,
               blocks: list[str], title: str) -> tuple[str, dict]:
    meta: dict = {"cover_media_id": None, "body_images": [], "fallback_used": False}

    try:
        keywords = _en_keywords(llm, title)
        cover_path, cover_src_url = _fetch_photo(cfg, keywords)
        if cover_path is None:
            raise RuntimeError(f"Pexels 按 “{keywords}” 无可用图片")

        processed = _process_cover(cover_path, title)
        meta["cover_media_id"] = wechat.add_material(processed, "thumb")
        meta["cover_query"] = keywords

        body_path, _ = _fetch_photo(cfg, keywords, exclude_url=cover_src_url)
        if body_path is not None:
            url = wechat.upload_content_image(body_path)
            meta["body_images"] = [url]
            blocks = _splice_image(blocks, url)
    except Exception as err:  # 配图是锦上添花，任何失败都不阻塞主流程
        if not cfg.fallback_plain:
            raise
        meta["fallback_used"] = True
        meta["fallback_reason"] = str(err)[:200]

    footer = "AI 辅助创作" if cfg.ai_disclosure else ""
    return render_shell(blocks, cfg.style_template, footer=footer), meta


def _en_keywords(llm: LLM, title: str) -> str:
    """Pexels 只支持英文检索，用一次轻量 LLM 调用换关键词。"""
    reply = llm.chat(
        "你是一个翻译助手。把中文标题转换成 2~3 个适合图库检索的英文关键词，"
        "只输出关键词本身，用空格分隔，不要任何解释。",
        title,
    )
    words = re.findall(r"[a-zA-Z]+", reply)
    if not words:
        return "technology abstract"
    return " ".join(words[:3])


def _fetch_photo(cfg: Config, keywords: str, exclude_url: str | None = None) -> tuple[Path | None, str | None]:
    """搜索并下载一张图，返回 (本地临时文件, 源图 URL)；无可用图返回 (None, None)。"""
    key = cfg.secret(cfg.pexels_api_key_env)
    resp = httpx.get(
        PEXELS_SEARCH,
        params={"query": keywords, "per_page": 10, "orientation": "landscape"},
        headers={"Authorization": key},
        timeout=20,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    random.shuffle(photos)
    for photo in photos:
        url = (photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")
        if not url or url == exclude_url:
            continue
        data = httpx.get(url, timeout=30, follow_redirects=True).content
        with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=False) as fh:
            fh.write(data)
            return Path(fh.name), url
    return None, None


def _process_cover(src: Path, title: str) -> Path:
    img = Image.open(src).convert("RGB")
    img = _cover_crop(img)

    font = _load_font(56)
    if font is not None:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, img.height - 130), (img.width, img.height)], fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        text = _fit_line(draw, title, font, img.width - 72)
        draw.text((36, img.height - 100), text, font=font, fill=(255, 255, 255, 255))

    out = Path(tempfile.gettempdir()) / f"cover_{src.stem}.jpg"
    img.save(out, "JPEG", quality=88)
    return out


def _cover_crop(img: Image.Image) -> Image.Image:
    """按 900×383（2.35:1）中心裁剪再缩放。"""
    target_ratio = COVER_SIZE[0] / COVER_SIZE[1]
    w, h = img.size
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        box = ((w - new_w) // 2, 0, (w + new_w) // 2, h)
    else:
        new_h = int(w / target_ratio)
        box = (0, max((h - new_h) // 3, 0), w, max((h - new_h) // 3, 0) + new_h)
    return img.crop(box).resize(COVER_SIZE, Image.LANCZOS)


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


def _splice_image(blocks: list[str], url: str) -> list[str]:
    """正文图插在约 40% 处的段落之间。"""
    if not blocks:
        return [f'<img src="{url}" style="width:100%;border-radius:6px;margin:12px auto;display:block;"/>']
    pos = max(len(blocks) * 2 // 5, 1)
    img_html = f'<img src="{url}" style="width:100%;border-radius:6px;margin:12px auto;display:block;"/>'
    return blocks[:pos] + [img_html] + blocks[pos:]
