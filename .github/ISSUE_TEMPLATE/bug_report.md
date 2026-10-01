name: Bug 报告
about: 报告问题前，建议先跑 `uv run autopilot verify` 并附上输出
title: "[Bug] "
labels: bug
body:
  - type: textarea
    id: what
    attributes:
      label: 问题描述
      description: 发生了什么、期望是什么
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: 关键输出 / 错误信息
      render: shell
  - type: textarea
    id: env
    attributes:
      label: 环境
      description: 账号类型、配置（脱敏）、模型端点、部署方式、操作系统
  - type: textarea
    id: repo
    attributes:
      label: 复现步骤
