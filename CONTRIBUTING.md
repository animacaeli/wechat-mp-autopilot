# 贡献指南

感谢关注 wechat-mp-autopilot！这是一个面向国内公众号运营者的 AI 内容流水线，
中文优先的issue / PR 都欢迎。

## 快速上手（开发环境）

```bash
git clone https://github.com/animacaeli/wechat-mp-autopilot.git
cd wechat-mp-autopilot
uv sync            # 安装依赖（含 dev 工具；国内网络走内置清华镜像）
make precommit     # 安装 git hooks：提交前 lint，推送前测试
make test          # 跑测试
```

## 开发约定

- **测试**：新增/修改功能必须带测试；微信接口相关测试用 fixture
  （`tests/test_wechat_client.py` 的 MockTransport 模式），不发真实请求。
  当前测试全部离线可跑（<1 秒）。
- **Lint**：ruff（配置在 pyproject.toml）。中文项目的全角标点规则
  （RUF001-003）已显式忽略，请勿重新启用。`make fmt` 一键格式化。
- **Prompt 与 Skill**：内置 prompts/ 只做兜底，能力演进优先发生在 skill
  生态侧（见 `skills/README.md`）。修改内置 prompt 必须同步升
  `prompts/_meta.json` 版本号。
- **Commit**：中文一行式，说清楚"做了什么 + 为什么"。参考 `git log`。

## 贡献方向

| 方向 | 说明 |
|---|---|
| 实测反馈 | 用你的账号（尤其企业认证号）跑 `autopilot verify`，提交实测报告 issue——README 兼容性矩阵靠这个更新 |
| Skill | 为某个阶段（选题/写作/去AI味/标题/摘要）写更好的 skill 并分享，注意输出格式契约 |
| 排版模板 | templates/ 下新增 Jinja2 模板（微信 inline-style 约束见 renderer.py） |
| 图案库 | artgen.py 的 _PATTERNS 加新图案（程序化、确定性种子） |
| 文档 | 部署教程（systemd/宝塔等）、踩坑记录 |

## 报告问题

- Bug 先跑 `uv run autopilot verify` 并附输出（脱敏）
- 微信接口问题附错误码（40164/48001 等），错误信息里通常已有修复指引
- 安全问题（密钥泄露等）请勿开公开 issue
