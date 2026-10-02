"""流水线公共工具：prompt 加载（含用户覆盖层）与产物 IO。"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import PROJECT_ROOT


def load_prompt(name: str) -> tuple[str, str]:
    """加载 prompt：prompts/user/<name> 优先于内置 prompts/<name>。

    返回 (内容, 版本号)；用户覆盖层版本记为 "user"。
    """
    builtin = PROJECT_ROOT / "prompts" / name
    user_path = PROJECT_ROOT / "prompts" / "user" / name
    if user_path.is_file():
        return user_path.read_text(encoding="utf-8"), "user"
    if not builtin.is_file():
        raise FileNotFoundError(f"prompt 文件不存在：prompts/{name}（内置目录与 prompts/user/ 覆盖层都没有）")
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
