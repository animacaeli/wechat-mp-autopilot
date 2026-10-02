"""③ 去 AI 味：LLM 重写 pass + 规则检测器双保险。

流程：检测初稿 → 按 prompt 重写 → 复检 → 仍超标则二次重写 → 复检。
最终仍超标的标黄（flagged）：人工审核重点看；auto 发布模式自动降级为只推草稿。
"""

from __future__ import annotations

from ..config import Config
from ..detector import THRESHOLD, detect, summarize_hits
from ..llm import LLM
from .common import load_stage_instructions, strip_fence


def run_humanizer(cfg: Config, llm: LLM, draft: str) -> tuple[str, dict]:
    system, prov = load_stage_instructions("humanize")
    report_before = detect(draft)

    text = _rewrite(llm, system, draft, report_before)
    report_after = detect(text)
    passes = 1

    if report_after["score"] >= THRESHOLD:
        text = _rewrite(llm, system, text, report_after)
        report_after = detect(text)
        passes = 2

    report = {
        "threshold": THRESHOLD,
        "before": report_before,
        "after": report_after,
        "passes": passes,
        "flagged": report_after["score"] >= THRESHOLD,
        "prompt_version": prov["label"],
    }
    return text, report


def _rewrite(llm: LLM, system: str, text: str, report: dict) -> str:
    user = (
        f"【机器检测报告】AI 味指数 {report['score']}/100（越低越好）\n"
        f"{summarize_hits(report)}\n\n"
        f"【原文】\n{text}\n\n"
        "请按系统指令重写全文：保留全部事实与观点、篇幅相当，只改掉 AI 味。直接输出重写后的全文。"
    )
    return strip_fence(llm.chat(system, user))
