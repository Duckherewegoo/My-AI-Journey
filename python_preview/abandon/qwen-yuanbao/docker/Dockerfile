# ============================================================
# Task Planner — 生产 Dockerfile（强化版）
# ============================================================
FROM python:3.11-slim AS base

# ── Python 环境 ──
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# ── 全局 pip 镜像（一劳永逸，不用每次 -i）──
RUN mkdir -p ~/.pip && \
    echo '[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\n[install]\ntrusted-host = mirrors.aliyun.com' > ~/.pip/pip.conf

# ── 系统依赖（cairosvg / Pango / CJK 字体）──
RUN echo 'deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware' > /etc/apt/sources.list && \
    echo 'deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware' >> /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app


# ── 先复制依赖描述文件（利用缓存）──
COPY pyproject.toml ./
COPY requirements.txt ./

# ── 再复制源码（必须在 pip install -e . 之前！）──
COPY src ./src

# ── 安装运行时依赖 ──
RUN pip install --upgrade pip && \
    pip install -e .

# ── 复制测试（可选，生产镜像可以不 COPY tests）──
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


