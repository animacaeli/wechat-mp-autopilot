"""配置层测试：模板可加载、联锁校验、环节覆盖继承、密钥解析。"""

import pytest

from autopilot.config import PROJECT_ROOT, ConfigError, load_config


def test_example_config_loads():
    """config.example.toml 必须始终是一份合法配置（防模板与代码脱节）。"""
    cfg = load_config(PROJECT_ROOT / "config.example.toml")
    assert cfg.account_type == "personal"
    assert cfg.publish_mode == "draft"
    assert cfg.style_preset in {"wenyi", "ganhuo", "youmo"}
    # 默认图库必须免 key（Pexels 已停发新 key，新用户拿不到）
    assert cfg.image_provider in {"gen", "local"}


def _rewrite_example(tmp_path, replacements: dict):
    import re

    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.MULTILINE)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(text, encoding="utf-8")
    return cfg_file


def test_unknown_image_provider_rejected(tmp_path):
    cfg_file = _rewrite_example(tmp_path, {r"^(provider\s*=).*$": r'\1 "giphy"'})
    with pytest.raises(ConfigError, match="provider"):
        load_config(cfg_file)


def test_pixabay_provider_without_key_rejected(tmp_path):
    cfg_file = _rewrite_example(
        tmp_path,
        {r"^(provider\s*=).*$": r'\1 "pixabay"', r"^pixabay_api_key_env.*$": ""},
    )
    with pytest.raises(ConfigError, match="pixabay"):
        load_config(cfg_file)


def test_pixabay_provider_with_key_ok(tmp_path):
    cfg_file = _rewrite_example(tmp_path, {r"^(provider\s*=).*$": r'\1 "pixabay"'})
    assert load_config(cfg_file).image_provider == "pixabay"


def test_interlock_personal_auto_rejected(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    broken = tmp_path / "config.toml"
    broken.write_text(text.replace('mode = "draft"', 'mode = "auto"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="enterprise"):
        load_config(broken)


def test_interlock_enterprise_auto_ok(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    ok = tmp_path / "config.toml"
    ok.write_text(
        text.replace('type = "personal"', 'type = "enterprise"').replace('mode = "draft"', 'mode = "auto"'),
        encoding="utf-8",
    )
    cfg = load_config(ok)
    assert cfg.publish_mode == "auto"
    assert cfg.with_publish_mode("draft").publish_mode == "draft"


def test_stage_override_inherits_unset_fields(tmp_path):
    text = (PROJECT_ROOT / "config.example.toml").read_text(encoding="utf-8")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        text.replace(
            "# [llm.writer]",
            "[llm.writer]\ntemperature = 1.0",
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    writer = cfg.llm.stage("writer")
    assert writer.temperature == 1.0
    assert writer.model == cfg.llm.model  # 未覆盖的字段继承全局
    assert cfg.llm.stage("titlist").temperature == cfg.llm.temperature


def test_missing_required_field(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[account]\ntype = "personal"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="缺少必填项"):
        load_config(cfg_file)


def test_secret_missing_env(monkeypatch):
    cfg = load_config(PROJECT_ROOT / "config.example.toml")
    monkeypatch.delenv("WECHAT_APP_ID", raising=False)
    with pytest.raises(ConfigError, match="WECHAT_APP_ID"):
        _ = cfg.app_id


def test_inline_secrets_single_file(tmp_path, monkeypatch):
    """双通道：直接填值即可单文件跑通，无需任何环境变量。"""
    for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = _rewrite_example(
        tmp_path,
        {
            r"^(app_id\s*=).*$": r'\1 "wx-inline"',
            r"^(app_secret\s*=).*$": r'\1 "secret-inline"',
            r"^(api_key\s*=).*$": r'\1 "sk-inline"',
        },
    )
    cfg = load_config(cfg_file)
    assert cfg.app_id == "wx-inline"
    assert cfg.app_secret == "secret-inline"
    assert cfg.resolve_llm_key(cfg.llm) == "sk-inline"


def test_env_overrides_inline_secret(tmp_path, monkeypatch):
    """双通道同时配置时，环境变量优先（容器/CI 可覆盖文件内值）。"""
    monkeypatch.setenv("WECHAT_APP_ID", "wx-from-env")
    cfg_file = _rewrite_example(tmp_path, {r"^(app_id\s*=).*$": r'\1 "wx-inline"'})
    cfg = load_config(cfg_file)
    assert cfg.app_id == "wx-from-env"


def test_missing_secret_both_channels_rejected(tmp_path, monkeypatch):
    for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    cfg_file = _rewrite_example(
        tmp_path,
        {
            r"^app_id_env.*$": "",
            r"^app_secret_env.*$": "",
            r"^api_key_env.*$": "",
        },
    )
    with pytest.raises(ConfigError, match="AppID"):
        load_config(cfg_file)


def test_load_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('# 注释\nFOO_ENV_TEST=hello\nBAR_ENV_TEST="quoted"\n', encoding="utf-8")
    monkeypatch.delenv("FOO_ENV_TEST", raising=False)
    monkeypatch.delenv("BAR_ENV_TEST", raising=False)
    from autopilot.config import load_dotenv

    load_dotenv(env_file)
    import os

    assert os.environ["FOO_ENV_TEST"] == "hello"
    assert os.environ["BAR_ENV_TEST"] == "quoted"


# ── AUTOPILOT_* 环境变量注入（Docker 部署通道）─────────────

_ALL_AUTOPILOT = [name for name in __import__("autopilot.config", fromlist=["ENV_OVERRIDES"]).ENV_OVERRIDES]


@pytest.fixture
def no_autopilot_env(monkeypatch):
    for name in _ALL_AUTOPILOT:
        monkeypatch.delenv(name, raising=False)


def test_env_overrides_file_config(tmp_path, no_autopilot_env, monkeypatch):
    """AUTOPILOT_* 优先于 config.toml 的值。"""
    cfg_file = _rewrite_example(tmp_path, {})
    monkeypatch.setenv("AUTOPILOT_ACCOUNT_TYPE", "enterprise")
    monkeypatch.setenv("AUTOPILOT_IMAGES_PROVIDER", "local")
    monkeypatch.setenv("AUTOPILOT_NICHE_DIRECTIONS", "A,B, C")
    monkeypatch.setenv("AUTOPILOT_CRON", "30 7 * * *")
    cfg = load_config(cfg_file)
    assert cfg.account_type == "enterprise"
    assert cfg.image_provider == "local"
    assert cfg.directions == ["A", "B", "C"]
    assert cfg.schedule_cron == "30 7 * * *"


def test_env_only_mode_without_config_file(tmp_path, no_autopilot_env, monkeypatch, tmp_path_factory):
    """无 config.toml 时，AUTOPILOT_* 环境变量即可完成全部配置（Docker env 注入）。"""
    for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "LLM_API_KEY"):
        monkeypatch.setenv(name, f"{name}-value")
    monkeypatch.setenv("AUTOPILOT_NICHE_FIELD", "情感成长")
    monkeypatch.setenv("AUTOPILOT_NICHE_AUDIENCE", "普通读者")
    monkeypatch.setenv("AUTOPILOT_STYLE_PRESET", "wenyi")
    monkeypatch.setenv("AUTOPILOT_ACCOUNT_TYPE", "personal")

    cfg = load_config(tmp_path / "不存在的config.toml")
    assert cfg.account_type == "personal"
    assert cfg.niche_field == "情感成长"
    assert cfg.style_preset == "wenyi"
    assert cfg.image_provider == "gen"  # 默认值
    assert cfg.schedule_cron == "0 8 * * *"
    assert cfg.app_id == "WECHAT_APP_ID-value"  # 密钥走默认 *_env 变量名


def test_env_only_missing_required_gives_env_hint(tmp_path, no_autopilot_env, monkeypatch):
    """纯 env 模式缺必填项时，报错指明对应的环境变量名。"""
    monkeypatch.setenv("AUTOPILOT_NICHE_FIELD", "只有领域没有读者")
    with pytest.raises(ConfigError, match="AUTOPILOT_NICHE_AUDIENCE"):
        load_config(tmp_path / "不存在的config.toml")


def test_env_bad_int_rejected(tmp_path, no_autopilot_env, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_PUBLISH_MAX_PER_DAY", "abc")
    cfg_file = _rewrite_example(tmp_path, {})
    with pytest.raises(ConfigError, match="AUTOPILOT_PUBLISH_MAX_PER_DAY"):
        load_config(cfg_file)


def test_comment_defaults_and_env_override(tmp_path, no_autopilot_env, monkeypatch):
    """留言默认开启；AUTOPILOT_* 可关闭或收紧为仅粉丝可评。"""
    cfg_file = _rewrite_example(tmp_path, {})
    cfg = load_config(cfg_file)
    assert cfg.open_comment is True
    assert cfg.only_fans_comment is False

    monkeypatch.setenv("AUTOPILOT_PUBLISH_OPEN_COMMENT", "false")
    monkeypatch.setenv("AUTOPILOT_PUBLISH_ONLY_FANS_COMMENT", "true")
    cfg2 = load_config(cfg_file)
    assert cfg2.open_comment is False
    assert cfg2.only_fans_comment is True
