"""④ 标题：5 种套路 × 2 = 10 个候选，打分取 top1，备选存档供人工换用。"""

from __future__ import annotations

from ..config import Config
from ..llm import LLM, LLMError
from .common import load_stage_instructions


def run_titlist(cfg: Config, llm: LLM, article_text: str) -> dict:
    system, prov = load_stage_instructions("titlist")
    outline = _outline(article_text)
    user = (
        f"【账号定位】领域：{cfg.niche_field}｜读者：{cfg.audience}\n\n"
        f"【文章概要】\n{outline}\n\n"
        "请生成 10 个标题候选并打分。"
    )
    data = llm.chat_json(system, user)
    candidates = [c for c in (data.get("candidates") or []) if isinstance(c, dict) and c.get("title")]
    for c in candidates:
        try:
            c["score"] = float(c.get("score", 0))
        except (TypeError, ValueError):
            c["score"] = 0.0
    if not candidates:
        raise LLMError("标题候选为空，请重跑 --from titlist。")

    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)
    return {
        "picked": ranked[0],
        "alternates": ranked[1:4],
        "prompt_version": prov["label"],
    }


def _outline(text: str, limit: int = 800) -> str:
    """正文太长会稀释标题生成的注意力，取开头 + 各小标题做概要。"""
    headings = [line for line in text.splitlines() if line.strip().startswith("#")]
    head = text[:limit]
    if headings:
        return head + "\n\n【小标题结构】\n" + "\n".join(headings)
    return head
