"""技能层测试：skill 覆盖内置、风格回退、补充说明附加、frontmatter 解析。"""

import pytest

from autopilot.config import PROJECT_ROOT
from autopilot.pipeline.common import load_stage_instructions, skills_report


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """临时项目根（含内置 prompts），patch common 模块的 PROJECT_ROOT。"""
    import shutil

    from autopilot.pipeline import common

    shutil.copytree(PROJECT_ROOT / "prompts", tmp_path / "prompts")
    monkeypatch.setattr(common, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _write_skill(root, name: str, body: str, version: str = "1.0.0"):
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: 测试技能\nversion: {version}\n---\n\n{body}",
        encoding="utf-8",
    )


def test_skill_replaces_builtin(sandbox):
    _write_skill(sandbox, "topics", "你是社区下载的选题技能。")
    body, prov = load_stage_instructions("topics")
    assert "社区下载的选题技能" in body
    assert "选题 agent" not in body  # 内置完全被替换，不再拼接
    assert prov["source"] == "skill:topics"
    assert prov["label"] == "skill:topics@1.0.0"


def test_fallback_to_builtin_without_skill(sandbox):
    body, prov = load_stage_instructions("titlist")
    assert "标题" in body
    assert prov["source"] == "builtin"
    assert prov["label"].startswith("builtin@")


def test_user_supplement_appended_on_top_of_skill(sandbox):
    _write_skill(sandbox, "titlist", "技能正文。")
    supp = sandbox / "prompts" / "user" / "titlist.md"
    supp.parent.mkdir(parents=True, exist_ok=True)
    supp.write_text("额外要求：标题里必须有数字。", encoding="utf-8")

    body, prov = load_stage_instructions("titlist")
    assert "技能正文。" in body
    assert "额外要求" in body
    assert body.index("技能正文。") < body.index("额外要求")
    assert prov.get("supplement") is True


def test_writer_style_specific_beats_generic(sandbox):
    _write_skill(sandbox, "writer", "通用写作技能。")
    _write_skill(sandbox, "writer.wenyi", "文艺专用技能。", version="2.1")

    body_ganhuo, prov_ganhuo = load_stage_instructions("writer", "ganhuo")
    assert "通用写作技能" in body_ganhuo
    assert prov_ganhuo["source"] == "skill:writer"

    body_wenyi, prov_wenyi = load_stage_instructions("writer", "wenyi")
    assert "文艺专用技能" in body_wenyi
    assert prov_wenyi["label"] == "skill:writer.wenyi@2.1"


def test_frontmatter_stripped(sandbox):
    _write_skill(sandbox, "digest", "正文从这里开始。")
    body, _ = load_stage_instructions("digest")
    assert not body.startswith("---")
    assert "name:" not in body


def test_missing_everything_raises(sandbox):
    (sandbox / "prompts" / "humanizer.md").unlink()
    with pytest.raises(FileNotFoundError, match="skills/humanize"):
        load_stage_instructions("humanize")


def test_skills_report_shape(sandbox):
    _write_skill(sandbox, "topics", "x")
    rows = {r["stage"]: r for r in skills_report()}
    assert rows["topics"]["skill"] == "topics@1.0.0"
    assert rows["writer"]["skill"] == "—"  # 未放 skill
    assert set(rows) == {"topics", "writer", "humanize", "titlist", "digest", "cover"}
