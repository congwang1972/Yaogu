"""路由聚合。"""
from fastapi import APIRouter

from src.api.routes import (
    auth,
    data_sources,
    export,
    manual_metrics,
    screening,
    settings,
    stocks,
    system,
    watch_pool,
)

api_router = APIRouter(prefix="/api/v1")
for module in (auth, screening, stocks, watch_pool, manual_metrics, data_sources, settings, export, system):
    api_router.include_router(module.router)
