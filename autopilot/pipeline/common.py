"""流水线公共工具：阶段指令三层加载（skill → 内置兜底 → 用户补充）与产物 IO。

每个阶段的「专业能力」来源优先级：

1. ``skills/<阶段>/SKILL.md`` —— 下载的技能（Agent Skills 通用格式：YAML
   frontmatter + markdown 正文），存在则**完全替换**内置指令；写作阶段支持
   按风格细分（``skills/writer.ganhuo/`` 优先于 ``skills/writer/``）
2. 内置 ``prompts/<对应文件>`` —— 无 skill 时的兜底默认，保证 clone 即能跑
3. ``prompts/user/<对应文件>`` —— 用户补充说明，无论上层来源是什么都会附加在末尾

内置 prompt 与用户补充都不再是能力主体：能力靠 skill 供给、可替换可升级。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import PROJECT_ROOT

# 阶段名 → 内置 prompt 文件（写作阶段按风格另行拼接）
STAGE_PROMPT_FILES = {
    "topics": "topic.selector.md",
    "humanize": "humanizer.md",
    "titlist": "titlist.md",
    "digest": "digest.md",
    "cover": "cover.designer.md",
}


def stage_prompt_file(stage: str, preset: str | None = None) -> str:
    if stage == "writer":
        return f"writer.{preset}.md"
    if stage not in STAGE_PROMPT_FILES:
        raise KeyError(f"未知阶段 {stage}；可用：writer / {' / '.join(STAGE_PROMPT_FILES)}")
    return STAGE_PROMPT_FILES[stage]


def load_stage_instructions(stage: str, preset: str | None = None) -> tuple[str, dict]:
    """加载某阶段的最终 system 指令。

    返回 (指令文本, 溯源信息)。溯源信息形如
    ``{"label": "skill:writer.ganhuo@1.2", "source": "skill", "version": "1.2", "supplement": True}``，
    label 会写入 run 产物，便于效果归因。
    """
    prompt_file = stage_prompt_file(stage, preset)

    skill_dir, skill_body, skill_version = _find_skill(stage, preset)
    if skill_dir is not None:
        body = skill_body
        provenance = {"source": f"skill:{skill_dir}", "version": skill_version}
    else:
        builtin = PROJECT_ROOT / "prompts" / prompt_file
        if not builtin.is_file():
            raise FileNotFoundError(
                f"阶段 {stage} 既没有 skills/{stage}/SKILL.md，也没有内置 prompts/{prompt_file}。"
                f"请下载对应 skill 放入 skills/ 目录（见 skills/README.md）。"
            )
        body = builtin.read_text(encoding="utf-8")
        provenance = {"source": "builtin", "version": str(_meta().get(prompt_file, "0"))}

    provenance["label"] = f"{provenance['source']}@{provenance['version']}"

    supplement = PROJECT_ROOT / "prompts" / "user" / prompt_file
    if supplement.is_file():
        body += "\n\n【项目补充说明】（追加约束，优先级低于上方指令）\n" + supplement.read_text(encoding="utf-8")
        provenance["supplement"] = True
    return body, provenance


def _find_skill(stage: str, preset: str | None) -> tuple[str | None, str, str]:
    """查找 skill：写作阶段先精确匹配风格，再退到通用 writer。"""
    candidates = [f"{stage}.{preset}", stage] if stage == "writer" and preset else [stage]
    for name in candidates:
        path = PROJECT_ROOT / "skills" / name / "SKILL.md"
        if path.is_file():
            body, version = _parse_skill(path)
            bundled = _bundled_resources(path.parent)
            if bundled:
                body += "\n\n" + bundled
            return name, body, version
    return None, "", ""


def _bundled_resources(skill_dir: Path) -> str:
    """拼接 skill 目录内 SKILL.md 之外的 .md 捆绑资源（按文件名排序）。

    Agent Skills 惯例允许目录里放 references/ 等语料；本流水线的阶段调用
    没有文件读取工具，因此把捆绑资料直接并入指令正文。
    """
    parts = []
    for md in sorted(skill_dir.rglob("*.md")):
        if md.name == "SKILL.md" or md.name == "README.md":
            continue
        rel = md.relative_to(skill_dir).as_posix()
        content = md.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"【捆绑资料：{rel}】\n{content}")
    return "\n\n".join(parts)


def _parse_skill(path: Path) -> tuple[str, str]:
    """解析 SKILL.md：剥掉 YAML frontmatter，提取 name/version。"""
    text = path.read_text(encoding="utf-8")
    version = "0"
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key, value = key.strip(), value.strip().strip("'\"")
            if key == "version":
                version = value
            elif key == "name" and version == "0":
                version = value
        text = text[match.end() :]
    return text.strip(), version


def skills_report(preset: str | None = None) -> list[dict]:
    """各阶段能力来源一览（`autopilot skills` 的数据源）。preset 缺省读当前配置。"""
    if preset is None:
        try:
            from ..config import load_config

            preset = load_config().style_preset
        except Exception:
            preset = "ganhuo"
    rows = []
    for stage in ["topics", "writer", "humanize", "titlist", "digest", "cover"]:
        row = {"stage": stage}
        prompt_file = stage_prompt_file(stage, preset) if stage == "writer" else stage_prompt_file(stage)
        row["builtin"] = prompt_file
        skill_dir, _, version = _find_skill(stage, preset)
        row["skill"] = f"{skill_dir}@{version}" if skill_dir else "—"
        row["supplement"] = (PROJECT_ROOT / "prompts" / "user" / prompt_file).is_file()
        rows.append(row)
    return rows


def load_prompt(name: str) -> tuple[str, str]:
    """直接读内置/用户 prompt 文件（遗留接口，仅供补充说明场景使用）。"""
    builtin = PROJECT_ROOT / "prompts" / name
    user_path = PROJECT_ROOT / "prompts" / "user" / name
    if user_path.is_file():
        return user_path.read_text(encoding="utf-8"), "user"
    if not builtin.is_file():
        raise FileNotFoundError(f"prompt 文件不存在：prompts/{name}")
    return builtin.read_text(encoding="utf-8"), _meta().get(name, "0")


def _meta() -> dict:
    meta_path = PROJECT_ROOT / "prompts" / "_meta.json"
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def strip_fence(text: str) -> str:
    """剥掉 LLM 回复外层的 ```markdown / ```json 围栏。"""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1 and text.rstrip().endswith("```"):
            text = text[first_nl + 1 : text.rstrip().rfind("```")]
    return text.strip()
