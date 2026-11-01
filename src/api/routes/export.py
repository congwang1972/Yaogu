"""CSV 导出。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Response

from src.api.deps import get_db, require_login
from src.services import export_service

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/watch-pool.csv")
def export_watch_pool(
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> Response:
    return _csv_response(export_service.watch_pool_csv(conn), "watch_pool.csv")


@router.get("/screening/{run_id}.csv")
def export_screening(
    run_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> Response:
    return _csv_response(
        export_service.screening_csv(conn, run_id), f"screening_{run_id}.csv"
    )
