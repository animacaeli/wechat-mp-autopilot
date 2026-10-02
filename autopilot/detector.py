"""AI 味规则检测器（纯 Python，不调 LLM）。

输出 0~100 的「AI 味指数」+ 命中明细。指数用于：
- 超阈值自动触发二次重写
- 仍超标则标黄，人工审核重点看；auto 发布模式下自动降级为只推草稿
"""

from __future__ import annotations

import re
import statistics

# 默认阈值：>= 此值视为超标（触发二次重写 / 标黄）
THRESHOLD = 40

BLACK_WORDS = [
    "赋能",
    "闭环",
    "抓手",
    "深耕",
    "破圈",
    "生态",
    "发力",
    "落地",
    "不难发现",
    "值得注意的是",
    "综上所述",
    "总而言之",
    "众所周知",
    "在当今",
    "的今天",
    "随着…的发展",
    "业内人士",
    "有观点认为",
    "有分析认为",
    "研究表明",
    "事实证明",
    "毫无疑问",
    "未来可期",
    "让我们拭目以待",
    "任重道远",
    "行稳致远",
    "砥砺前行",
    "至关重要",
    "不可或缺",
    "极大地",
]

STRUCTURE_WORDS = ["首先", "其次", "再次", "最后", "一方面", "另一方面", "与此同时"]

ENDING_CLICHES = ["未来可期", "拭目以待", "让我们", "共勉", "与君共勉", "路漫漫"]


def detect(text: str) -> dict:
    """返回 {score, hits, sentence_stats}。score ∈ [0,100]。"""
    if not text.strip():
        return {"score": 0, "hits": [], "sentence_stats": {}}

    n_chars = max(len(text), 1)
    hits: list[dict] = []
    score = 0.0

    def per_1000(count: int) -> float:
        return count * 1000 / n_chars

    # 1. 黑词表：每命中 6 分，上限 30
    black_hits = [(w, text.count(w)) for w in BLACK_WORDS if w in text]
    if black_hits:
        total = sum(c for _, c in black_hits)
        score += min(6 * total, 30)
        hits.append(
            {
                "rule": "八股词汇",
                "count": total,
                "samples": [w for w, c in black_hits for _ in range(min(c, 1))][:8],
            }
        )

    # 2. 结构八股（首先/其次/最后…）：每个 8 分，上限 24
    struct_hits = [(w, text.count(w)) for w in STRUCTURE_WORDS if w in text]
    if struct_hits:
        total = sum(c for _, c in struct_hits)
        score += min(8 * total, 24)
        hits.append({"rule": "公式化结构词", "count": total, "samples": [w for w, _ in struct_hits][:6]})

    # 3. 「不是X，而是Y」句式：每个 7 分，上限 21
    contrast = re.findall(r"不是[^，。；！？]{1,15}，而是", text)
    if contrast:
        score += min(7 * len(contrast), 21)
        hits.append({"rule": "「不是X，而是Y」句式", "count": len(contrast), "samples": contrast[:3]})

    # 4. 破折号密度：>1 处/千字后每 +1 扣 5 分，上限 15
    dashes = text.count("——")
    if per_1000(dashes) > 1:
        score += min(5 * (per_1000(dashes) - 1), 15)
        hits.append({"rule": "破折号插语密度", "count": dashes, "samples": []})

    # 5. 感叹号：>2 个/千字扣分，上限 10
    excl = text.count("！") + text.count("!")
    if per_1000(excl) > 2:
        score += min(10, 3 * (per_1000(excl) - 2))
        hits.append({"rule": "感叹号密度", "count": excl, "samples": []})

    # 6. 句长均一：变异系数 < 0.3 视为机械节奏，扣 15
    sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]+", text) if s.strip()]
    lengths = [len(s) for s in sentences]
    sent_stats = {
        "count": len(lengths),
        "mean": round(statistics.mean(lengths), 1) if lengths else 0,
        "stdev": round(statistics.stdev(lengths), 1) if len(lengths) > 1 else 0.0,
    }
    if len(lengths) >= 5 and sent_stats["mean"] > 0:
        cv = sent_stats["stdev"] / sent_stats["mean"]
        if cv < 0.3:
            score += 15
            hits.append({"rule": "句长过于均一（缺少长短句节奏）", "count": len(lengths), "samples": []})

    # 7. 万能结尾：命中扣 10
    tail = text[-80:]
    ending = [w for w in ENDING_CLICHES if w in tail]
    if ending:
        score += 10
        hits.append({"rule": "万能收尾套路", "count": len(ending), "samples": ending})

    # 8. 空洞让步套娃（虽然…但…）
    concessions = re.findall(r"虽然[^。]{0,25}，?但", text)
    if len(concessions) >= 2:
        score += min(5 * len(concessions), 10)
        hits.append({"rule": "「虽然…但…」空洞让步", "count": len(concessions), "samples": concessions[:3]})

    return {
        "score": round(max(0, min(score, 100))),
        "hits": hits,
        "sentence_stats": sent_stats,
    }


def summarize_hits(report: dict) -> str:
    """把检测报告压成给 humanizer prompt 用的文本提示。"""
    if not report["hits"]:
        return "未检出明显模式。"
    lines = []
    for hit in report["hits"]:
        samples = f"（如：{'、'.join(hit['samples'][:3])}）" if hit["samples"] else ""
        lines.append(f"- {hit['rule']}：{hit['count']} 处{samples}")
    return "\n".join(lines)
