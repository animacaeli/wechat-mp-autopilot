"""② 写作：按风格预设的长文写作，产物为 markdown 初稿。"""

from __future__ import annotations

from ..config import Config
from ..llm import LLM
from .common import load_stage_instructions, strip_fence


def run_writer(cfg: Config, llm: LLM, topic: dict) -> tuple[str, str]:
    """返回 (初稿 markdown, 指令来源标签)。"""
    system, prov = load_stage_instructions("writer", cfg.style_preset)
    user = (
        f"【账号定位】领域：{cfg.niche_field}｜读者：{cfg.audience}\n"
        f"【选题】{topic.get('title_direction', '')}\n"
        f"【切入点】{topic.get('angle', '')}\n"
        f"【写给谁】{topic.get('target_reader', cfg.audience)}\n"
        f"【点击理由（写作时要兑现）】{topic.get('click_reason', '')}\n"
        f"【内容风险（写作时要规避）】{topic.get('risk', '无')}\n\n"
        "请输出完整文章正文（markdown，不要标题中的序号前缀，第一行就是引子段落）。"
    )
    draft = llm.chat(system, user)
    return strip_fence(draft), prov["label"]
