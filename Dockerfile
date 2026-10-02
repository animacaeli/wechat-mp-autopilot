FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# CJK 字体：封面标题叠加文字依赖（slim 基础镜像不带任何中文字体）
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存），再拷代码
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "autopilot", "--help"]
