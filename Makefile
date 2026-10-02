.PHONY: help install test lint fmt audit precommit ci docker-build clean

help: ## 显示本帮助
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖（含 dev 工具）
	uv sync

test: ## 运行测试
	uv run pytest -q

lint: ## ruff 检查（含格式检查）
	uv run ruff check .
	uv run ruff format --check .

fmt: ## ruff 自动修复 + 格式化
	uv run ruff check --fix .
	uv run ruff format .

audit: ## 依赖漏洞扫描（在线查询 PyPI advisory，国内网络可能失败；CI 中自动跑）
	uv export --format requirements-txt --no-dev --no-emit-project -o /tmp/ap-requirements.txt
	uv run pip-audit --disable-pip --no-deps -r /tmp/ap-requirements.txt

precommit: ## 安装 git hooks（pre-commit: lint；pre-push: 测试）
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

ci: lint test audit ## 本地模拟 CI（lint + 测试 + 漏洞扫描）

docker-build: ## 构建镜像
	docker compose build

clean: ## 清理缓存产物
	rm -rf .pytest_cache dist *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
