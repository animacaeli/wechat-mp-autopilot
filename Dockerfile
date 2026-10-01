FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 先装依赖（利用层缓存），再拷代码
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "autopilot", "--help"]
