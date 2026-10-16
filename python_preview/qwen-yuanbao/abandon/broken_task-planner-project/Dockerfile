# ============================================================
# Task Planner — 生产 Dockerfile
# ============================================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# ── 系统依赖（cairosvg / Pango / CJK 字体）──
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    fonts-noto-cjk \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 先复制依赖描述文件（利用 Docker 缓存）──
COPY pyproject.toml ./
COPY requirements.txt ./

# ── 安装运行时依赖 ──
RUN pip install --upgrade pip && \
    pip install -e .

# ── 复制源码 ──
COPY task_planner ./task_planner
COPY tests ./tests

# ── 创建必要目录 ──
RUN mkdir -p logs exports

# ── 暴露端口 ──
EXPOSE 7860

# ── 健康检查 ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# ── 启动 ──
CMD ["python", "-m", "task_planner.app"]
