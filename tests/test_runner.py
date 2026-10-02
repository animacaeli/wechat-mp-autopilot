"""端到端编排测试：mock LLM 与微信 client，真实执行 runner 七阶段。

覆盖：产物落盘编号、断点重跑（--from）、auto 模式发布路径与 08 产物。
渲染/检测等纯逻辑走真实实现。
"""

import shutil

import pytest

from autopilot.config import PROJECT_ROOT, load_config

MARKDOWN = """上周帮朋友排查慢查询，日志里翻到一条 SQL，盯着看了十秒。
索引建了四个，全没用上。问题不在数据库，在写 SQL 的人。

## 问题出在哪

执行计划没看过。教科书害人。

```python
print("hello")
```

改完之后，查询从 8 秒掉到 0.2 秒。不是玄学，是基本功。

## 一点感受

工具没问题，问题总在人。
"""


class FakeLLM:
    usage_tokens = 100

    def __init__(self, cfg, stage=None):
        self.stage = stage or ""

    def chat(self, system, user, **kw):
        if self.stage == "writer":
            return MARKDOWN
        if self.stage == "humanizer":
            return MARKDOWN
        if self.stage == "digest":
            return "一篇讲慢查询排查的实战复盘，两分钟读完。"
        return "technology code"  # images 环节的英文关键词

    def chat_json(self, system, user):
        if self.stage == "topics":
            return {
                "candidates": [
                    {
                        "title_direction": "一次慢查询排查复盘",
                        "angle": "从执行计划说起",
                        "target_reader": "后端开发者",
                        "click_reason": "痛点共鸣",
                        "risk": "无",
                        "score": 9,
                    },
                    {
                        "title_direction": "数据库索引避坑",
                        "angle": "索引失效场景",
                        "target_reader": "全栈",
                        "click_reason": "干货清单",
                        "risk": "无",
                        "score": 7,
                    },
                ]
            }
        if self.stage == "titlist":
            return {
                "candidates": [
                    {"title": "查询从8秒到0.2秒，我只改了一行代码", "type": "数字", "hook": "反差", "score": 9},
                    {"title": "索引建了四个全没用上，问题出在这", "type": "痛点", "hook": "痛点", "score": 8},
                ]
            }
        if self.stage == "":  # images 环节：gen 封面的美术指导调用
            return {"pattern": "waves", "palette": ["#24344d", "#4d6a8f", "#aebfd6"], "mood": "沉稳科技"}
        raise AssertionError(f"unexpected stage {self.stage}")


class FakeWechat:
    last_article = None

    def __init__(self, app_id, app_secret, http=None):
        pass

    def add_material(self, path, material_type="thumb"):
        return "THUMB_MEDIA_1"

    def upload_content_image(self, path):
        return "https://mmbiz.qpic.cn/mmbiz_jpg/fake/body.jpg"

    def add_draft(self, articles):
        assert articles[0]["thumb_media_id"] == "THUMB_MEDIA_1"
        FakeWechat.last_article = articles[0]
        return "DRAFT_MEDIA_1"

    def freepublish_submit(self, draft_id):
        return "PUBLISH_1"

    def freepublish_get(self, publish_id):
        return {
            "publish_id": publish_id,
            "publish_status": 0,
            "article_id": "ART_1",
            "article_detail": {"count": 1, "item": [{"article_url": "https://mp.weixin.qq.com/s/ok"}]},
        }


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """临时项目根：拷贝 prompts/templates，PATCH 各模块的 PROJECT_ROOT 绑定。"""
    monkeypatch.setenv("WECHAT_APP_ID", "wx-test")
    monkeypatch.setenv("WECHAT_APP_SECRET", "secret-test")
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-test")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    shutil.copytree(PROJECT_ROOT / "prompts", tmp_path / "prompts")
    shutil.copytree(PROJECT_ROOT / "templates", tmp_path / "templates")
    from autopilot.pipeline import common, images, publisher, renderer, runner

    for mod in (common, publisher, renderer, runner):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "LLM", FakeLLM)
    monkeypatch.setattr(runner, "WechatClient", FakeWechat)
    monkeypatch.setattr(publisher, "WechatClient", FakeWechat)
    monkeypatch.setattr(images, "WechatClient", FakeWechat)

    # 免依赖外网：_fetch_photo 返回本地生成的真实 JPEG
    from PIL import Image

    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (1200, 800), (120, 140, 160)).save(photo, "JPEG")
    monkeypatch.setattr(
        images, "_fetch_photo", lambda cfg, kw, exclude_url=None: (photo, "https://images.pexels.com/1.jpeg")
    )
    return tmp_path


def _make_cfg(tmp_path, mode="auto", provider=None):
    import re

    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    text = text.replace('type = "personal"', 'type = "enterprise"').replace('mode = "draft"', f'mode = "{mode}"')
    if provider:
        text = re.sub(r"(?m)^(provider\s*=).*$", rf'\1 "{provider}"', text)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(text, encoding="utf-8")
    return load_config(cfg_file)


def _run(tmp_path, cfg, **kw):
    from autopilot.pipeline.runner import RunOptions, execute

    return execute(cfg, RunOptions(direction="数据库性能", **kw))


def test_full_run_auto_publish(sandbox, capsys):
    cfg = _make_cfg(sandbox, mode="auto", provider="openverse")
    run_dir = _run(sandbox, cfg)
    out = capsys.readouterr().out

    for name in (
        "01_topics.json",
        "02_draft.md",
        "03_humanized.md",
        "03_report.json",
        "04_titles.json",
        "05_article.html",
        "06_meta.json",
        "07_draft_result.json",
        "08_publish_result.json",
    ):
        assert (run_dir / name).is_file(), f"缺产物 {name}"

    html = (run_dir / "05_article.html").read_text(encoding="utf-8")
    assert "mmbiz.qpic.cn" in html and "style=" in html

    import json

    draft = json.loads((run_dir / "07_draft_result.json").read_text(encoding="utf-8"))
    assert draft["media_id"] == "DRAFT_MEDIA_1"
    assert draft["mode"] == "auto"
    assert "AI 辅助创作" in draft["digest"]

    publish = json.loads((run_dir / "08_publish_result.json").read_text(encoding="utf-8"))
    assert publish["status"] == 0
    assert publish["article_urls"] == ["https://mp.weixin.qq.com/s/ok"]
    assert "已发布" in out


def test_full_run_draft_mode(sandbox):
    cfg = _make_cfg(sandbox, mode="draft")
    run_dir = _run(sandbox, cfg)
    assert not (run_dir / "08_publish_result.json").exists()
    import json

    draft = json.loads((run_dir / "07_draft_result.json").read_text(encoding="utf-8"))
    assert "publish_skipped" not in draft
    assert "人工" in draft["next_step"]


def test_resume_from_titlist_reuses_upstream(sandbox):
    cfg = _make_cfg(sandbox, mode="draft")
    run_dir = _run(sandbox, cfg)
    before = (run_dir / "01_topics.json").read_text(encoding="utf-8")
    draft_before = (run_dir / "02_draft.md").read_text(encoding="utf-8")

    _run(sandbox, cfg, from_stage="titlist", resume_dir=run_dir)

    assert (run_dir / "01_topics.json").read_text(encoding="utf-8") == before
    assert (run_dir / "02_draft.md").read_text(encoding="utf-8") == draft_before


def test_resume_from_topics_reuses_same_dir(sandbox):
    """--from topics --resume 必须写回同一目录，而不是新建 run 目录。"""
    cfg = _make_cfg(sandbox, mode="draft")
    run_dir = _run(sandbox, cfg)
    again = _run(sandbox, cfg, from_stage="topics", resume_dir=run_dir)
    assert again == run_dir


def test_cover_fallback_when_gallery_dead(sandbox, monkeypatch):
    """远程图库全挂时本地生成渐变封面兜底，thumb_media_id 不允许为空。"""
    from autopilot.pipeline import images

    monkeypatch.setattr(images, "_fetch_photo", lambda cfg, kw, exclude_url=None: (None, None))
    cfg = _make_cfg(sandbox, mode="draft", provider="openverse")
    run_dir = _run(sandbox, cfg)

    import json

    meta = json.loads((run_dir / "06_meta.json").read_text(encoding="utf-8"))
    assert meta["fallback_used"] is True
    assert meta["cover_source"] == "local_fallback"
    assert meta["cover_media_id"] == "THUMB_MEDIA_1"  # 兜底封面也走素材上传
    draft = json.loads((run_dir / "07_draft_result.json").read_text(encoding="utf-8"))
    assert draft["has_cover"] is True


def test_provider_gen_ai_cover(sandbox):
    """默认 gen provider：LLM 设计稿 → 程序化渲染 → 照常上传素材 + 小节装饰条。"""
    cfg = _make_cfg(sandbox, mode="draft", provider="gen")
    run_dir = _run(sandbox, cfg)

    import json

    meta = json.loads((run_dir / "06_meta.json").read_text(encoding="utf-8"))
    assert meta["cover_source"] == "ai_generated"
    assert meta["cover_design"]["pattern"] == "waves"
    assert meta["cover_media_id"] == "THUMB_MEDIA_1"
    # FakeWriter 的 MARKDOWN 有 2 个 ## 小节 → 2 张装饰条
    assert len(meta["body_images"]) == 2
    html = (run_dir / "05_article.html").read_text(encoding="utf-8")
    assert html.count("mmbiz.qpic.cn") == 2
    draft = json.loads((run_dir / "07_draft_result.json").read_text(encoding="utf-8"))
    assert draft["has_cover"] is True


def test_ensure_headings_inserted_when_missing(sandbox):
    """写作产物无 ## 标题时，ensure_headings 补意象式小节；已有 ## 时不动。"""
    from autopilot.pipeline import renderer

    class HeadingLLM:
        usage_tokens = 0

        def chat(self, system, user):
            return "## 深夜的路灯\n" + user

    text = "一段没有任何标题的正文。" * 10
    out, inserted = renderer.ensure_headings(text, HeadingLLM())
    assert inserted is True
    assert out.startswith("## 深夜的路灯")
    assert "一段没有任何标题的正文。" in out  # 原文保留

    out2, inserted2 = renderer.ensure_headings("## 已有\n正文", HeadingLLM())
    assert inserted2 is False
    assert out2 == "## 已有\n正文"


def test_provider_local_never_touches_network(sandbox, monkeypatch):
    """provider=local：全程不访问图库网络，封面由本地渐变生成。"""
    from autopilot.pipeline import images

    def _boom(*args, **kwargs):
        raise AssertionError("provider=local 不应访问图库")

    monkeypatch.setattr(images, "_fetch_photo", _boom)
    cfg = _make_cfg(sandbox, mode="draft", provider="local")
    run_dir = _run(sandbox, cfg)

    import json

    meta = json.loads((run_dir / "06_meta.json").read_text(encoding="utf-8"))
    assert meta["cover_source"] == "local"
    assert meta["cover_media_id"] == "THUMB_MEDIA_1"
    assert meta["body_images"] == []


def test_fetch_photo_dispatch_by_provider(tmp_path, monkeypatch):
    """不走 sandbox fixture（它会整体替换 _fetch_photo），单独验证真实分发逻辑。"""
    from autopilot.pipeline import images

    calls = []
    monkeypatch.setattr(
        images, "_fetch_pexels", lambda cfg, kw, exclude_url=None: calls.append("pexels") or (None, None)
    )
    monkeypatch.setattr(
        images, "_fetch_pixabay", lambda cfg, kw, exclude_url=None: calls.append("pixabay") or (None, None)
    )
    monkeypatch.setattr(
        images, "_fetch_openverse", lambda kw, exclude_url=None: calls.append("openverse") or (None, None)
    )

    for provider in ("pexels", "pixabay", "openverse"):
        cfg = _make_cfg(tmp_path, provider=provider)
        assert images._fetch_photo(cfg, "kw") == (None, None)
    assert calls == ["pexels", "pixabay", "openverse"]
