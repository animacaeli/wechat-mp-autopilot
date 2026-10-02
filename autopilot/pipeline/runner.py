"""流水线编排：七阶段顺序执行，产物依次落盘，支持 --from 断点重跑。

run 目录：runs/YYYY-MM-DD-slug/，产物编号见 docs/plan.md §5.2。
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PROJECT_ROOT, Config
from ..llm import LLM, UsageTracker
from ..wechat.client import WechatClient
from .common import load_json, save_json

STAGES = ["topics", "writer", "humanize", "titlist", "render", "images", "publish"]

ARTIFACTS = {
    "topics": "01_topics.json",
    "writer": "02_draft.md",
    "humanize": "03_humanized.md",
    "titlist": "04_titles.json",
    "render": "05_blocks.json",
    "images": "06_meta.json",
    "publish": "07_draft_result.json",
}


@dataclass
class RunOptions:
    direction: str = ""
    topic_only: bool = False
    pick: int | None = None
    from_stage: str | None = None
    resume_dir: Path | None = None


@dataclass
class RunState:
    cfg: Config
    run_dir: Path
    usage: UsageTracker = field(default_factory=UsageTracker)
    prompt_versions: dict[str, str] = field(default_factory=dict)

    def track(self, stage: str, llm: LLM) -> None:
        self.usage.record(stage, llm)

    def artifact(self, stage: str) -> Path:
        return self.run_dir / ARTIFACTS[stage]


def execute(cfg: Config, opts: RunOptions) -> Path:
    if opts.from_stage and opts.from_stage not in STAGES:
        raise SystemExit(f"未知阶段 --from {opts.from_stage}；可用：{' / '.join(STAGES)}")

    from_index = STAGES.index(opts.from_stage) if opts.from_stage else 0

    # ── ① 选题（决定 run 目录名）─────────────────────────
    if from_index == 0:
        if not opts.direction:
            raise SystemExit("请用 --direction 提供本次选题方向（或写入 config 的 niche.directions）。")
        from ..pipeline import topics as topics_mod

        llm = LLM(cfg, "topics")
        topics_result = topics_mod.run_topics(cfg, llm, opts.direction, opts.pick)
        if opts.from_stage == "topics":
            # --from topics --resume <dir>：重跑选题写回同一目录
            state = RunState(cfg, _require_resume_dir(opts))
        else:
            state = RunState(cfg, _new_run_dir(topics_result["picked"]["title_direction"]))
        state.prompt_versions["topics"] = topics_result["prompt_version"]
        save_json(state.artifact("topics"), topics_result)
        state.track("topics", llm)
        if opts.topic_only:
            print(f"[1/{len(STAGES)}] 选题完成（--topic-only 模式）：{state.run_dir}")
            return state.run_dir
    else:
        state = RunState(cfg, opts.resume_dir or _require_resume_dir(opts))
        topics_result = load_json(state.artifact("topics"))

    picked = topics_result["picked"]
    print(f"选题：{picked['title_direction']}（{topics_result['picked_reason']}）")

    # ── ② 写作 ───────────────────────────────────────────
    if from_index <= 1:
        from ..pipeline import writer as writer_mod

        llm = LLM(cfg, "writer")
        draft, version = writer_mod.run_writer(cfg, llm, picked)
        state.prompt_versions["writer"] = version
        state.artifact("writer").write_text(draft, encoding="utf-8")
        state.track("writer", llm)
        print(f"[2/7] 初稿完成：{len(draft)} 字")
    else:
        draft = state.artifact("writer").read_text(encoding="utf-8")

    # ── ③ 去AI味 ─────────────────────────────────────────
    if from_index <= 2:
        from ..pipeline import humanizer as humanizer_mod

        llm = LLM(cfg, "humanizer")
        humanized, report = humanizer_mod.run_humanizer(cfg, llm, draft)
        state.prompt_versions["humanize"] = report["prompt_version"]
        state.artifact("humanize").write_text(humanized, encoding="utf-8")
        save_json(state.run_dir / "03_report.json", report)
        state.track("humanizer", llm)
        flag = "⚠ 标黄（人工重点审）" if report["flagged"] else "通过"
        print(f"[3/7] 去AI味：指数 {report['before']['score']} → {report['after']['score']}（{flag}）")
    else:
        humanized = state.artifact("humanize").read_text(encoding="utf-8")
        report = load_json(state.run_dir / "03_report.json")

    # ── ④ 标题 ───────────────────────────────────────────
    if from_index <= 3:
        from ..pipeline import titlist as titlist_mod

        llm = LLM(cfg, "titlist")
        titles = titlist_mod.run_titlist(cfg, llm, humanized)
        state.prompt_versions["titlist"] = titles["prompt_version"]
        save_json(state.artifact("titlist"), titles)
        state.track("titlist", llm)
        print(f"[4/7] 标题：{titles['picked']['title']}")
    else:
        titles = load_json(state.artifact("titlist"))
    title = titles["picked"]["title"]

    # ── ⑤ 排版渲染 ───────────────────────────────────────
    if from_index <= 4:
        from ..pipeline import renderer as renderer_mod

        blocks = renderer_mod.render_blocks(humanized, cfg.style_template)
        save_json(state.artifact("render"), {"template": cfg.style_template, "blocks": blocks})
        print(f"[5/7] 排版：{len(blocks)} 个内容块（{cfg.style_template} 模板）")
    else:
        blocks = load_json(state.artifact("render"))["blocks"]

    # ── ⑥ 配图 ───────────────────────────────────────────
    if from_index <= 5:
        from ..pipeline import images as images_mod

        wechat = WechatClient(cfg.app_id, cfg.app_secret)
        images_llm = LLM(cfg)
        html, meta = images_mod.run_images(cfg, wechat, images_llm, list(blocks), title)
        state.track("images", images_llm)
        (state.run_dir / "05_article.html").write_text(html, encoding="utf-8")
        save_json(state.artifact("images"), meta)
        cover_info = (
            "封面 + 正文图"
            if meta.get("body_images")
            else "仅封面"
            if meta.get("cover_media_id")
            else "无封面（草稿推送可能被微信拒绝）"
        )
        if meta.get("fallback_used"):
            cover_info += f"，图库降级：{meta.get('fallback_reason', '')[:60]}"
        print(f"[6/7] 配图：{cover_info}")
    else:
        meta = load_json(state.artifact("images"))
        html = (state.run_dir / "05_article.html").read_text(encoding="utf-8")

    # ── ⑦ 草稿 +（auto）发布 ─────────────────────────────
    from ..pipeline import publisher as publisher_mod

    wechat = WechatClient(cfg.app_id, cfg.app_secret)
    digest_llm = LLM(cfg, "digest")
    result = publisher_mod.run_publish(
        cfg,
        wechat,
        digest_llm,
        html=html,
        title=title,
        article_text=humanized,
        cover_media_id=meta.get("cover_media_id"),
        humanize_report=report,
        usage_summary=state.usage.summary(),
        prompt_versions=dict(state.prompt_versions),
    )
    state.track("digest", digest_llm)
    save_json(state.artifact("publish"), result)
    if "publish_id" in result:
        save_json(
            state.run_dir / "08_publish_result.json",
            {
                k: v
                for k, v in result.items()
                if k in ("publish_id", "status", "status_text", "article_id", "article_urls", "polled_at", "next_step")
            },
        )
    print(f"[7/7] {'已发布' if result.get('status') == 0 else '已推入草稿箱'}（media_id={result['media_id']}）")
    if result.get("publish_skipped"):
        print(f"      自动发布未执行：{result['next_step']}")
    elif cfg.publish_mode == "draft":
        print(f"      下一步：{result['next_step']}")
    print(f"产物目录：{state.run_dir}")
    return state.run_dir


def _slugify(text: str, limit: int = 24) -> str:
    keep = re.sub(r"[^\w\u4e00-\u9fff-]+", "", text).strip("-")
    return keep[:limit] or "untitled"


def _new_run_dir(topic_title: str) -> Path:
    base = PROJECT_ROOT / "runs"
    base.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    run_dir = base / f"{today}-{_slugify(topic_title)}"
    n = 2
    while run_dir.exists():
        run_dir = base / f"{today}-{_slugify(topic_title)}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    return run_dir


def _require_resume_dir(opts: RunOptions) -> Path:
    if opts.resume_dir is None:
        raise SystemExit("--from 需要配合 --resume <run目录> 指定要续跑的产物目录。")
    if not opts.resume_dir.is_dir():
        raise SystemExit(f"run 目录不存在：{opts.resume_dir}")
    return opts.resume_dir
