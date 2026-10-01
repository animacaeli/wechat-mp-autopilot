# wechat-mp-autopilot

公众号 AI 自动化写作流水线。一条命令（或一个 cron）跑完：

**选题 → 写作 → 去AI味 → 标题优化 → 排版渲染 → 配图 → 推入草稿箱 →（企业认证号）自动发布**

- **双账号形态，同一套代码**：个人公众号跑到草稿箱为止，人工在后台确认发布；企业认证公众号可配置为全自动发布（freepublish）
- **全配置驱动**：账号类型、发布策略、大模型（任意 OpenAI 兼容端点：DeepSeek / GLM / OpenAI / 本地 vLLM……）、账号定位、写作风格，全部收敛在一个 `config.toml`
- **产物落盘 + 断点重跑**：每篇文章独立 `runs/日期-slug/` 目录，每步产物可检视，任一步不满意可 `--from humanize` 从该步重跑
- **去 AI 味双保险**：LLM 重写 + 纯规则检测器（0~100 AI 味指数）；auto 发布模式下指数超标自动降级为只推草稿
- **刻意的克制**：不引入 LangChain/CrewAI（线性管道更透明）、不做 Web UI、不做群发自动化

```
方向输入 ─▶ ①选题 ─▶ ②写作 ─▶ ③去AI味 ─▶ ④标题 ─▶ ⑤排版 ─▶ ⑥配图 ─▶ ⑦草稿箱
                                                                        │
                                            personal: 到此为止，人工发布 ──┘
                                            enterprise+auto: ⑧提交发布 ─▶ ⑨轮询 ─▶ 文章上线
```

## 两种账号形态

| | `personal` 个人公众号 | `enterprise` 企业认证公众号 |
|---|---|---|
| 流程终点 | 草稿箱（人工后台发布） | 可全自动发布 |
| 发布接口 | 无（2025.7 起个人号被回收权限） | `freepublish/submit` + 轮询 |
| 数据回流 | 人工补录（`autopilot stats`） | 同左（datacube 自动拉取规划中） |
| AI 味超标时 | 标黄，人工审核重点看 | 自动降级为只推草稿 |
| 适用场景 | 有质量/合规安全垫的半自动 | 全自动日更 |

> **「发布」≠「群发」**：本项目自动化的「发布」指文章正式发表（出现在公众号主页、可搜索可分享）；**不会推送到粉丝会话**。群发（订阅号 1 次/天、服务号 4 次/月）不在自动化范围，需要推粉丝请在后台手动操作。

## 快速开始

要求：Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)、一个微信公众号（后台能拿到 AppID/AppSecret）。

```bash
git clone https://github.com/<you>/wechat-mp-autopilot.git
cd wechat-mp-autopilot
uv sync

uv run autopilot init        # 生成 config.toml + .env 并给出填写指引
$EDITOR .env config.toml     # 填密钥与账号定位
uv run autopilot verify      # 自检：配置 + 微信/模型连通性 + 权限探测
uv run autopilot run --direction "你的选题方向"
```

跑完后：个人号去公众号后台草稿箱过目发布；企业号（`mode="auto"`）等待自动发布完成，`runs/<日期-slug>/` 里能看到文章链接。

别忘了：**公众号后台「设置与开发 → 基本配置 → IP 白名单」加入运行机出口 IP**，否则 token 获取报 40164。

### 日常命令

```bash
uv run autopilot run --direction "AI 编程工具实测"          # 全流程
uv run autopilot run --resume runs/2026-10-01-xxx --from humanize   # 从某步重跑
uv run autopilot run --topic-only --direction "..."         # 只要选题
uv run autopilot verify --with-publish                      # 企业号全链路实测（发测试文后即删）
uv run autopilot status --run runs/xxx                      # 补查自动发布的轮询状态
uv run autopilot unpublish --run runs/xxx                   # 回滚误发（freepublish/delete）
uv run autopilot stats --run runs/xxx --day 3               # 人工补录第 3 天阅读数据
```

### 定时（固定服务器）

```bash
# crontab -e ：每天 08:00 跑一篇
0 8 * * * cd /opt/wechat-mp-autopilot && uv run autopilot run >> logs/cron.log 2>&1
```

Docker 方式见 `docker-compose.yml`。

## 配置一览（config.toml）

完整模板见 [`config.example.toml`](config.example.toml)，关键项：

| 配置 | 说明 |
|---|---|
| `[account].type` | `personal` / `enterprise`，决定流程终点 |
| `[publish].mode` | `draft`（默认）/ `auto`；联锁：`auto` 仅 enterprise 可用，配错启动即报错 |
| `[publish].max_per_day` | 自动发布自我频控上限 |
| `[publish].ai_disclosure` | 摘要与文末自动加「AI 辅助创作」标识（默认开） |
| `[llm]` | base_url / model / temperature / api_key_env，任意 OpenAI 兼容端点 |
| `[llm.writer]` 等环节覆盖 | 可单独给写作环节换更强的模型 |
| `[niche]` | 账号定位（领域/读者/人设/方向池）——选题质量的上限由它决定 |
| `[style].preset` | 写作风格：`wenyi` 文艺 / `ganhuo` 干货 / `youmo` 幽默 |
| `[style].template` | 排版模板：`clean` / `wenyi` |

敏感值（AppSecret、各家 API key）只存环境变量名，实际值放 `.env`（已 gitignore）。

## 自定义 prompt 与范文

- 内置 prompt 在 `prompts/`，版本记录在 `prompts/_meta.json`（每篇 run 会快照所用版本）
- **你的私货放 `prompts/user/`**（已 gitignore）：同名文件优先于内置目录。写作质量的捷径是把自己的代表作放进 `prompts/user/writer.<风格>.md` 做 few-shot——示例比形容词管用

## 兼容性矩阵

实测状态随社区反馈更新（欢迎提交 [实测报告](.github/ISSUE_TEMPLATE/live_test_report.md)）：

| 路径 | 状态 |
|---|---|
| 个人号：token / 素材 / 草稿推入 | 代码就绪，待作者实测（M0） |
| 企业认证号：草稿推入 | 代码就绪，待社区实测 |
| 企业认证号：freepublish 全自动发布 | 按官方文档实现 + fixture 单测，**待社区实测** |

`autopilot verify` 会在**你的账号上**实际探测权限——那才是权威，矩阵只是参考。

## 合规须知（务必阅读）

- **AI 内容标识**：《人工智能生成合成内容标识办法》（2025.9 施行）要求标识 AI 生成内容。人工发布时请在后台勾选「AI 生成」声明；`auto` 模式下 API 无法勾选该声明，本项目默认在摘要与文末自动加「AI 辅助创作」文字标识（`ai_disclosure`），请勿关闭后隐瞒 AI 属性
- **内容责任**：自动发布没有人工闸门，发布内容的责任在你。建议保持 `max_per_day ≤ 1`，先以 `draft` 模式观察产出质量再开 `auto`
- **图片版权**：仅使用 Pexels（无版权图库），不爬搜索引擎图片
- **平台规则**：纯 AI 批量低质产出可能被平台判定营销号/限流，AI 味超标自动降级只是底线，不是免死金牌

## 开发

```bash
uv sync                       # 安装依赖（含 dev）
uv run pytest                 # 单测：配置联锁 / AI味检测器 / 渲染器 / 微信 client（fixture 驱动，不发真实请求）
```

架构与决策记录见 [docs/plan.md](docs/plan.md)。

## License

[MIT](LICENSE)
