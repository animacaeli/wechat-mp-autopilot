# Changelog

本项目的显著变化记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- `autopilot schedule` 常驻定时写作：每日 HH:MM 自动产出，方向池按日轮换，单日失败不退出（容器部署免宿主 cron）
- tag 发布流水线（docker.yml）：`v*` tag → ghcr.io 多架构镜像（amd64/arm64）+ GitHub Release，镜像 tag 规则 `v0.1.0 → :0.1.0/:0.1/:latest`
- docker-compose 支持 `docker compose pull` 直接拉取已发布镜像

### Added
- 自动分节保底：写作产物无小标题时由 LLM 插入意象式标题行（ensure_headings，带防篡改校验）
- gen 配图新增小节装饰条：复用封面图案与配色渲染 900×200，插在每个二级标题后（最多 3 张）
- skill 供给体系：各阶段能力支持 drop-in SKILL.md（含捆绑资源自动拼接），内置 prompts 降级为兜底，prompts/user/ 为补充说明层
- `autopilot skills` 命令：查看各阶段实际能力来源
- AI 生成封面（gen provider，默认）：LLM 美术指导（6 图案 × 3 色配色）+ Pillow 程序化渲染，同标题种子固定
- 密钥双通道：config.toml 直接填值或 `*_env` 环境变量引用（环境变量优先）
- 工程化：GitHub Actions CI（lint / 3.11-3.13 矩阵测试 / pip-audit）、Makefile、pre-commit + pre-push、ruff
- Docker 部署（含 CJK 字体）、docker-compose
- verify 权限探测与 `--with-publish` 全链路实测（发测试文后即删）

## [0.1.0] - 2026-10-02

### Added
- 七阶段流水线：选题 → 写作 → 去AI味 → 标题 → 排版 → 配图 → 草稿箱 →（企业认证号）freepublish 全自动发布
- 双账号形态（personal / enterprise）与发布模式联锁校验（fail fast）
- 微信薄 client：token 缓存与自动刷新、素材/草稿/发布接口、错误码操作指引（40164/48001 等）
- LLM 封装：任意 OpenAI 兼容端点、按环节覆盖模型参数
- AI 味规则检测器（0~100 指数），auto 模式超标自动降级为只推草稿
- 产物落盘 runs/日期-slug/ 与 `--from` 断点重跑
- M0/M1 在个人订阅号实测闭环（首篇 AI 产出文章入草稿箱）
