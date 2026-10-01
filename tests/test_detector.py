"""AI 味检测器测试：人味文本低分、八股文本高分。"""

from autopilot.detector import THRESHOLD, detect, summarize_hits

HUMAN_TEXT = """上周帮一个朋友排查慢查询，日志里翻到一条 SQL，我盯着它看了十秒。
索引建了四个，全没用上。问题不在数据库，在写这条 SQL 的人没搞清楚一件事：过滤条件该放在哪一层。
我让他把三行代码发我。看完就明白了，教科书害人。
他后来跟我说，改完之后查询从 8 秒掉到 0.2 秒。我说不是我厉害，是你之前压根没看执行计划。
这种事见多了。工具没问题，问题总在人。"""

AI_TEXT = """首先，随着人工智能的快速发展，编程工具正在被深度赋能。
其次，值得注意的是，开发者生态的闭环建设至关重要，这是一个不可或缺的抓手。
不难发现，业内人士表示，AI 不是简单的效率工具，而是开发者能力的延伸，与其说是工具，不如说是伙伴。
综上所述，AI 编程工具的未来可期，让我们拭目以待。在当今时代，深耕这一领域将极大地提升效率。
一方面，工具可以提升效率；另一方面，工具也可以赋能开发者。最后，AI 工具的重要性不言而喻。"""


def test_human_text_scores_low():
    report = detect(HUMAN_TEXT)
    assert report["score"] < THRESHOLD


def test_ai_text_scores_high():
    report = detect(AI_TEXT)
    assert report["score"] >= THRESHOLD
    rules = {hit["rule"] for hit in report["hits"]}
    assert any("八股" in r for r in rules)
    assert report["sentence_stats"]["count"] > 0


def test_empty_text():
    assert detect("").get("score") == 0
    assert detect("   \n ").get("score") == 0


def test_score_clamped_to_100():
    text = "赋能。赋能。赋能。综上所述！未来可期！首先其次最后！" * 30
    assert 0 <= detect(text)["score"] <= 100


def test_summarize_hits_formats():
    report = detect(AI_TEXT)
    summary = summarize_hits(report)
    assert summary.startswith("-") or summary == "未检出明显模式。"
