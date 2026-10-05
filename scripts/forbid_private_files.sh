#!/usr/bin/env bash
# 防泄检查：私密/产物文件一旦被 git 跟踪立即失败。
# 动机：.gitignore 曾被无关内容误覆盖，导致 git add -A 把 .env 密钥卷入提交。
# 挂载点：pre-commit 钩子 + GitHub Actions（见 .pre-commit-config.yaml / ci.yml）。
set -euo pipefail

bad=$(git ls-files --cached \
  | grep -E '^\.env$|^\.env\.[^/]+$|^config\.toml$|^runs/|^data/|^logs/|^prompts/user/|__pycache__/|\.pyc$|^\.idea/|^\.DS_Store$|^skills/' \
  | grep -vE '^\.env\.example$|^config\.example\.toml$|^skills/README\.md$' || true)

if [ -n "$bad" ]; then
  echo "✗ 检测到被 git 跟踪的私密/产物文件（仅允许存在于本地）：" >&2
  echo "$bad" >&2
  echo "  先确认 .gitignore 内容完整，再执行：git rm --cached <上述文件>" >&2
  exit 1
fi
echo "✓ 无私密/产物文件被跟踪"
