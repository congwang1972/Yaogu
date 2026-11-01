"""应用装配。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core import config, db
from src.core.logging import get_logger, setup_logging
from src.api.routes import api_router
from src.services import watch_pool_service
from src.tasks import scheduler

logger = get_logger(__name__)

FRONTEND_DIST = config.BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db.init_db()
    logger.info("[DEBUG] 数据库就绪 | path=%s", config.DB_PATH)
    if config.SCHEDULER_ENABLED:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="妖股选股系统", version="1.0.0", lifespan=lifespan)
app.include_router(api_router)


def _error(status: int, code: str, message: str, detail: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "VALIDATION_ERROR", "请求参数不合法", {"errors": exc.errors()})


@app.exception_handler(watch_pool_service.PoolError)
async def pool_exception_handler(request: Request, exc: watch_pool_service.PoolError) -> JSONResponse:
    status = 409 if isinstance(exc, (watch_pool_service.PoolFull, watch_pool_service.AlreadyInPool)) else 400
    if isinstance(exc, watch_pool_service.PoolNotFound):
        status = 404
    return _error(status, type(exc).__name__.upper(), str(exc))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("[DEBUG] 未处理异常 | path=%s error=%s", request.url.path, exc)
    return _error(500, "INTERNAL_ERROR", "服务器内部错误，请查看日志")


# 生产环境由 Nginx 托管静态资源；本地直接访问后端时也能打开构建产物。
# 用通配路由而不是 StaticFiles 挂载，是为了让 /pool 这类前端路由刷新时不 404。
if FRONTEND_DIST.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            # 未匹配的 API 必须保持 404，不能被 SPA 兜底成 200
            raise HTTPException(status_code=404, detail="接口不存在")
        root = FRONTEND_DIST.resolve()
        target = (root / full_path).resolve()
        if target.is_file() and root in target.parents:
            return FileResponse(target)
        return FileResponse(root / "index.html")
