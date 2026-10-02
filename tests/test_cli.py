"""CLI 冒烟测试：不触网，验证子命令入口、帮助与无配置时的友好报错。"""

import pytest

from autopilot.cli import build_parser, main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "autopilot" in capsys.readouterr().out


def test_all_subcommands_registered():
    parser = build_parser()
    actions = {a for a in parser._subparsers._group_actions}
    choices = set().union(*(a.choices.keys() for a in actions))
    assert choices == {"init", "verify", "run", "status", "unpublish", "stats", "skills"}


def test_unknown_command_exits():
    with pytest.raises(SystemExit):
        main(["frobnicate"])


def test_run_requires_direction_or_pool(tmp_path, monkeypatch):
    """无 --direction 且 niche.directions 为空时给出可读报错（非 traceback）。"""
    import shutil

    from autopilot.config import PROJECT_ROOT

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        (PROJECT_ROOT / "config.example.toml")
        .read_text(encoding="utf-8")
        .replace("directions = []", "directions = []"),
        encoding="utf-8",
    )
    monkeypatch.setattr("autopilot.config.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("autopilot.pipeline.common.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("autopilot.pipeline.runner.PROJECT_ROOT", tmp_path)
    shutil.copytree(PROJECT_ROOT / "prompts", tmp_path / "prompts")
    shutil.copytree(PROJECT_ROOT / "templates", tmp_path / "templates")
    for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "LLM_API_KEY", "PEXELS_API_KEY"):
        monkeypatch.setenv(name, "x")

    from autopilot.config import load_config

    cfg = load_config(cfg_file)
    assert cfg.directions == []
    # execute 的入口校验（不真正跑 LLM）
    from autopilot.pipeline.runner import RunOptions

    with pytest.raises(SystemExit, match="--direction"):
        from autopilot.pipeline.runner import execute

        execute(cfg, RunOptions(direction=""))
