"""配置层测试：模板可加载、联锁校验、环节覆盖继承、密钥解析。"""

import pytest

from autopilot.config import PROJECT_ROOT, ConfigError, load_config


def test_example_config_loads():
    """config.example.toml 必须始终是一份合法配置（防模板与代码脱节）。"""
    cfg = load_config(PROJECT_ROOT / "config.example.toml")
    assert cfg.account_type == "personal"
    assert cfg.publish_mode == "draft"
    assert cfg.style_preset in {"wenyi", "ganhuo", "youmo"}


def test_interlock_personal_auto_rejected(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    broken = tmp_path / "config.toml"
    broken.write_text(text.replace('mode = "draft"', 'mode = "auto"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="enterprise"):
        load_config(broken)


def test_interlock_enterprise_auto_ok(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    ok = tmp_path / "config.toml"
    ok.write_text(text.replace('type = "personal"', 'type = "enterprise"')
                      .replace('mode = "draft"', 'mode = "auto"'), encoding="utf-8")
    cfg = load_config(ok)
    assert cfg.publish_mode == "auto"
    assert cfg.with_publish_mode("draft").publish_mode == "draft"


def test_stage_override_inherits_unset_fields(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(text.replace(
        "# [llm.writer]",
        '[llm.writer]\ntemperature = 1.0',
    ), encoding="utf-8")
    cfg = load_config(cfg_file)
    writer = cfg.llm.stage("writer")
    assert writer.temperature == 1.0
    assert writer.model == cfg.llm.model  # 未覆盖的字段继承全局
    assert cfg.llm.stage("titlist").temperature == cfg.llm.temperature


def test_missing_required_field(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[account]\ntype = \"personal\"\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="缺少必填项"):
        load_config(cfg_file)


def test_secret_missing_env(monkeypatch):
    cfg = load_config(PROJECT_ROOT / "config.example.toml")
    monkeypatch.delenv("WECHAT_APP_ID", raising=False)
    with pytest.raises(ConfigError, match="WECHAT_APP_ID"):
        cfg.app_id


def test_load_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# 注释\nFOO_ENV_TEST=hello\nBAR_ENV_TEST=\"quoted\"\n", encoding="utf-8")
    monkeypatch.delenv("FOO_ENV_TEST", raising=False)
    monkeypatch.delenv("BAR_ENV_TEST", raising=False)
    from autopilot.config import load_dotenv
    load_dotenv(env_file)
    import os
    assert os.environ["FOO_ENV_TEST"] == "hello"
    assert os.environ["BAR_ENV_TEST"] == "quoted"
