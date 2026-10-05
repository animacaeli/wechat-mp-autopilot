"""⑦⑧⑨ 发布：摘要 → 草稿箱 →（auto 模式）提交发布 + 轮询。

安全闸门：
- AI 味检测标黄（flagged）时 auto 模式自动降级为只推草稿
- max_per_day 自我频控，超限停在草稿并提示
- 轮询超时不判失败，publish_id 落盘可事后 autopilot status 补查
"""

from __future__ import annotations

import datetime as dt
import json
import time

from ..config import PROJECT_ROOT, Config
from ..llm import LLM
from ..wechat.client import WechatClient, parse_publish_result
from .common import load_stage_instructions


def run_publish(
    cfg: Config,
    wechat: WechatClient,
    llm: LLM,
    *,
    html: str,
    title: str,
    article_text: str,
    cover_media_id: str | None,
    humanize_report: dict,
    usage_summary: dict,
    prompt_versions: dict,
) -> dict:
    digest, digest_version = _make_digest(cfg, llm, article_text)
    prompt_versions = {**prompt_versions, "digest": digest_version}

    article = {
        "title": title,
        "digest": digest,
        "content": html,
        "thumb_media_id": cover_media_id or "",
        "need_open_comment": 1 if cfg.open_comment else 0,
        "only_fans_can_comment": 1 if cfg.only_fans_comment else 0,
    }
    media_id = wechat.add_draft([article])
    result = {
        "media_id": media_id,
        "title": title,
        "digest": digest,
        "has_cover": bool(cover_media_id),
        "mode": cfg.publish_mode,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "prompt_versions": prompt_versions,
        "usage": usage_summary,
    }

    if cfg.publish_mode == "draft":
        result["next_step"] = (
            "人工到公众号后台草稿箱确认发布（附A SOP）；发布后建议手动群发一次触达关注者（发布≠群发，订阅号每天 1 次）"
        )
        return result

    # ── auto 模式的三道闸门 ──────────────────────────────
    if humanize_report.get("flagged"):
        result["publish_skipped"] = "ai_flavor_flagged"
        result["next_step"] = (
            f"AI 味指数 {humanize_report['after']['score']} 仍超阈值，已停在草稿箱；"
            "人工过目后可在后台发布，或调整后 --from humanize 重跑。"
        )
        return result

    if _published_today() >= cfg.max_per_day:
        result["publish_skipped"] = "max_per_day_reached"
        result["next_step"] = f"今日已自动发布 {_published_today()} 篇，达到 max_per_day={cfg.max_per_day} 上限。"
        return result

    publish_id = wechat.freepublish_submit(media_id)
    result["publish_id"] = publish_id
    final = _poll(wechat, publish_id, cfg.poll_interval_sec, cfg.poll_timeout_min * 60)
    result.update(final)
    if final["status"] == 0:
        result["next_step"] = f"已发布：{final['article_urls'][0] if final['article_urls'] else final['article_id']}"
    elif final["status"] is None:
        result["next_step"] = "轮询超时（不等于失败），稍后用 `autopilot status --run <目录>` 补查。"
    else:
        result["next_step"] = f"发布未成功：{final['status_text']}；草稿仍在草稿箱，可人工处理。"
    return result


def _make_digest(cfg: Config, llm: LLM, article_text: str) -> tuple[str, str]:
    system, prov = load_stage_instructions("digest")
    digest = llm.chat(system, article_text[:2000]).strip().strip('"“”')
    limit = 110 if cfg.ai_disclosure else 120
    digest = digest[:limit]
    if cfg.ai_disclosure:
        digest += "｜AI 辅助创作"
    return digest, prov["label"]


def _poll(wechat: WechatClient, publish_id: str, interval_sec: int, timeout_sec: int):
    """轮询直至终态或超时；超时返回 status=None（不判失败）。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        final = parse_publish_result(wechat.freepublish_get(publish_id))
        if final["status"] != 1:
            final["polled_at"] = dt.datetime.now().isoformat(timespec="seconds")
            return final
        time.sleep(max(interval_sec, 3))
    return {
        "status": None,
        "status_text": "轮询超时（发布可能仍在进行）",
        "article_urls": [],
        "polled_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _published_today() -> int:
    """扫描 runs/ 里今天的成功发布记录（自我频控依据）。"""
    runs_root = PROJECT_ROOT / "runs"
    if not runs_root.is_dir():
        return 0
    today = dt.date.today().isoformat()
    count = 0
    for path in runs_root.glob(f"{today}-*/08_publish_result.json"):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("status") == 0:
                count += 1
        except (OSError, json.JSONDecodeError):
            continue
    return count
