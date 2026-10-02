# skills/ — 各阶段的能力来源

每个流水线阶段的专业指令（怎么选题、怎么写、怎么去 AI 味……）由放在这里的
**skill** 提供。skill 采用 Agent Skills 通用格式（YAML frontmatter + markdown
正文），从任何来源下载后按目录名放入即可生效，**无需改代码**。

## 加载优先级（每个阶段）

```
skills/<阶段>/SKILL.md      ← 下载的技能，存在则完全替换内置指令
        ↓（没有 skill 时兜底）
prompts/<对应文件>           ← 仓库内置默认，保证 clone 即能跑
        ↓（无论上层是谁，都会附加在末尾）
prompts/user/<对应文件>      ← 你的补充说明：项目特有约束、范文等
```

## 阶段名 → 目录名映射

| 阶段 | skill 目录 | 内置兜底文件 |
|---|---|---|
| 选题 | `skills/topics/` | `prompts/topic.selector.md` |
| 写作 | `skills/writer.ganhuo/`（按风格精确匹配）或 `skills/writer/`（通用） | `prompts/writer.<风格>.md` |
| 去 AI 味 | `skills/humanize/` | `prompts/humanizer.md` |
| 标题 | `skills/titlist/` | `prompts/titlist.md` |
| 摘要 | `skills/digest/` | `prompts/digest.md` |
| 封面设计 | `skills/cover/` | `prompts/cover.designer.md` |

## SKILL.md 格式

```markdown
---
name: my-writer
description: 我的公众号写作技能
version: 1.0.0
---

（正文：完整的阶段指令。它会作为该阶段 LLM 的 system prompt，
请写清楚角色、规则、输出格式约束——输出格式必须与内置文件一致，
否则流水线解析会失败，可参照内置文件里的格式约定。）
```

## 注意事项

- **捆绑资源**：skill 目录内 SKILL.md 之外的所有 `.md`（如 `references/`
  语料，README.md 除外）会自动并入该阶段指令正文——Agent Skills 的捆绑
  资料惯例在单次 LLM 调用场景下的等价实现
- **输出格式契约**：topics / titlist / cover 三个阶段要求 JSON 输出，skill
  正文中必须保留与内置文件相同的 JSON 字段约定（字段名、枚举值），骨架代码
  按这些字段解析；writer / humanize / digest 输出纯文本，格式自由
- 用 `uv run autopilot skills` 随时查看当前各阶段的实际来源
- 每篇 run 的产物会记录各阶段来源标签（如 `skill:writer@1.2`），便于效果归因
- 写作类 skill 里放自己的范文 few-shot，效果远好于抽象的风格形容词
