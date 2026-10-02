# wechat-mp-autopilot — 公众号 AI 自动化写作流水线（开源项目计划）

> 状态：**已确认 v0.3**（2026-10-01 审核通过，开发启动）
> v0.1 → v0.2：定位开源项目、固定服务器部署、双账号类型（企业号可全自动发布）、全配置驱动
> v0.2 → v0.3 变化：确立「什么类型都有可能」原则——项目不对任何具体账号类型做设计假设，账号真实权限一律以 `autopilot verify` 运行时探测为准；企业发布路径按文档 + fixture 用例实现，靠社区实测闭环
> 实施进度（2026-10-01）：M0+M1 代码骨架已落地（七阶段流水线、verify 自检、31 项单测/集成测试全绿、Docker/README/issue 模板）；待办＝真实个人号跑 `autopilot verify` + `run` 完成 M0 实测闭环
> 审核方式：直接在本文档上批注，或逐条回复「需要你确认的决策点」（见第 10 节）

## 1. 项目目标

一个开源的公众号 AI 自动化写作流水线，部署在固定服务器上，全自动完成内容生产链路：

**选题 → 写作 → 去 AI 味 → 标题优化 → 排版渲染 → 配图 → 推入草稿箱 →（企业号）自动发布**

两种运行形态，由配置决定，代码同一套：

| 账号类型 | 流程终点 | 说明 |
|---|---|---|
| `personal`（个人公众号） | 草稿箱 | 2025.7 起个人号无发布 API 权限，人工在后台确认发布（也是质量与合规的安全垫） |
| `enterprise`（企业认证公众号） | **发布** | 草稿推入后自动调 `freepublish/submit` 提交发布，轮询直至拿到正式文章链接 |

每天的目标：定时任务跑完后——个人号模式，草稿箱里躺着 1 篇排版配图齐全的文章等人过目；企业号模式，文章已自动发布并可分享。

开源项目意味着：**一切账号相关、模型相关的差异都收敛到 `config.toml`**，仓库不含任何私货，别人 clone 下来填好自己的配置就能跑。

## 2. 约束与前提

### 2.1 账号类型相关约束

| 约束 | 影响 | 应对 |
|---|---|---|
| 个人主体账号，2025.7 起无 `freepublish` 发布接口权限 | 不能全自动发布 | `account.type = personal` 时流程终点为草稿箱 |
| 企业**认证**公众号（订阅号/服务号均可）有发布能力接口 | 可全自动发布 | `account.type = enterprise` + `publish.mode = auto` 解锁 |
| 各接口实际权限以后台「设置与开发 → 接口权限」页为准 | 文档与实际可能有出入，且开源用户的账号情况不可知 | 提供 `autopilot verify` 自检命令，运行时探测是权威（见下方原则） |
| access_token 获取需 IP 白名单 | 出口 IP 必须固定 | 已定：固定服务器部署，白名单配服务器出口 IP |
| 正文图片仅允许微信域名 URL | 不能外链图床 | 所有图片先经微信素材接口换 URL |
| AI 生成内容需标识（《人工智能生成合成内容标识办法》2025.9 施行） | 合规义务 | 见 2.3 |

> **「什么类型都有可能」原则**：这是开源项目，用户可能带着个人号、企业认证号、甚至未认证企业号等边缘情况来，设计不能假设任何一种。因此：
> ① personal / enterprise 两种形态都是一等公民，同等实现、同等文档化；
> ② 权限是否存在，一律以 `autopilot verify` 在**用户自己账号上实际探测**的结果为准，不以作者账号情况或文档描述为准；
> ③ 权限不足的错误码（如 48001）必须翻译成具体的后台操作指引，而不是让用户猜。

### 2.2 「发布」≠「群发」（对齐预期，重要）

- **发布**（`freepublish/submit`）：文章正式发表，出现在公众号主页/历史消息，可被搜索、分享；**不推送粉丝会话**。本项目 auto 模式自动化的就是这一步。
- **群发**（`message/mass/sendall` 或后台手动）：推送到粉丝会话，占用群发次数（订阅号 1 次/天、服务号 4 次/月），监管敏感度更高。
- 群发不在自动化范围内，需要推粉丝时在后台手动操作。远期是否接群发 API，等真实需求出现再议。

### 2.3 AI 标识合规

- 人工发布模式（personal）：SOP 第一条就是后台勾选「AI 生成」声明。
- 自动发布模式（enterprise）：后台发表流程里的声明勾选**无法通过 API 完成**（以后台实测为准），因此兜底方案是 `publish.ai_disclosure = true`（默认开）：自动在摘要尾部/文末加「本文 AI 辅助创作」文字标识。

## 3. 技术选型

**语言：Python（已定）**。本项目是 IO 胶水 + prompt 迭代 + HTML 拼装，无性能敏感点；LLM/HTML/图库生态全是 Python 一等公民。

| 组件 | 选择 | 理由 |
|---|---|---|
| LLM 调用 | `openai` SDK + **可配置 base_url** | 任意 OpenAI 兼容端点（DeepSeek / GLM / OpenAI / 本地 vLLM）即插即用，模型与参数全部来自 config |
| 公众号 API | 自封薄 client（`httpx`，约 10 个接口） | 接口面小，自封比引 wechatpy 更可控、依赖更少 |
| 排版 | Jinja2 模板 + markdown→HTML 转换 | 模板版本化，多套风格可切换 |
| 图片处理 | Pillow + 多 provider（默认 gen：LLM 美术指导 + 程序化渲染） | Pexels 2025 起停发新 key，海外图库国内不可达；详见 6.6 |
| 数据存储 | SQLite | 数据回流记录，零运维 |
| 调度 | 系统 cron / systemd timer | 应用本身无内嵌调度（YAGNI），一行 crontab 搞定定时 |
| 部署 | Docker（内置 uv）或裸机 uv | 固定服务器两种方式都文档化 |
| 包管理 | `uv` | 快、锁版本 |

**刻意不做的事**（YAGNI）：

- 不引入 LangChain / CrewAI 等编排框架——流程是线性的，纯函数式管道更透明可调试
- 不做 Web 管理界面——CLI + 文件落盘足够
- 不做多账号并发——一份配置对应一个号，跑多号就部署多实例
- 不做群发自动化——见 2.2

## 4. 配置设计（本项目的门面）

所有账号差异、模型差异收敛于一个 `config.toml`。仓库内提交 `config.example.toml` 作为文档与模板，真实 `config.toml` 与 `.env` 均 gitignore。**密钥双通道**：直接填值（单文件快速上手）或 `*_env` 引用环境变量（适配 Docker env_file / systemd / CI secrets，且避免误提交）；两者都配时以环境变量优先。

```toml
# config.example.toml — 复制为 config.toml 后填写

# ── 公众号账号 ──────────────────────────────────────────
[account]
type = "personal"          # personal  = 个人公众号（流程终点：草稿箱）
                           # enterprise = 企业认证公众号（可开全自动发布）

[wechat]
app_id_env     = "WECHAT_APP_ID"
app_secret_env = "WECHAT_APP_SECRET"

# ── 发布策略 ────────────────────────────────────────────
[publish]
mode = "draft"             # draft = 推入草稿箱即止（两类账号均可，默认值）
                           # auto  = 草稿→freepublish/submit→轮询至发布成功
                           #        联锁：仅 enterprise 可用，personal 配 auto 启动即报错（fail fast，不静默降级）
poll_interval_sec = 30     # auto：freepublish/get 轮询间隔
poll_timeout_min  = 60     # auto：轮询超时（超时≠失败，publish_id 落盘可事后查询）
max_per_day = 1            # 自我频控：单日发布次数上限，防失控
ai_disclosure = true       # 自动在摘要/文末加「AI 辅助创作」标识（合规兜底）

# ── 大模型（任意 OpenAI 兼容端点，参数全在这里）──────────
[llm]
base_url    = "https://api.deepseek.com/v1"
api_key_env = "LLM_API_KEY"
model       = "deepseek-chat"
temperature = 0.7
max_tokens  = 4096
timeout_sec = 120

# 可选：按流水线环节覆盖（缺省继承 [llm]，实现「写作用强模型、其余用便宜模型」）
[llm.writer]
# model = "deepseek-reasoner"
temperature = 1.0

# ── 账号定位（选题 agent 的核心输入）────────────────────
[niche]
field      = "AI 编程工具与效率"   # 写什么领域
audience   = "一线开发者"          # 给谁看
persona    = ""                    # 差异化人设一句话
directions = []                    # 常备选题方向池（可留空，运行时 --direction 传入）

# ── 风格与排版 ──────────────────────────────────────────
[style]
preset   = "ganhuo"         # wenyi | ganhuo | youmo（对应 prompts/writer.*.md）
template = "clean"          # templates/ 下的 Jinja2 模板名

# ── 配图 ────────────────────────────────────────────────
[images]
provider         = "pexels" # M3 预留：pexels | cogview（生图）
pexels_api_key_env = "PEXELS_API_KEY"
fallback_plain   = true     # 取图失败降级为纯文字排版，不阻塞流程
```

```bash
# .env.example
WECHAT_APP_ID=wx1234
WECHAT_APP_SECRET=…
LLM_API_KEY=sk-…
PEXELS_API_KEY=…
```

配置加载时做三类校验（`config.py`）：必填项齐全、环境变量能取到值、`publish.mode` 与 `account.type` 的联锁。任何一条不过，启动即报错并指出改哪里。`account.type` 本质是用户对自己账号情况的**声明**（用于联锁与文档引导），权威永远是 `verify` 的实测结果——不符合文档画像的边缘账号，按 verify 输出调整配置即可。

## 5. 总体架构

### 5.1 流水线

```
                    ┌──────────────────────────────────────────────────────────┐
                    │  config.toml + .env（账号类型/发布模式/模型参数/定位风格）     │
                    └──────────────────────────┬───────────────────────────────┘
                                               ▼
  方向输入(手动/热榜) ──▶ ① 选题 agent ──▶ ② 写作 agent ──▶ ③ 去AI味 agent
                                            (风格参数化)      (rewrite+规则检测)
                                                                     ▼
  ┌── personal: 到此为止，人工后台发布 ─────────────────────────────────────────┐
  │ 草稿箱 ◀── ⑦ draft/add ◀── ⑥ 配图+上传 ◀── ⑤ 排版渲染 ◀── ④ 标题 agent      │
  │  (media_id)                 (uploadimg/      (Jinja2→微信       (10候选+打分) │
  │                              永久素材)         兼容HTML)                        │
  │                                                                              │
  └── enterprise + auto: 继续 ──▶ ⑧ freepublish/submit ──▶ ⑨ 轮询 freepublish/get
                                 (publish_id)              (0成功/1进行中/3,4失败)
                                                                     │
                                  文章正式发布（公众号主页可访问）◀────┘
                                                                     ▼
  ⑩ 数据回流：enterprise 走 datacube 接口自动拉阅读数据；personal 人工补录 → SQLite → 反哺选题与标题 prompt
```

### 5.2 核心设计：产物落盘 + 断点重跑

每篇文章一个独立工作目录 `runs/YYYY-MM-DD-slug/`，每步产物依次落盘：

```
runs/
└── 2026-10-01-claude-code-tips/
    ├── 01_topics.json        # 3 个候选选题（含打分与选择理由）
    ├── 02_draft.md           # 写作初稿
    ├── 03_humanized.md       # 去 AI 味后正文
    ├── 03_report.json        # AI 味检测报告（指数、命中的模式）
    ├── 04_titles.json        # 10 个标题候选 + 打分 + 最终选择
    ├── 05_article.html       # 渲染后的微信兼容 HTML
    ├── 06_meta.json          # 摘要、封面 media_id、正文图片清单
    ├── 07_draft_result.json  # 草稿 media_id、上传时间、prompt 版本快照
    ├── 08_publish_result.json# 仅 auto 模式：publish_id、轮询结果、article_url
    └── 09_stats.json         # 阅读数据（enterprise 自动拉 / personal 人工补录）
```

好处：
- 任一步不满意可 `--from humanize` 从该步重跑，不用从头来
- 人工审核时直接看落盘文件，不必信任黑盒
- 每篇记录所用 prompt 版本号，与阅读数据一起构成迭代闭环
- auto 模式轮询超时后，凭落盘的 `publish_id` 可随时补查状态

### 5.3 CLI 形态（拟）

```bash
uv run autopilot init                                # 首跑向导：交互式生成 config.toml（账号类型/定位/风格/模型逐项填）
uv run autopilot verify                              # 自检：配置校验 + 逐项探测 token / draft / freepublish 实际权限
uv run autopilot verify --with-publish               # 企业号用户可选全链路实测：发一篇测试草稿→提交发布→立即删除
uv run autopilot run --direction "AI 编程工具实测"    # 全流程，终点由 config 决定
uv run autopilot run --publish draft                 # 临时覆盖发布模式（企业号只推草稿时用）
uv run autopilot run --resume runs/2026-10-01-xxx --from humanize
uv run autopilot run --topic-only                    # 只要选题，人工定方向再写
uv run autopilot status --run runs/xxx               # 补查 auto 发布的轮询状态
uv run autopilot stats --run runs/xxx                # personal 模式人工补录阅读数据
```

## 6. 模块设计

### 6.1 选题模块

- **输入**：config 的 `[niche]`（领域、读者、人设、方向池）+ 方向（手动给定或热榜）
- **输出**：3 个候选选题 JSON：`{标题方向, 目标读者, 切入点, 预估点击理由, 内容风险, 评分}`
- **评分**：LLM 按「点击欲 × 与账号定位匹配度 × 可写性」打分，默认自动取最高分，`--pick 2` 可人工指定
- **热榜**：M3 再接（微博/知乎/百度热榜 + 与定位的相关性过滤）。一期手动给方向，避免为抓热点而跑偏

### 6.2 写作模块

- 风格参数化，config `[style].preset` 选择，prompts 目录放 3 套预设：
  - `wenyi`（文艺风）：叙事开头、意象化小标题、克制的抒情、长短句交错
  - `ganhuo`（干货风）：痛点开头、步骤化、重点加粗、每段有信息增量
  - `youmo`（幽默风）：自嘲开头、口语化、梗密度适中
- 结构约束写进 prompt：开头 3 句内出钩子；段落 3~5 行；全文 1200~1800 字；结尾金句或留白，不强行升华
- 每套风格配 2~3 篇人工挑选的范文做 few-shot 锚定（风格这事，示例比形容词管用）

### 6.3 去 AI 味模块（本项目质量关键）

两部分：LLM 重写 pass + 规则检测器。

**中文 AI 味清单**（汉化自本地 humanize-writing skill + 中文特有模式，作为 prompt 主体）：

| 类别 | 典型特征 |
|---|---|
| 公式化结构 | 首先/其次/最后；总而言之；每节结尾强行总结升华；排比三连（第三项凑数） |
| 八股词汇 | 赋能、闭环、抓手、深耕、破圈、生态、不难发现、值得注意的是、综上所述、在……的今天 |
| 句式惯性 | 「不是X，而是Y」高频出现；「与其说……不如说……」；破折号插语滥用；空洞让步（「虽然……但……」套娃） |
| 节奏 | 句子长度均一（全是 15~25 字）；没有短句；每句都以名词开头 |
| 空洞指称 | 「业内人士表示」「有观点认为」；无出处的「研究表明」 |
| 结尾套路 | 「未来可期」「让我们拭目以待」式的万能收尾 |

**规则检测器**（纯 Python 正则，不调 LLM）：

- 黑词表命中计数、排比密度、破折号/感叹号密度、「首先…其次」结构检测
- 输出 0~100 的「AI 味指数」+ 命中明细，写入 `03_report.json`
- 指数超阈值自动触发一次二次重写；仍超标则标黄，人工审核时重点看
- **auto 发布模式下的额外闸门**：指数仍超标时默认不自动提交发布（降级为只推草稿），可配置

### 6.4 标题模块

- 一次生成 10 个候选：5 种套路（痛点/数字/悬念/反差/身份代入）× 各 2 个
- 约束：15~25 字优先（公众号 64 字上限，但信息流截断在 ~30 字）
- LLM 按「信息流场景下的点击欲」打分取 top1，top2/top3 存入 meta 供人工换用

### 6.5 排版模块

- Jinja2 模板 2 套起（`wenyi`：衬线字体、大留白、细分隔线；`clean`：主题色块、圆角卡片、要点高亮）
- 微信编辑器兼容约束（模板中强制遵守）：
  - 仅 inline style，无 class / 外部 CSS / JS
  - 结构用 `<section>` 嵌套（135编辑器同款做法）
  - 字号 15~16px、行高 1.75、段间距 margin 控制
  - 代码块：`<pre>` + inline style 模拟（背景色 + 等宽字体），内容 HTML 转义
- markdown → HTML：用 `mistune`（或 `markdown-it-py`）+ 自定义渲染器输出微信兼容标签，再套 Jinja2 外壳

### 6.6 配图模块

**背景变化（2026-10）**：Pexels 官方已暂停发放新 API key，且实测海外图库（openverse/pixabay/pexels/unsplash）在国内网络均不可直达。因此配图改为多 provider 架构（config `images.provider`）：

| provider | 说明 |
|---|---|
| `gen`（默认） | **AI 生成封面**：LLM 当美术指导（`cover.designer.md` prompt 从 6 种图案库选型、按主题定 3 色配色），本地 Pillow 程序化渲染——文本模型不能直接吐图，但选型与配色正是它擅长的；零图库依赖、国内可达、无版权；同标题种子固定重跑不换脸 |
| `local` | 本地固定渐变底 + 标题字，连 LLM 设计环节也省了（最省最稳的兜底） |
| `openverse` | 免 key 开放图库（检索限定 CC0/PDM，可商用免署名），需网络可达或代理 |
| `pixabay` | 免费 key（仍在发放），图片质量更佳，需网络可达或代理 |
| `pexels` | 仅已有 key 的老用户可用（官方停发新 key） |

- **封面**：gen 设计渲染（或取图）→ 叠加标题字 → 上传永久素材拿 `thumb_media_id`
- **正文点缀**：仅远程图库 provider 配 1 张（关键词取图 → `media/uploadimg` 换微信 URL → 插入 HTML 约 40% 处）；gen/local 不配正文图
- **降级链**：LLM 设计失败 → 内置默认设计；远程取图失败 → 本地渐变封面；封面素材是 `draft/add` 必需品，thumb_media_id 永不为空
- M3 接生图模型（CogView / 通义万相）做像素级风格化插画（国内可达、无版权），与 gen 的「美术指导」路线并存

### 6.7 草稿与发布模块（wechat 薄 client）

封装以下接口，全部带重试与错误码解释：

| 接口 | 用途 | 可用性 |
|---|---|---|
| `GET /cgi-bin/token` | 取 access_token（2h 有效，落盘缓存，过期前 10min 刷新） | 全部 |
| `POST /cgi-bin/media/uploadimg` | 正文图上传，返回微信 URL | 全部 |
| `POST /cgi-bin/material/add_material` | 封面永久素材，返回 media_id | 全部 |
| `POST /cgi-bin/draft/add` | 新增图文草稿 → `media_id` | 全部（M0 实测） |
| `POST /cgi-bin/draft/get` / `draft/count` | 回查草稿、草稿数监控 | 全部 |
| `POST /cgi-bin/draft/delete` | 删除草稿（verify 自检的清理动作） | 全部 |
| `POST /cgi-bin/freepublish/submit` | 提交发布：`draft_id` → `publish_id` | **仅企业认证号** |
| `POST /cgi-bin/freepublish/get` | 轮询发布状态：0 成功（含 article_url）/ 1 进行中 / 3 常规失败 / 4 审核不通过 | 同上 |
| `POST /cgi-bin/freepublish/delete` | 删除已发布文章（测试清理、误发回滚） | 同上 |

发布子流程（仅 `enterprise + auto`）：

1. `draft/add` 拿到草稿 `media_id`（作为 `draft_id`）
2. `freepublish/submit` → `publish_id`，落盘到 `08_publish_result.json`
3. 按 `poll_interval_sec` 轮询 `freepublish/get`，直至状态 0（成功，记录 article_url）或 3/4（失败，标红原因并停止）
4. 状态 4（审核不通过）是终态，不重试；状态 3 可配置重试一次
5. 超时未决：不判失败，run 标记 pending，事后 `autopilot status` 补查
6. 发布前检查 `[publish].max_per_day` 当日已发布数，超限则停在草稿并提示

- `digest`（摘要）由 LLM 生成 120 字内，不留给微信默认截取正文前 54 字
- 常见错误码处理：40164（IP 不在白名单）直接提示操作路径；40007（media_id 无效）自动重传素材；48001（api 未授权）→ 明确提示「当前账号无此权限，请到后台『接口权限』页核对」，并指出与 `account.type` 声明不符
- **client 测试策略**：薄 client 层以官方文档的响应示例做 fixture，单测先行。作者只有个人号可实测，企业发布路径由 fixture 保证代码正确性，README 的兼容性矩阵跟踪「已实测 / 按文档实现」状态，社区用户提交实测报告后更新
- 可选加固（M2）：提交发布前过一遍微信内容安全接口 `msg/sec/check` 做预检

### 6.8 数据回流（M3）

- **enterprise 模式**：微信数据统计接口（datacube 系列，认证号可用）自动拉阅读/分享数据，写入 `09_stats.json`
- **personal 模式**：个人号数据接口权限有限，人工补录——发布后 3 天/7 天把阅读、点赞、在看、转发交互式录入（`autopilot stats --run`）
- SQLite 汇总：`prompt版本 × 选题类型 × 标题套路` 与阅读数据的对应关系
- 月度输出一份「什么选题/标题/风格表现好」的统计报告，作为 prompt 迭代依据

## 7. Prompt 库设计

```
prompts/
├── topic.selector.md    # 选题 agent
├── writer.wenyi.md      # 写作（按风格分文件）
├── writer.ganhuo.md
├── writer.youmo.md
├── humanizer.md         # 去 AI 味（含中文 AI 味清单全文）
├── titlist.md           # 标题
├── digest.md            # 摘要
└── _meta.json           # 各 prompt 版本号（每篇 run 记录快照）
```

- 每个 prompt 只干一件事（单一职责，好定位问题好迭代）
- 写作类 prompt 内嵌 2~3 篇范文 few-shot（**范文属于用户私有内容**，仓库只放示例占位与「如何替换范文」的说明）
- 迭代规则：改 prompt 必升版本号；不删旧版本；效果对比靠 run 目录里的版本快照 + 阅读数据
- **用户覆盖层**：用户自己的范文/prompt 微调放 `prompts/user/`（gitignore），同名文件优先于内置目录——官方仓库更新（git pull）永不与用户私有内容冲突

## 8. 合规与风险

| 风险 | 应对 |
|---|---|
| AI 内容未标识 | personal：人工发布 SOP 第一条勾选「AI 生成」声明；enterprise/auto：`ai_disclosure` 自动加文字标识（API 无法勾选后台声明，见 2.3） |
| 纯 AI 批量产出被判营销号 / 限流 | AI 味指数超标不自动发布；`max_per_day` 自我频控；宁可少发不发水文 |
| auto 模式发布后发现内容有问题 | `freepublish/delete` 回滚；run 目录保留全量证据链 |
| 图片版权 | 仅用可商用免署名来源（openverse 限定 CC0 / pixabay / pexels）或本地生成；不爬搜索引擎图片 |
| 事实性错误 | 写作 prompt 强制「不确定的事实不写具体数字」；人工审核关注点写入 SOP；auto 模式用户自担审核责任（README 明示） |
| token 成本 | 单篇全流程约 6~10 次调用、2~4 万 tokens，Flash 级定价下成本可忽略；run 记录中累计用量 |

## 9. 部署（固定服务器）与里程碑

### 9.1 部署步骤

1. 公众号后台「设置与开发 → 基本配置 → IP 白名单」加入服务器出口 IP
2. 服务器上 `git clone` → `cp config.example.toml config.toml` 填好 → `.env` 填密钥
3. 运行方式二选一：
   - **Docker**：`docker compose run autopilot`（Dockerfile 基于 uv 官方镜像）
   - **裸机**：`uv sync` 后直接 `uv run autopilot …`
4. 定时任务一行 crontab（或 systemd timer）：
   ```
   0 8 * * * cd /opt/wechat-mp-autopilot && . .env && uv run autopilot run >> logs/cron.log 2>&1
   ```

### 9.2 里程碑

| 阶段 | 内容 | 验收标准 | 预估工作量（业余时间） |
|---|---|---|---|
| **M0 连通性验证** | 微信薄 client + `autopilot verify` 自检 | 作者个人号实测 `draft/add` 推草稿成功；企业发布路径以官方文档响应示例做 fixture 单测，README 兼容性矩阵标注「按文档实现，待社区实测」 | 1 个晚上 |
| **M1 最小闭环** | 全 pipeline 到草稿 + 发布路径代码完成；Docker 化；README + 兼容性矩阵 + issue 模板 | 一条命令产出一篇完整草稿（个人号实测）；auto 模式路径实现完整且 fixture 单测通过；发布第一篇正式文章（作者自己的号） | 2 周 |
| **M2 质量打磨与发布加固** | 排版模板美化×2、AI 味检测器调优、封面加字、失败降级、发布轮询超时/失败分类、`msg_sec_check` 预检（可选）、`autopilot init` 首跑向导 | 连续 5 篇产出人工只需微调（改动 < 10%）即可发布；auto 模式失败场景全部有明确状态与日志；新用户从 clone 到产出第一篇草稿只需 init + verify 两步引导 | 2~3 周 |
| **M3 迭代闭环** | datacube 自动回流（enterprise）、prompt 版本对比、热榜接入选题 | 每月一份选题/标题效果报告驱动 prompt 迭代 | 2~3 周 |

M0 放在最前：**在作者自己的真实账号上实测草稿路径**。企业发布路径作者无法实测（没有企业号），走「文档 + fixture + 社区验证」路线：fixture 保证代码逻辑正确，README 兼容性矩阵跟踪实测进度，并提供实测报告 issue 模板供社区的企业号用户反馈。

## 10. 需要你确认的决策点

已定：

- ✅ **运行环境**（v0.2）：固定服务器，Docker 或 cron/systemd 部署，IP 白名单配服务器出口 IP
- ✅ **项目形态**（v0.2）：开源项目，目录 `~/Documents/code/python/wechat-mp-autopilot`，建 git 仓库
- ✅ **双账号类型 + 模型配置**（v0.2）：personal / enterprise 由 `[account].type` 配置，企业号可 `publish.mode = auto` 全自动发布；LLM 参数全在 `[llm]`
- ✅ **什么类型都有可能**（v0.3）：不对任何具体账号类型做设计假设——两种形态一等公民；权限以 `autopilot verify` 运行时探测为准；企业发布路径走「文档 + fixture + 社区实测验证」，不依赖作者持有企业号

**你自己部署时才要填的**（进你本地的 config.toml / prompts/user/，不阻塞项目开发，仓库自带一套可用的内置默认值）：

1. 账号定位与领域 → `[niche]`，仓库带演示默认值 + 各字段说明
2. 风格基调 → `[style].preset`，wenyi / ganhuo / youmo 三套内置全交付
3. 范文 few-shot → 自己的放 `prompts/user/`，仓库带构造示例 + 替换文档
4. 更新频率 → crontab 频率，与项目设计无关

待确认（仅剩两项）：

5. **LICENSE**：默认 MIT（无异议则建仓库时定下）
6. **API key**（你自己的 dogfooding 用）：DeepSeek API key、微信公众号 AppID/AppSecret + IP 白名单（注意本机调试时 IP 不在白名单会 40164，M0 实测在服务器上做，或临时把本机 IP 加进白名单）。图库默认 `local` 免 key；海外图库（openverse/pixabay/pexels）国内不可达需代理，已不作为默认依赖

## 11. 拟定目录结构（M1 落地形态）

```
wechat-mp-autopilot/
├── pyproject.toml          # ruff/pytest 配置 + 清华 PyPI 镜像（国内优先，海外可删）
├── Makefile                # install/test/lint/fmt/audit/precommit/ci
├── .pre-commit-config.yaml # pre-commit: ruff+通用检查；pre-push: 全量测试
├── README.md                # 开源门面：quickstart、双账号模式说明、配置项表、免责声明
├── LICENSE
├── .gitignore               # config.toml / .env / runs/ / data/ / logs/
├── config.example.toml      # 见第 4 节
├── .env.example
├── Dockerfile               # 含 CJK 字体（封面标题叠加依赖）
├── docker-compose.yml
├── .github/
│   ├── workflows/ci.yml     # lint + 3.11/3.12/3.13 矩阵测试 + pip-audit
│   └── ISSUE_TEMPLATE/     # 实测报告 / bug 报告模板（收集企业号用户的验证反馈）
├── autopilot/
│   ├── cli.py               # CLI 入口
│   ├── config.py            # 配置加载 + 校验（含 mode/type 联锁）
│   ├── llm.py               # OpenAI 兼容 client（读 [llm] 与环节覆盖，JSON 输出与重试）
│   ├── wechat/
│   │   ├── client.py        # 薄 API client + token 缓存（草稿 + freepublish）
│   │   └── errors.py        # 错误码解释与处理策略
│   ├── pipeline/
│   │   ├── topics.py        # ① 选题
│   │   ├── writer.py        # ② 写作
│   │   ├── humanizer.py     # ③ 去AI味（LLM rewrite + 规则检测器）
│   │   ├── titlist.py       # ④ 标题
│   │   ├── renderer.py      # ⑤ markdown→微信HTML
│   │   ├── images.py        # ⑥ Pexels取图 + Pillow加工 + 上传
│   │   └── publisher.py     # ⑦ draft/add；auto 模式：⑧submit + ⑨轮询get
│   ├── stats.py             # ⑩ 数据回流（enterprise 自动拉 / personal 人工补录）
│   └── detector.py          # AI 味规则检测器
├── prompts/                 # 内置 prompt 库（见第 7 节），仓库带构造范文示例
│   └── user/                # 用户覆盖层：自己的范文/prompt 微调（gitignore），同名优先于内置
├── templates/               # Jinja2 排版模板（wenyi / clean）
├── tests/                   # 检测器、配置校验、渲染器的单测（CI 跑）
├── runs/                    # 每篇工作目录（gitignore）
└── data/                    # SQLite（gitignore）
```

---

**附 A：人工发布 SOP（personal 模式，发布环节标准动作）**

1. 打开公众号后台 → 草稿箱，找到当天 run 产出的文章
2. 通读全文：重点看事实性表述、AI 味检测标黄的段落、图片与内容相关性
3. 标题/摘要不满意 → 从 `04_titles.json` 的备选中换（后台可直接改）
4. 勾选「AI 生成」声明；原创声明按实际情况
5. 发送手机预览，确认排版在移动端无异常 → 发布
6. 发布后 3 天/7 天回填数据：`uv run autopilot stats --run runs/xxx`

**附 B：auto 发布模式的例行检查（enterprise 模式）**

- 每天看一眼 `logs/` 与最新 run 的 `08_publish_result.json`：发布成功（article_url）、审核不通过（原因）、轮询超时（补查命令）
- AI 味指数超标自动降级为草稿的文章，过目后可手动 `autopilot run --resume … --from publish` 继续提交
- 误发回滚：`autopilot unpublish --run runs/xxx`（封装 `freepublish/delete`）
