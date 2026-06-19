FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY static/ ./static/
# 烘焙 api/ 热更新资源（QR 配置/图片）进镜像，使镜像自包含：
# 即使 docker run 不挂载 ./api:/app/api，/app/api 也存在，避免 StaticFiles 启动崩溃；
# compose 的 bind mount 仍可在运行时覆盖这些默认资源。
# 注意：仓库 .dockerignore 默认排除 api，发布流水线会在构建前临时取消该排除。
COPY api/ ./api/

# 非 root 运行：缩小容器被攻破后的影响面（VULN 加固）。
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5918

# 镜像内健康检查：plain docker run 也能获得 liveness 信号（compose 另有 healthcheck）。
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q -O /dev/null http://localhost:5918/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5918"]
