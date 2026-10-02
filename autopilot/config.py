"""配置加载与校验。

一切账号差异、模型差异收敛于 config.toml。密钥支持两种填法（双通道）：

1. 直接填值（``app_id = "wx..."``）——单文件快速上手，config.toml 已 gitignore
2. 只填 ``*_env`` 变量名，真实值放 .env / 服务器环境变量——适配 Docker
   ``env_file``、systemd、CI secrets 等标准注入通道，也避免误提交

两者都写时以环境变量优先。校验不过立即抛 ConfigError 并给出修复指引
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
IMAGE_PROVIDERS = {"gen", "local", "openverse", "pixabay", "pexels"}


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
    api_key_direct: str = ""
    stages: dict[str, LLMStageConfig] = field(default_factory=dict)

    def stage(self, name: str) -> LLMConfig:
        """返回某环节生效后的配置（覆盖值优先，其余继承全局）。"""
        ov = self.stages.get(name, LLMStageConfig())
        return LLMConfig(
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            model=ov.model or self.model,
            temperature=ov.temperature if ov.temperature is not None else self.temperature,
            max_tokens=ov.max_tokens if ov.max_tokens is not None else self.max_tokens,
            timeout_sec=self.timeout_sec,
            api_key_direct=self.api_key_direct,
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
    pixabay_api_key_env: str
    fallback_plain: bool
    app_id_direct: str = ""
    schedule_cron: str = "0 8 * * *"
    app_secret_direct: str = ""
    pexels_api_key_direct: str = ""
    pixabay_api_key_direct: str = ""

    def resolve_llm_key(self, llm: LLMConfig) -> str:
        return _resolve_secret(llm.api_key_direct, llm.api_key_env, "模型 API key")

    @property
    def app_id(self) -> str:
        return _resolve_secret(self.app_id_direct, self.app_id_env, "微信公众号 AppID")

    @property
    def app_secret(self) -> str:
        return _resolve_secret(self.app_secret_direct, self.app_secret_env, "微信公众号 AppSecret")

    @property
    def pexels_api_key(self) -> str:
        return _resolve_secret(self.pexels_api_key_direct, self.pexels_api_key_env, "Pexels API key")

    @property
    def pixabay_api_key(self) -> str:
        return _resolve_secret(self.pixabay_api_key_direct, self.pixabay_api_key_env, "Pixabay API key")

    def with_publish_mode(self, mode: str) -> Config:
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


def _resolve_secret(direct: str, env_name: str, label: str) -> str:
    """双通道密钥解析，环境变量优先（容器/CI 可覆盖文件内值），其次直接值。"""
    if env_name and env_name.strip():
        value = os.environ.get(env_name.strip(), "").strip()
        if value:
            return value
    if direct and direct.strip():
        return direct.strip()
    raise ConfigError(
        f"{label} 未配置：在 config.toml 中直接填写对应字段，"
        f"或设置环境变量 {env_name or '（*_env 字段指定的名字）'}（可写入 .env）。"
    )


def _require(data: dict, section: str, key: str):
    value = data.get(section, {}).get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        hint = _ENV_BY_TOML.get((section, key))
        env_hint = f"（纯环境变量模式：设置 {hint}）" if data.get("_env_only") and hint else ""
        raise ConfigError(f"配置缺少必填项 [{section}].{key}，请参照 config.example.toml 补齐{env_hint}。")
    return value


def _has(data: dict, section: str, key: str) -> bool:
    value = data.get(section, {}).get(key)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _secret_path_present(data: dict, section: str, base: str) -> bool:
    """密钥的双通道至少配了一条：直接值（base）或环境变量名（base_env）。"""
    return _has(data, section, base) or _has(data, section, f"{base}_env")


def validate_publish_interlock(cfg: Config) -> None:
    if cfg.publish_mode == "auto" and cfg.account_type != "enterprise":
        raise ConfigError(
            'publish.mode = "auto" 需要 account.type = "enterprise"。'
            "个人公众号自 2025.7 起无发布接口权限，只能推到草稿箱后人工发布；"
            f'当前 account.type = "{cfg.account_type}"。'
            '如只需推草稿，请把 [publish].mode 改回 "draft"。'
        )


# AUTOPILOT_* 环境变量 → config.toml 路径与类型（Docker env 注入的唯一通道）
ENV_OVERRIDES: dict[str, tuple[str, str, str]] = {
    "AUTOPILOT_ACCOUNT_TYPE": ("account", "type", "str"),
    "AUTOPILOT_PUBLISH_MODE": ("publish", "mode", "str"),
    "AUTOPILOT_PUBLISH_MAX_PER_DAY": ("publish", "max_per_day", "int"),
    "AUTOPILOT_PUBLISH_AI_DISCLOSURE": ("publish", "ai_disclosure", "bool"),
    "AUTOPILOT_POLL_INTERVAL_SEC": ("publish", "poll_interval_sec", "int"),
    "AUTOPILOT_POLL_TIMEOUT_MIN": ("publish", "poll_timeout_min", "int"),
    "AUTOPILOT_LLM_BASE_URL": ("llm", "base_url", "str"),
    "AUTOPILOT_LLM_API_KEY": ("llm", "api_key", "str"),
    "AUTOPILOT_LLM_MODEL": ("llm", "model", "str"),
    "AUTOPILOT_LLM_TEMPERATURE": ("llm", "temperature", "float"),
    "AUTOPILOT_LLM_MAX_TOKENS": ("llm", "max_tokens", "int"),
    "AUTOPILOT_LLM_TIMEOUT_SEC": ("llm", "timeout_sec", "int"),
    "AUTOPILOT_WECHAT_APP_ID": ("wechat", "app_id", "str"),
    "AUTOPILOT_WECHAT_APP_SECRET": ("wechat", "app_secret", "str"),
    "AUTOPILOT_NICHE_FIELD": ("niche", "field", "str"),
    "AUTOPILOT_NICHE_AUDIENCE": ("niche", "audience", "str"),
    "AUTOPILOT_NICHE_PERSONA": ("niche", "persona", "str"),
    "AUTOPILOT_NICHE_DIRECTIONS": ("niche", "directions", "list"),
    "AUTOPILOT_STYLE_PRESET": ("style", "preset", "str"),
    "AUTOPILOT_STYLE_TEMPLATE": ("style", "template", "str"),
    "AUTOPILOT_IMAGES_PROVIDER": ("images", "provider", "str"),
    "AUTOPILOT_IMAGES_FALLBACK_PLAIN": ("images", "fallback_plain", "bool"),
    "AUTOPILOT_PEXELS_API_KEY": ("images", "pexels_api_key", "str"),
    "AUTOPILOT_PIXABAY_API_KEY": ("images", "pixabay_api_key", "str"),
    "AUTOPILOT_CRON": ("schedule", "cron", "str"),
}
_ENV_BY_TOML = {(s, k): env for env, (s, k, _t) in ENV_OVERRIDES.items()}


def _coerce_env(raw: str, typ: str, env_name: str):
    try:
        if typ == "str":
            return raw
        if typ == "int":
            return int(raw)
        if typ == "float":
            return float(raw)
        if typ == "bool":
            return raw.lower() in {"1", "true", "yes", "on"}
        if typ == "list":
            return [x.strip() for x in raw.split(",") if x.strip()]
    except ValueError as err:
        raise ConfigError(f"环境变量 {env_name}={raw!r} 无法解析为 {typ}：{err}") from err
    raise ConfigError(f"未知类型 {typ}（{env_name}）")


def _apply_env_overrides(data: dict) -> None:
    """AUTOPILOT_* 环境变量覆盖配置（优先级最高），支持纯 env 无 config.toml 部署。"""
    for env_name, (section, key, typ) in ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            continue
        data.setdefault(section, {})[key] = _coerce_env(raw.strip(), typ, env_name)


# 纯 env 模式（无 config.toml）的默认值：密钥环境变量名 + 各段合理缺省，
# 让 Docker 用户最少只需设 3 个密钥 + 2 个定位字段
_ENV_ONLY_DEFAULTS = {
    "account": {"type": "personal"},
    "publish": {"mode": "draft"},
    "style": {"preset": "ganhuo", "template": "clean"},
    "llm": {
        "api_key_env": "LLM_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "wechat": {"app_id_env": "WECHAT_APP_ID", "app_secret_env": "WECHAT_APP_SECRET"},
    "images": {"pexels_api_key_env": "PEXELS_API_KEY", "pixabay_api_key_env": "PIXABAY_API_KEY"},
    "schedule": {"cron": "0 8 * * *"},
}


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or PROJECT_ROOT / "config.toml"
    if cfg_path.is_file():
        data = loads(cfg_path.read_text(encoding="utf-8"))
    elif any(os.environ.get(name, "").strip() for name in ENV_OVERRIDES):
        # 纯环境变量模式：Docker env 注入部署，无需挂载 config.toml
        data = {"_env_only": True}
        for section, defaults in _ENV_ONLY_DEFAULTS.items():
            data.setdefault(section, {}).update(defaults)
    else:
        raise ConfigError(
            f"找不到 {cfg_path}。请先复制模板：cp config.example.toml config.toml、运行 `autopilot init`，"
            "或用 AUTOPILOT_* 环境变量做纯 env 配置（Docker 部署，见 README）。"
        )
    _apply_env_overrides(data)

    account_type = _require(data, "account", "type")
    if account_type not in ACCOUNT_TYPES:
        raise ConfigError(f'[account].type 只能是 {" / ".join(sorted(ACCOUNT_TYPES))}，当前为 "{account_type}"。')

    publish_mode = _require(data, "publish", "mode")
    if publish_mode not in PUBLISH_MODES:
        raise ConfigError(f'[publish].mode 只能是 {" / ".join(sorted(PUBLISH_MODES))}，当前为 "{publish_mode}"。')

    for base, label in (("app_id", "微信公众号 AppID"), ("app_secret", "微信公众号 AppSecret")):
        if not _secret_path_present(data, "wechat", base):
            raise ConfigError(
                f"[wechat] 缺少 {label}：直接填 {base}，或用 {base}_env 指定环境变量"
                f"（参照 config.example.toml 的双通道注释）。"
            )
    if not _secret_path_present(data, "llm", "api_key"):
        raise ConfigError("[llm] 缺少模型 API key：直接填 api_key，或用 api_key_env 指定环境变量。")

    style_preset = _require(data, "style", "preset")
    if style_preset not in STYLE_PRESETS:
        raise ConfigError(f'[style].preset 只能是 {" / ".join(sorted(STYLE_PRESETS))}，当前为 "{style_preset}"。')

    image_provider = str(data.get("images", {}).get("provider", "gen"))
    if image_provider not in IMAGE_PROVIDERS:
        raise ConfigError(
            f'[images].provider 只能是 {" / ".join(sorted(IMAGE_PROVIDERS))}，当前为 "{image_provider}"。'
        )
    if image_provider == "pexels" and not _secret_path_present(data, "images", "pexels_api_key"):
        raise ConfigError(
            '[images].provider = "pexels" 需要配置 pexels_api_key 或 pexels_api_key_env'
            "（注意：Pexels 官方已暂停发放新 API key，老 key 仍可用）。"
        )
    if image_provider == "pixabay" and not _secret_path_present(data, "images", "pixabay_api_key"):
        raise ConfigError(
            '[images].provider = "pixabay" 需要配置 pixabay_api_key 或 pixabay_api_key_env'
            "（pixabay.com/api/docs 免费注册即得）。"
        )

    style_template = _require(data, "style", "template")
    if not (PROJECT_ROOT / "templates" / f"{style_template}.html.j2").is_file():
        raise ConfigError(
            f'[style].template = "{style_template}" 不存在，templates/ 目录下可用模板：{_available_templates()}。'
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
        app_id_env=str(data.get("wechat", {}).get("app_id_env", "WECHAT_APP_ID")),
        app_secret_env=str(data.get("wechat", {}).get("app_secret_env", "WECHAT_APP_SECRET")),
        publish_mode=publish_mode,
        poll_interval_sec=int(data.get("publish", {}).get("poll_interval_sec", 30)),
        poll_timeout_min=int(data.get("publish", {}).get("poll_timeout_min", 60)),
        max_per_day=int(data.get("publish", {}).get("max_per_day", 1)),
        ai_disclosure=bool(data.get("publish", {}).get("ai_disclosure", True)),
        llm=LLMConfig(
            base_url=_require(data, "llm", "base_url"),
            api_key_env=str(llm_raw.get("api_key_env", "LLM_API_KEY")),
            model=_require(data, "llm", "model"),
            temperature=float(llm_raw.get("temperature", 0.7)),
            max_tokens=int(llm_raw.get("max_tokens", 4096)),
            timeout_sec=int(llm_raw.get("timeout_sec", 120)),
            api_key_direct=str(llm_raw.get("api_key", "") or ""),
            stages=stages,
        ),
        niche_field=_require(data, "niche", "field"),
        audience=_require(data, "niche", "audience"),
        persona=str(data.get("niche", {}).get("persona", "")),
        directions=list(data.get("niche", {}).get("directions", [])),
        style_preset=style_preset,
        style_template=style_template,
        image_provider=image_provider,
        pexels_api_key_env=str(data.get("images", {}).get("pexels_api_key_env", "PEXELS_API_KEY")),
        pixabay_api_key_env=str(data.get("images", {}).get("pixabay_api_key_env", "PIXABAY_API_KEY")),
        fallback_plain=bool(data.get("images", {}).get("fallback_plain", True)),
        app_id_direct=str(data.get("wechat", {}).get("app_id", "") or ""),
        app_secret_direct=str(data.get("wechat", {}).get("app_secret", "") or ""),
        pexels_api_key_direct=str(data.get("images", {}).get("pexels_api_key", "") or ""),
        pixabay_api_key_direct=str(data.get("images", {}).get("pixabay_api_key", "") or ""),
        schedule_cron=str(data.get("schedule", {}).get("cron", "0 8 * * *")),
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
