"""① 选题：账号定位 + 方向 → 3 个候选（打分）→ 取最高分或人工指定。"""

from __future__ import annotations

from ..config import Config
from ..llm import LLM, LLMError
from .common import load_prompt

# LLM 偶尔会用中文键名，这里做一层别名归一
_ALIASES = {
    "title_direction": ["title_direction", "标题方向", "topic", "选题"],
    "angle": ["angle", "切入点", "cut_in"],
    "target_reader": ["target_reader", "目标读者", "audience"],
    "click_reason": ["click_reason", "预估点击理由", "reason"],
    "risk": ["risk", "内容风险", "risk_note"],
    "score": ["score", "评分"],
}


def _normalize(candidate: dict) -> dict | None:
    out = {}
    for key, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in candidate:
                out[key] = candidate[alias]
                break
    if not out.get("title_direction"):
        return None
    try:
        out["score"] = float(out.get("score", 0))
    except (TypeError, ValueError):
        out["score"] = 0.0
    return out


def run_topics(cfg: Config, llm: LLM, direction: str, pick: int | None = None) -> dict:
    system, version = load_prompt("topic.selector.md")
    pool = "、".join(cfg.directions) if cfg.directions else "（无常备方向，以本次输入为准）"
    user = (
        f"【账号定位】\n领域：{cfg.niche_field}\n读者：{cfg.audience}\n"
        f"人设：{cfg.persona or '（未设置）'}\n常备方向池：{pool}\n\n"
        f"【本次选题方向】\n{direction}"
    )
    data = llm.chat_json(system, user)
    raw = data.get("candidates") or data.get("topics") or []
    candidates = [c for c in (_normalize(x) for x in raw if isinstance(x, dict)) if c]
    if not candidates:
        raise LLMError("选题结果为空或字段无法识别，请重跑（可先 autopilot run --topic-only 排查）。")

    if pick is not None:
        idx = min(max(pick - 1, 0), len(candidates) - 1)
        reason = f"人工指定第 {idx + 1} 个"
    else:
        idx = max(range(len(candidates)), key=lambda i: candidates[i]["score"])
        reason = "自动取评分最高"
    picked = candidates[idx]
    return {"candidates": candidates, "picked": picked, "picked_reason": reason, "prompt_version": version}
