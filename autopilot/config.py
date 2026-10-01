"""配置加载与校验。

一切账号差异、模型差异收敛于 config.toml；敏感值只存环境变量名，
实际取值在本模块按名字解析。校验不过立即抛 ConfigError 并给出修复指引
（fail fast，不静默降级）。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tomllib import loads

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ACCOUNT_TYPES = {"personal", "enterprise"}
PUBLISH_MODES = {"draft", "auto"}
STYLE_PRESETS = {"wenyi", "ganhuo", "youmo"}
LLM_STAGES = {"topics", "writer", "humanizer", "titlist", "digest"}


class ConfigError(Exception):
    """配置不合法；str(err) 已包含修复指引。"""


@dataclass
class LLMStageConfig:
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class LLMConfig:
    base_url: str
    api_key_env: str
    model: str
    temperature: float
    max_tokens: int
    timeout_sec: int
    stages: dict[str, LLMStageConfig] = field(default_factory=dict)

    def stage(self, name: str) -> "LLMConfig":
        """返回某环节生效后的配置（覆盖值优先，其余继承全局）。"""
        ov = self.stages.get(name, LLMStageConfig())
        return LLMConfig(
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            model=ov.model or self.model,
            temperature=ov.temperature if ov.temperature is not None else self.temperature,
            max_tokens=ov.max_tokens if ov.max_tokens is not None else self.max_tokens,
            timeout_sec=self.timeout_sec,
        )


@dataclass
class Config:
    account_type: str
    app_id_env: str
    app_secret_env: str
    publish_mode: str
    poll_interval_sec: int
    poll_timeout_min: int
    max_per_day: int
    ai_disclosure: bool
    llm: LLMConfig
    niche_field: str
    audience: str
    persona: str
    directions: list[str]
    style_preset: str
    style_template: str
    image_provider: str
    pexels_api_key_env: str
    fallback_plain: bool

    def secret(self, env_name: str) -> str:
        value = os.environ.get(env_name, "").strip()
        if not value:
            raise ConfigError(
                f"环境变量 {env_name} 未设置。请在 .env 或服务器环境中填写，"
                f"变量名来自 config.toml 中对应的 *_env 字段。"
            )
        return value

    @property
    def app_id(self) -> str:
        return self.secret(self.app_id_env)

    @property
    def app_secret(self) -> str:
        return self.secret(self.app_secret_env)

    def with_publish_mode(self, mode: str) -> "Config":
        """CLI --publish 临时覆盖发布模式；同样走联锁校验。"""
        data = dict(self.__dict__)
        data["publish_mode"] = mode
        new = Config(**data)
        validate_publish_interlock(new)
        return new


def load_dotenv(path: Path | None = None) -> None:
    """读取 .env（KEY=VALUE），已存在的环境变量不覆盖。"""
    env_file = path or PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _require(data: dict, section: str, key: str):
    value = data.get(section, {}).get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigError(f"config.toml 缺少必填项 [{section}].{key}，请参照 config.example.toml 补齐。")
    return value


def validate_publish_interlock(cfg: Config) -> None:
    if cfg.publish_mode == "auto" and cfg.account_type != "enterprise":
        raise ConfigError(
            "publish.mode = \"auto\" 需要 account.type = \"enterprise\"。"
            "个人公众号自 2025.7 起无发布接口权限，只能推到草稿箱后人工发布；"
            f"当前 account.type = \"{cfg.account_type}\"。"
            "如只需推草稿，请把 [publish].mode 改回 \"draft\"。"
        )


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or PROJECT_ROOT / "config.toml"
    if not cfg_path.is_file():
        raise ConfigError(
            f"找不到 {cfg_path}。请先复制模板：cp config.example.toml config.toml，"
            "或运行 `autopilot init`。"
        )
    data = loads(cfg_path.read_text(encoding="utf-8"))

    account_type = _require(data, "account", "type")
    if account_type not in ACCOUNT_TYPES:
        raise ConfigError(f"[account].type 只能是 {' / '.join(sorted(ACCOUNT_TYPES))}，当前为 \"{account_type}\"。")

    publish_mode = _require(data, "publish", "mode")
    if publish_mode not in PUBLISH_MODES:
        raise ConfigError(f"[publish].mode 只能是 {' / '.join(sorted(PUBLISH_MODES))}，当前为 \"{publish_mode}\"。")

    style_preset = _require(data, "style", "preset")
    if style_preset not in STYLE_PRESETS:
        raise ConfigError(f"[style].preset 只能是 {' / '.join(sorted(STYLE_PRESETS))}，当前为 \"{style_preset}\"。")

    style_template = _require(data, "style", "template")
    if not (PROJECT_ROOT / "templates" / f"{style_template}.html.j2").is_file():
        raise ConfigError(
            f"[style].template = \"{style_template}\" 不存在，"
            f"templates/ 目录下可用模板：{_available_templates()}。"
        )

    llm_raw = data.get("llm", {})
    stages: dict[str, LLMStageConfig] = {}
    for name, ov in llm_raw.items():
        if name in LLM_STAGES and isinstance(ov, dict):
            stages[name] = LLMStageConfig(
                model=ov.get("model"),
                temperature=ov.get("temperature"),
                max_tokens=ov.get("max_tokens"),
            )
    cfg = Config(
        account_type=account_type,
        app_id_env=_require(data, "wechat", "app_id_env"),
        app_secret_env=_require(data, "wechat", "app_secret_env"),
        publish_mode=publish_mode,
        poll_interval_sec=int(data.get("publish", {}).get("poll_interval_sec", 30)),
        poll_timeout_min=int(data.get("publish", {}).get("poll_timeout_min", 60)),
        max_per_day=int(data.get("publish", {}).get("max_per_day", 1)),
        ai_disclosure=bool(data.get("publish", {}).get("ai_disclosure", True)),
        llm=LLMConfig(
            base_url=_require(data, "llm", "base_url"),
            api_key_env=_require(data, "llm", "api_key_env"),
            model=_require(data, "llm", "model"),
            temperature=float(llm_raw.get("temperature", 0.7)),
            max_tokens=int(llm_raw.get("max_tokens", 4096)),
            timeout_sec=int(llm_raw.get("timeout_sec", 120)),
            stages=stages,
        ),
        niche_field=_require(data, "niche", "field"),
        audience=_require(data, "niche", "audience"),
        persona=str(data.get("niche", {}).get("persona", "")),
        directions=list(data.get("niche", {}).get("directions", [])),
        style_preset=style_preset,
        style_template=style_template,
        image_provider=str(data.get("images", {}).get("provider", "pexels")),
        pexels_api_key_env=_require(data, "images", "pexels_api_key_env"),
        fallback_plain=bool(data.get("images", {}).get("fallback_plain", True)),
    )
    validate_publish_interlock(cfg)
    return cfg


def _available_templates() -> str:
    templates = sorted(p.stem.removesuffix(".html") for p in (PROJECT_ROOT / "templates").glob("*.html.j2"))
    return " / ".join(templates) if templates else "（无）"


def exit_on_config_error(fn):
    """CLI 装饰器：配置错误打印指引后退出，不吐 traceback。"""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ConfigError as err:
            print(f"[配置错误] {err}", file=sys.stderr)
            raise SystemExit(2) from err

    return wrapper
