import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings, APP_VERSION
from app.core.account_pool import account_pool
from app.core.auth import verify_api_key
from app.core.fingerprint.version_sync import version_sync_loop
from app.core.usage_stats import UsageStatsStore
from app.core.usage_timer import snapshot_loop
from app.core.log_store import LogStore, create_log_record
from app.routers import openai, claude, gemini, research
from app.routers import admin
from app.routers import logs as logs_router
from app.routers import usage_stats as usage_stats_router
from app.routers import settings as settings_router
from app.routers import api_keys as api_keys_router
from app.routers import model_mapping as model_mapping_router
from app.core.api_key_store import ApiKeyPool
from app.core.model_mapping import ModelMapping

STATIC_DIR = Path(__file__).parent.parent / "static"

log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
logging.getLogger("app").setLevel(log_level)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    logger.info(f"API Key: {settings.api_key}")
    await account_pool.initialize()

    app.state.log_store = LogStore()
    app.state.api_key_pool = ApiKeyPool()
    app.state.model_mapping = ModelMapping()

    async def log_flush_loop():
        while True:
            await asyncio.sleep(10)
            app.state.log_store.flush()

    log_flush_task = asyncio.create_task(log_flush_loop())

    async def image_cleanup_loop():
        from app.core import image_store
        while True:
            try:
                image_store.cleanup_old()
            except Exception as e:
                logger.warning(f"[image_store] 清理异常: {e}")
            await asyncio.sleep(6 * 3600)  # 每 6 小时清一次过期生成图片

    image_cleanup_task = asyncio.create_task(image_cleanup_loop())

    async def web_chat_cleanup_loop():
        # 定时清理 Gemini 网页端堆积的会话（API 每次对话都会在网页端留记录）。
        # 保留窗口 >> 反代上下文窗口(6h)，不会误删正在续接的活跃对话；置顶可保留。
        interval = max(1, settings.chat_cleanup_interval_hours) * 3600
        while True:
            await asyncio.sleep(interval)
            try:
                results = await account_pool.cleanup_web_chats(
                    keep_hours=settings.chat_cleanup_keep_hours,
                    skip_pinned=settings.chat_cleanup_skip_pinned,
                )
                total_deleted = sum(r.get("deleted", 0) for r in results if isinstance(r, dict))
                if total_deleted:
                    logger.info(f"[web_chat_cleanup] 清理网页会话 {total_deleted} 个")
            except Exception as e:
                logger.warning(f"[web_chat_cleanup] 清理异常: {e}")

    web_chat_cleanup_task = None
    if settings.chat_cleanup_enabled:
        web_chat_cleanup_task = asyncio.create_task(web_chat_cleanup_loop())
        logger.info(
            f"Web chat cleanup loop started "
            f"(keep {settings.chat_cleanup_keep_hours}h, every {settings.chat_cleanup_interval_hours}h)"
        )

    version_task = None
    if settings.version_sync_enabled:
        version_task = asyncio.create_task(version_sync_loop())
        logger.info("Chrome version sync task started")

    snapshot_task = None
    if settings.usage_stats_enabled:
        store = UsageStatsStore(retention_days=settings.usage_stats_retention_days)
        app.state.usage_stats_store = store
        snapshot_task = asyncio.create_task(
            snapshot_loop(store, account_pool, interval=settings.usage_stats_interval)
        )
        logger.info("Usage stats snapshot loop started")

    yield

    logger.info("Shutting down...")
    log_flush_task.cancel()
    try:
        await log_flush_task
    except asyncio.CancelledError:
        pass
    image_cleanup_task.cancel()
    try:
        await image_cleanup_task
    except asyncio.CancelledError:
        pass
    if web_chat_cleanup_task:
        web_chat_cleanup_task.cancel()
        try:
            await web_chat_cleanup_task
        except asyncio.CancelledError:
            pass
    app.state.log_store.flush()
    if snapshot_task:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
    if version_task:
        version_task.cancel()
        try:
            await version_task
        except asyncio.CancelledError:
            pass
    await account_pool.shutdown()


app = FastAPI(
    title="Gemini2API",
    description="Gemini Web to API proxy",
    version=APP_VERSION,
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

if settings.rate_limit_enabled:
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"error": {"message": "Rate limit exceeded", "type": "rate_limit"}},
        )


SKIP_LOG_PREFIXES = ("/static/", "/favicon.ico", "/admin/logs")


@app.middleware("http")
async def log_capture_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in SKIP_LOG_PREFIXES):
        return await call_next(request)

    import time
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000

    method = request.method
    status = response.status_code

    is_api = path.startswith(("/openai/", "/claude/", "/gemini/", "/v1/", "/v1beta/"))
    if not is_api and not path.startswith("/admin/"):
        return response

    direction = "egress" if path.startswith(("/v1beta/", "/gemini/")) else "ingress"

    model = None
    stream = None
    if hasattr(request.state, "_body_cache"):
        import json
        try:
            body = json.loads(request.state._body_cache)
            model = body.get("model")
            stream = body.get("stream")
        except Exception:
            pass

    error_msg = None
    if status >= 400:
        error_msg = f"HTTP {status}"

    log_store = request.app.state.log_store
    record = create_log_record(
        method=method,
        path=path,
        direction=direction,
        model=model,
        status=status,
        latency_ms=latency_ms,
        stream=stream,
        error=error_msg,
    )
    log_store.add(record)

    return response

app.include_router(openai.router, prefix="/openai/v1")
app.include_router(openai.router, prefix="/v1")  # 标准 OpenAI 路径，兼容 OpenClaw 等客户端

# Claude：完整端点挂 /claude/v1；裸 /v1 仅暴露对话入口（messages），
# 模型列表 models_router 不挂裸 /v1，避免 /v1/models 与 OpenAI 撞车
app.include_router(claude.models_router, prefix="/claude/v1")
app.include_router(claude.router, prefix="/claude/v1")
app.include_router(claude.router, prefix="/v1")  # 标准 Claude 路径（/v1/messages），兼容 Claude 官方 SDK

# Gemini：/v1beta 与 /v1 不同段，完整端点可同时挂 /gemini/v1beta 和裸 /v1beta
app.include_router(gemini.router, prefix="/gemini/v1beta")
app.include_router(gemini.router, prefix="/v1beta")  # 标准 Gemini 路径，兼容 Gemini 官方 SDK
app.include_router(research.router)
app.include_router(admin.router)
app.include_router(logs_router.router)
app.include_router(usage_stats_router.router)
app.include_router(settings_router.router)
app.include_router(api_keys_router.router)
app.include_router(model_mapping_router.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "gemini2api"}


@app.get("/images/{image_id}")
async def serve_generated_image(image_id: str):
    """提供 AI 生成图片的访问（供对话接口返回可渲染 URL）。"""
    from app.core import image_store
    path = image_store.get_image_path(image_id)
    if not path:
        return JSONResponse(status_code=404, content={"error": "image not found"})
    return FileResponse(path, media_type=image_store.content_type_for(image_id))


@app.get("/login.html")
async def login_page():
    login_file = STATIC_DIR / "login.html"
    if login_file.exists():
        return FileResponse(login_file, media_type="text/html")
    return HTMLResponse("<h1>Login page not found</h1>", status_code=404)


@app.get("/index.html")
async def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    return HTMLResponse("<h1>Panel not found</h1>", status_code=404)


API_DIR = Path(__file__).parent.parent / "api"

app.mount("/api-assets", StaticFiles(directory=str(API_DIR)), name="api-assets")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
