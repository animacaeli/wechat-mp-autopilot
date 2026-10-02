"""⑥ 配图：按 provider 取图 → Pillow 加工 → 上传微信素材。

provider 可选（config `images.provider`，默认 gen）：
- gen：AI 生成封面——LLM 当美术指导（选图案/配色），本地 Pillow 渲染（见 artgen.py）
- local：本地渐变封面 + 标题字，零外部依赖（连 LLM 设计环节也不需要）
- openverse：免 key（CC0/公有领域图），海外服务，国内网络通常需代理
- pixabay：免费 key（pixabay.com/api/docs 仍在发放），海外服务
- pexels：官方已暂停发放新 key，仅已有 key 的用户可用

所有远程取图失败都会降级到本地封面——draft/add 要求封面素材，
thumb_media_id 不允许为空。

- 封面：裁 900×383 → 叠加标题字 → 永久素材 thumb_media_id
- 正文点缀：1 张 → media/uploadimg 换微信域名 URL → 插入 HTML 块列表
"""

from __future__ import annotations

import random
import re
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from ..config import Config
from ..llm import LLM
from ..wechat.client import WechatClient
from . import artgen
from .artgen import _fit_line, _load_font
from .renderer import render_shell

COVER_SIZE = (900, 383)
PEXELS_SEARCH = "https://api.pexels.com/v1/search"
PIXABAY_SEARCH = "https://pixabay.com/api/"
OPENVERSE_SEARCH = "https://api.openverse.org/v1/images/"


def run_images(cfg: Config, wechat: WechatClient, llm: LLM,
               blocks: list[str], title: str) -> tuple[str, dict]:
    meta: dict = {"cover_media_id": None, "body_images": [], "fallback_used": False}
    cover_src_url = None

    # 封面：draft/add 要求 thumb_media_id，因此取图失败时用本地渐变封面兜底
    if cfg.image_provider == "gen":
        processed, design = artgen.design_and_generate(llm, cfg, title)
        meta["cover_source"] = "ai_generated"
        meta["cover_design"] = design
    elif cfg.image_provider == "local":
        processed = _local_cover(title)
        meta["cover_source"] = "local"
    else:
        try:
            keywords = _en_keywords(llm, title)
            cover_path, cover_src_url = _fetch_photo(cfg, keywords)
            if cover_path is None:
                raise RuntimeError(f"{cfg.image_provider} 按 “{keywords}” 无可用图片")
            processed = _process_cover(cover_path, title)
            meta["cover_query"] = keywords
        except Exception as err:
            if not cfg.fallback_plain:
                raise
            meta["fallback_used"] = True
            meta["fallback_reason"] = str(err)[:200]
            processed = _local_cover(title)
            meta["cover_source"] = "local_fallback"
    meta["cover_media_id"] = wechat.add_material(processed, "thumb")

    # 正文图：锦上添花，任何失败只记录不阻塞（gen/local 不配正文图）
    if cfg.image_provider not in {"local", "gen"}:
        try:
            keywords = meta.get("cover_query") or _en_keywords(llm, title)
            body_path, _ = _fetch_photo(cfg, keywords, exclude_url=cover_src_url)
            if body_path is not None:
                url = wechat.upload_content_image(body_path)
                meta["body_images"] = [url]
                blocks = _splice_image(blocks, url)
        except Exception as err:
            meta["body_image_skipped"] = str(err)[:200]

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
    """按 provider 分发；返回 (本地临时文件, 源图 URL)，无可用图返回 (None, None)。"""
    if cfg.image_provider == "pixabay":
        return _fetch_pixabay(cfg, keywords, exclude_url)
    if cfg.image_provider == "openverse":
        return _fetch_openverse(keywords, exclude_url)
    return _fetch_pexels(cfg, keywords, exclude_url)


def _fetch_pexels(cfg: Config, keywords: str, exclude_url: str | None = None) -> tuple[Path | None, str | None]:
    resp = httpx.get(
        PEXELS_SEARCH,
        params={"query": keywords, "per_page": 10, "orientation": "landscape"},
        headers={"Authorization": cfg.secret(cfg.pexels_api_key_env)},
        timeout=20,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    random.shuffle(photos)
    for photo in photos:
        url = (photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")
        if not url or url == exclude_url:
            continue
        path = _download_image(url)
        if path is not None:
            return path, url
    return None, None


def _fetch_pixabay(cfg: Config, keywords: str, exclude_url: str | None = None) -> tuple[Path | None, str | None]:
    resp = httpx.get(
        PIXABAY_SEARCH,
        params={"key": cfg.secret(cfg.pixabay_api_key_env), "q": keywords,
                "image_type": "photo", "orientation": "horizontal",
                "per_page": 10, "safesearch": "true"},
        timeout=20,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    random.shuffle(hits)
    for hit in hits:
        url = hit.get("largeImageURL") or hit.get("webformatURL")
        if not url or url == exclude_url:
            continue
        path = _download_image(url)
        if path is not None:
            return path, url
    return None, None


def _fetch_openverse(keywords: str, exclude_url: str | None = None) -> tuple[Path | None, str | None]:
    """免 key 图库。license 限定 CC0/PDM：可商用且无需署名。"""
    resp = httpx.get(
        OPENVERSE_SEARCH,
        params={"q": keywords, "license": "cc0,pdm", "page_size": 20, "mature": "false"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    landscape = [r for r in results if (r.get("width") or 0) >= (r.get("height") or 0)] or results
    random.shuffle(landscape)
    for item in landscape:
        url = item.get("url")
        if not url or url == exclude_url:
            continue
        path = _download_image(url)
        if path is not None:
            return path, url
    return None, None


def _download_image(url: str) -> Path | None:
    """下载并按魔数校验是 JPEG/PNG 才接受（openverse 结果偶有非图文件）。"""
    try:
        data = httpx.get(url, timeout=30, follow_redirects=True).content
    except httpx.HTTPError:
        return None
    if data[:3] == b"\xff\xd8\xff":
        suffix = ".jpg"
    elif data[:8].startswith(b"\x89PNG"):
        suffix = ".png"
    else:
        return None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(data)
        return Path(fh.name)


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


def _local_cover(title: str) -> Path:
    """本地生成封面：左右渐变底 + 居中标题白字，零外部依赖。"""
    img = _gradient(COVER_SIZE, (52, 68, 88), (110, 128, 150))
    font = _load_font(54)
    if font is not None:
        draw = ImageDraw.Draw(img)
        text = _fit_line(draw, title, font, img.width - 120)
        width = draw.textlength(text, font=font)
        draw.text(((img.width - width) / 2, (img.height - 70) / 2), text,
                  font=font, fill=(255, 255, 255))
    out = Path(tempfile.gettempdir()) / f"autopilot-cover-{int(time.time() * 1000)}.jpg"
    img.save(out, "JPEG", quality=88)
    return out


def _gradient(size: tuple[int, int], c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size
    for x in range(w):
        t = x / (w - 1)
        draw.line([(x, 0), (x, h)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    return img


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


def _splice_image(blocks: list[str], url: str) -> list[str]:
    """正文图插在约 40% 处的段落之间。"""
    if not blocks:
        return [f'<img src="{url}" style="width:100%;border-radius:6px;margin:12px auto;display:block;"/>']
    pos = max(len(blocks) * 2 // 5, 1)
    img_html = f'<img src="{url}" style="width:100%;border-radius:6px;margin:12px auto;display:block;"/>'
    return blocks[:pos] + [img_html] + blocks[pos:]
