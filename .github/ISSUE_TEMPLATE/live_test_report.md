name: 实测报告
about: 反馈某条路径在你账号上的实测结果（用于更新兼容性矩阵）
title: "[实测] "
labels: live-test
body:
  - type: markdown
    attributes:
      value: 感谢反馈！实测结论会更新到 README 的兼容性矩阵。
  - type: dropdown
    id: account
    attributes:
      label: 账号类型
      options:
        - 个人公众号（未认证订阅号）
        - 企业认证订阅号
        - 企业认证服务号
        - 其他（请在下面说明）
    validations:
      required: true
  - type: dropdown
    id: path
    attributes:
      label: 实测路径
      options:
        - verify 自检（token / 草稿权限探测）
        - 全流程到草稿箱（draft 模式）
        - freepublish 全自动发布（auto 模式）
        - verify --with-publish 全链路实测
        - 其他
    validations:
      required: true
  - type: textarea
    id: result
    attributes:
      label: 结果与现象
      description: 成功/失败、关键输出（media_id / publish_id / 错误码）、轮询时长等
    validations:
      required: true
  - type: textarea
    id: env
    attributes:
      label: 环境
      description: 版本（git commit）、模型与端点、部署方式（本机/Docker/服务器）
  - type: input
    id: date
    attributes:
      label: 实测日期
      placeholder: "2026-10-01"
