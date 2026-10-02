"""CLI 入口：init / verify / run / status / unpublish / stats。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import httpx

from . import __version__
from .config import (
    PROJECT_ROOT,
    Config,
    ConfigError,
    exit_on_config_error,
    load_config,
    load_dotenv,
)
from .llm import LLM, LLMError
from .pipeline.common import load_json, save_json
from .wechat.client import WechatClient, parse_publish_result
from .wechat.errors import WechatApiError

OK, BAD, WARN = "[✓]", "[✗]", "[!]"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autopilot",
        description="公众号 AI 自动化写作流水线：选题 → 写作 → 去AI味 → 标题 → 排版 → 配图"
        " → 草稿箱 →（企业号）自动发布",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化本地配置（复制模板并给出填写指引）")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在的本地配置")

    p_verify = sub.add_parser("verify", help="自检：配置校验 + 微信/模型连通性探测")
    p_verify.add_argument(
        "--with-publish",
        action="store_true",
        help="企业号全链路实测：发一篇测试草稿并提交发布，随后立即删除（约 1 分钟）",
    )

    p_run = sub.add_parser("run", help="跑完整流水线")
    p_run.add_argument("--direction", default="", help="本次选题方向（个人号必填，或写入 config 的 niche.directions）")
    p_run.add_argument("--topic-only", action="store_true", help="只跑选题，人工定方向后再写")
    p_run.add_argument("--pick", type=int, default=None, help="指定选择第几个候选选题（默认自动取最高分）")
    p_run.add_argument(
        "--publish", choices=["draft", "auto"], default=None, help="临时覆盖发布模式（联锁校验同样生效）"
    )
    p_run.add_argument("--resume", type=Path, default=None, help="续跑的 run 目录（配合 --from）")
    p_run.add_argument(
        "--from",
        dest="from_stage",
        metavar="STAGE",
        choices=["topics", "writer", "humanize", "titlist", "render", "images", "publish"],
        help="从指定阶段重跑（默认从头）",
    )

    p_status = sub.add_parser("status", help="补查 auto 发布的轮询状态")
    p_status.add_argument("--run", type=Path, required=True, help="run 目录")

    p_unpublish = sub.add_parser("unpublish", help="删除已自动发布的文章（回滚）")
    p_unpublish.add_argument("--run", type=Path, required=True, help="run 目录")

    p_stats = sub.add_parser("stats", help="人工补录阅读数据（发布后第 3/7 天）")
    p_stats.add_argument("--run", type=Path, required=True, help="run 目录")
    p_stats.add_argument("--day", type=int, default=3, choices=[3, 7], help="补录第几天（默认 3）")

    sub.add_parser("skills", help="查看各阶段能力来源（skill / 内置兜底 / 补充说明）")

    p_sched = sub.add_parser("schedule", help="常驻定时写作：每日定点自动产出（容器部署用，免宿主 cron）")
    p_sched.add_argument(
        "--daily", default="08:00", type=_arg_daily, metavar="HH:MM", help="每日触发时间（默认 08:00）"
    )
    p_sched.add_argument("--direction", default="", help="方向池为空时的固定选题方向（方向池非空时按日轮换，忽略此项）")
    p_sched.add_argument(
        "--publish", choices=["draft", "auto"], default=None, help="临时覆盖发布模式（联锁校验同样生效）"
    )

    return parser


def _arg_daily(value: str) -> tuple[int, int]:
    from .scheduler import parse_daily

    try:
        return parse_daily(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        {
            "init": cmd_init,
            "verify": cmd_verify,
            "run": cmd_run,
            "status": cmd_status,
            "unpublish": cmd_unpublish,
            "stats": cmd_stats,
            "skills": cmd_skills,
            "schedule": cmd_schedule,
        }[args.command](args)
    except ConfigError as err:
        print(f"{BAD} [配置错误] {err}", file=sys.stderr)
        raise SystemExit(2) from err
    except WechatApiError as err:
        print(f"{BAD} [微信接口] {err}", file=sys.stderr)
        raise SystemExit(1) from err
    except LLMError as err:
        print(f"{BAD} [模型调用] {err}", file=sys.stderr)
        raise SystemExit(1) from err
    except httpx.HTTPError as err:
        print(f"{BAD} [网络错误] 无法访问微信/模型服务：{err}", file=sys.stderr)
        raise SystemExit(1) from err


# ── init ────────────────────────────────────────────────
def cmd_init(args) -> None:
    cfg_path = PROJECT_ROOT / "config.toml"
    env_path = PROJECT_ROOT / ".env"
    if cfg_path.exists() and not args.force:
        print(f"{WARN} config.toml 已存在（--force 可覆盖）")
    else:
        shutil.copyfile(PROJECT_ROOT / "config.example.toml", cfg_path)
        print(f"{OK} 已生成 {cfg_path}")
    if env_path.exists() and not args.force:
        print(f"{WARN} .env 已存在（--force 可覆盖）")
    else:
        shutil.copyfile(PROJECT_ROOT / ".env.example", env_path)
        print(f"{OK} 已生成 {env_path}")
    print(
        "\n接下来三步：\n"
        "  1. 配置密钥（二选一，都配时环境变量优先）：\n"
        "     a. 直接编辑 config.toml 填 app_id / app_secret / [llm].api_key —— 单文件即可跑\n"
        "     b. 或编辑 .env 填 WECHAT_APP_ID / WECHAT_APP_SECRET / LLM_API_KEY（推荐服务器/容器部署）\n"
        "  2. 编辑 config.toml：账号类型 [account].type、定位 [niche]、风格 [style]\n"
        '     （企业认证号想全自动发布：type="enterprise" + [publish].mode="auto"）\n'
        '  3. 跑 `autopilot verify` 自检，全绿后 `autopilot run --direction "…"`\n'
        "注意：公众号后台「设置与开发→基本配置→IP 白名单」需加入本机/服务器出口 IP，否则 token 获取会报 40164。"
    )


# ── verify ──────────────────────────────────────────────
@exit_on_config_error
def cmd_verify(args) -> None:
    load_dotenv()
    cfg = load_config()
    print(
        f"{OK} 配置加载通过：账号类型={cfg.account_type}，发布模式={cfg.publish_mode}，"
        f"模型={cfg.llm.model} @ {cfg.llm.base_url}"
    )
    failures = sum(
        [
            _check_env(cfg),
            _check_wechat(cfg),
            _check_freepublish(cfg, with_publish=args.with_publish),
            _check_llm(cfg),
        ]
    )
    if failures:
        print(f"\n{BAD} 自检完成：{failures} 项未通过，按上面指引修复后重试。")
        raise SystemExit(1)
    print('\n自检完成，全部通过。即可 `autopilot run --direction "…"` 跑全流程。')


def _check_env(cfg: Config) -> int:
    checks = [
        ("微信 AppID", lambda: cfg.app_id),
        ("微信 AppSecret", lambda: cfg.app_secret),
        ("模型 API key", lambda: cfg.resolve_llm_key(cfg.llm)),
    ]
    if cfg.image_provider == "pexels":
        checks.append(("Pexels key", lambda: cfg.pexels_api_key))
    elif cfg.image_provider == "pixabay":
        checks.append(("Pixabay key", lambda: cfg.pixabay_api_key))
    failed = 0
    for label, resolve in checks:
        try:
            resolve()
            print(f"  {OK} {label}：已配置（config.toml 直接值或环境变量）")
        except ConfigError as err:
            print(f"  {BAD} {err}")
            failed += 1
    if cfg.image_provider in {"gen", "openverse", "local"}:
        print(f"  {OK} 图库 provider={cfg.image_provider} 免 key")
    return failed


def _check_wechat(cfg: Config) -> int:
    try:
        wechat = WechatClient(cfg.app_id, cfg.app_secret)
        token = wechat.get_token()
        print(f"  {OK} access_token 获取成功（{token[:8]}…，IP 白名单配置正确）")
        count = wechat.draft_count()
        print(f"  {OK} 草稿权限正常（draft/count，当前草稿数 {count}）")
        return 0
    except (WechatApiError, httpx.HTTPError) as err:
        print(f"  {BAD} 微信连通失败：{err}")
        return 1


def _check_freepublish(cfg: Config, with_publish: bool) -> int:
    try:
        wechat = WechatClient(cfg.app_id, cfg.app_secret)
        if not with_publish:
            state, detail = _probe_freepublish(wechat)
            icon = OK if state == "yes" else WARN
            print(f"  {icon} 发布权限（只读探测，{detail}）")
            return 0
        return 0 if _full_publish_test(wechat) else 1
    except (WechatApiError, httpx.HTTPError) as err:
        print(f"  {BAD} 发布权限探测失败：{err}")
        return 1


def _full_publish_test(wechat: WechatClient) -> bool:
    """全链路实测：本地生成测试封面 → 推草稿 → 提交发布 → 轮询 → 删除发布与草稿。"""
    import tempfile
    import time

    from PIL import Image

    print("  … 全链路实测开始（发布一篇测试文章后立即删除，约 1 分钟）")
    media_id = article_id = None
    ok = True
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            Image.new("RGB", (900, 383), (240, 240, 240)).save(fh, "JPEG")
            cover = Path(fh.name)
        thumb = wechat.add_material(cover, "thumb")
        test_content = (
            '<section style="font-size:15px;">autopilot verify --with-publish 的测试文章，即将自动删除。</section>'
        )
        media_id = wechat.add_draft(
            [
                {
                    "title": "autopilot连通性测试(即将删除)",
                    "content": test_content,
                    "digest": "连通性测试",
                    "thumb_media_id": thumb,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        )
        print(f"  {OK} 测试草稿已推入（media_id={media_id}）")

        publish_id = wechat.freepublish_submit(media_id)
        print(f"  {OK} 发布已提交（publish_id={publish_id}），轮询结果…")
        result = {"status": 1}
        for _ in range(10):
            time.sleep(6)
            result = parse_publish_result(wechat.freepublish_get(publish_id))
            if result["status"] != 1:
                break
        ok = result["status"] == 0
        print(f"  {OK if ok else WARN} 发布结果：{result['status_text']}")
        article_id = result.get("article_id")
    except (WechatApiError, httpx.HTTPError) as err:
        print(f"  {BAD} 全链路实测失败：{err}")
        ok = False
    finally:
        try:
            if article_id:
                wechat.freepublish_delete(article_id)
                print(f"  {OK} 已删除测试发布（article_id={article_id}）")
            if media_id:
                wechat.delete_draft(media_id)
                print(f"  {OK} 已清理测试草稿")
        except (WechatApiError, httpx.HTTPError) as err:
            print(f"  {WARN} 清理未完成，请到公众号后台手动删除测试内容：{err}")
    return ok


def _probe_freepublish(wechat: WechatClient) -> tuple[str, str]:
    """只读探测 freepublish 权限：用一个不存在的 publish_id 查询。

    48001（api 未授权）说明账号无该权限；freepublish 层的其他错误码说明
    请求已通过授权层，推测有权限。权威结论以后台「接口权限」页与实际发布为准。
    """
    try:
        wechat.freepublish_get("autopilot-probe-nonexistent")
        return "yes", "接口直接返回成功，账号具备发布能力"
    except WechatApiError as err:
        if "freepublish" not in err.api:
            # 错误来自 token 等前置环节，说明不了发布权限
            return "unknown", f"无法探测（{err.errmsg[:60]}…），请先解决上方连通问题"
        if err.errcode == 48001:
            return "no", "账号无 freepublish 权限（个人号即如此；请确认 account.type 配置与后台『接口权限』页）"
        if err.errcode in (40007, 53401, 40013):
            return "yes", "请求已通过授权层（参数级报错），推测具备发布权限；如需确证请实测一次"
        return "unknown", f"无法判断（errcode={err.errcode}），请以后台「接口权限」页为准"


def _check_llm(cfg: Config) -> int:
    try:
        LLM(cfg).ping()
        print(f"  {OK} 模型连通正常")
        return 0
    except Exception as err:
        print(f"  {WARN} 模型连通失败：{str(err)[:160]}")
        return 0  # 模型问题不影响 verify 对微信侧的判定，只提示


# ── run ─────────────────────────────────────────────────
def cmd_run(args) -> None:
    load_dotenv()
    from .pipeline.runner import RunOptions, execute

    cfg = load_config()
    if args.publish:
        cfg = cfg.with_publish_mode(args.publish)
    opts = RunOptions(
        direction=args.direction,
        topic_only=args.topic_only,
        pick=args.pick,
        from_stage=args.from_stage,
        resume_dir=args.resume.resolve() if args.resume else None,
    )
    if not opts.direction and not opts.from_stage and not opts.topic_only and cfg.directions:
        opts.direction = cfg.directions[0]
        print(f"[0/7] 未指定 --direction，使用 niche.directions[0]：{opts.direction}")
    execute(cfg, opts)


# ── status / unpublish ─────────────────────────────────
@exit_on_config_error
def cmd_status(args) -> None:
    load_dotenv()
    cfg = load_config()
    path = args.run.resolve() / "08_publish_result.json"
    if not path.is_file():
        print(f"{WARN} {args.run} 没有发布记录（draft 模式只推草稿，不产生 08_publish_result.json）")
        return
    data = load_json(path)
    publish_id = data.get("publish_id")
    if not publish_id:
        print(f"{WARN} 发布未提交（当时被跳过：{data.get('publish_skipped', '未知原因')}）")
        return
    wechat = WechatClient(cfg.app_id, cfg.app_secret)
    result = parse_publish_result(wechat.freepublish_get(publish_id))
    data.update(result)
    save_json(path, data)
    print(f"{OK} 状态：{result['status_text']}")
    for url in result["article_urls"]:
        print(f"    文章链接：{url}")


@exit_on_config_error
def cmd_unpublish(args) -> None:
    load_dotenv()
    cfg = load_config()
    path = args.run.resolve() / "08_publish_result.json"
    if not path.is_file():
        raise SystemExit(f"{WARN} {args.run} 没有发布记录，无需回滚")
    data = load_json(path)
    article_id = data.get("article_id")
    if not article_id:
        raise SystemExit(f"{WARN} 该发布没有 article_id（可能未成功或已超时），请到公众号后台手动删除")
    wechat = WechatClient(cfg.app_id, cfg.app_secret)
    wechat.freepublish_delete(article_id)
    data["deleted"] = True
    save_json(path, data)
    print(f"{OK} 已删除已发布文章（article_id={article_id}）；草稿仍在草稿箱。")


# ── stats ───────────────────────────────────────────────
def cmd_stats(args) -> None:
    from .stats import record_stats

    run_dir = args.run.resolve()
    print(f"补录 {run_dir.name} 第 {args.day} 天数据（公众号后台「内容分析」里查看）：")
    record_stats(run_dir, day=args.day)
    print(f"{OK} 已写入 {run_dir / '09_stats.json'}")


# ── skills ──────────────────────────────────────────────
def cmd_skills(args) -> None:
    from .pipeline.common import skills_report

    print("各阶段能力来源（优先级：skills/<阶段>/SKILL.md → 内置 prompts/ → prompts/user/ 补充）\n")
    print(f"  {'阶段':<10}{'skill（下载）':<28}{'内置兜底':<28}补充说明")
    for row in skills_report():
        supplement = "✓" if row["supplement"] else "—"
        print(f"  {row['stage']:<10}{row['skill']:<28}{row['builtin']:<28}{supplement}")
    print(
        "\n放入方式：把 skill 目录（含 SKILL.md）拷贝为 skills/<阶段名>/，"
        "写作阶段可用 skills/writer.<风格>/ 精确匹配或 skills/writer/ 通用。详见 skills/README.md。"
    )


# ── schedule ────────────────────────────────────────────
def cmd_schedule(args) -> None:
    """常驻定时写作：每日 HH:MM 触发全流程，单日失败不退出进程。"""
    import datetime as dt
    import time

    from .pipeline.runner import RunOptions, execute
    from .scheduler import pick_direction, seconds_until_next

    load_dotenv()
    cfg = load_config()
    if args.publish:
        cfg = cfg.with_publish_mode(args.publish)
    if not cfg.directions and not args.direction:
        raise SystemExit(
            "定时写作需要选题方向：在 config.toml 的 [niche].directions 填方向池"
            "（推荐，按日轮换），或给 schedule 传 --direction 固定方向。"
        )
    hour, minute = args.daily
    pool_desc = f"方向池 {len(cfg.directions)} 个按日轮换" if cfg.directions else f"固定方向「{args.direction}」"
    print(f"[schedule] 定时写作已启动：每日 {hour:02d}:{minute:02d}（{pool_desc}），Ctrl+C 退出")

    while True:
        now = dt.datetime.now()
        wait = seconds_until_next(now, hour, minute)
        print(f"[schedule] 下次执行 {(now + dt.timedelta(seconds=wait)):%Y-%m-%d %H:%M}（{int(wait // 60)} 分钟后）")
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            print("\n[schedule] 已停止")
            return

        day = dt.date.today()
        direction = pick_direction(cfg.directions, day) or args.direction
        print(f"[schedule] {day} 开始执行，选题方向：{direction}")
        try:
            execute(cfg, RunOptions(direction=direction))
        except SystemExit as err:  # execute 的入参校验失败等，记录后继续等下一天
            print(f"{BAD} [schedule] 本次执行失败（exit={err.code}），明天继续。", file=sys.stderr)
        except KeyboardInterrupt:
            print("\n[schedule] 已停止")
            return
        except Exception as err:  # 单日失败（网络/模型/微信）不杀死常驻进程
            print(f"{BAD} [schedule] 本次执行失败：{err}；明天继续。", file=sys.stderr)


if __name__ == "__main__":
    main()
