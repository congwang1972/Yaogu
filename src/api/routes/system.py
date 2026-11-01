"""健康探针与顶栏状态。"""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends

from src.api.deps import get_db, require_login
from src.repositories import data_sources as source_repo
from src.repositories import jobs as job_repo
from src.repositories import screening as screening_repo
from src.services import watch_pool_service

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/system/status")
def status(
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    sources = source_repo.list_sources(conn)
    healthy = [s for s in sources if s["enabled"] and not s["last_error"]]
    last_run = conn.execute(
        "SELECT * FROM screening_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_job = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "sources": {
            "total": len(sources),
            "enabled": len([s for s in sources if s["enabled"]]),
            "healthy": len(healthy),
        },
        "last_run": {
            "id": last_run["id"],
            "status": last_run["status"],
            "started_at": last_run["started_at"],
            "finished_at": last_run["finished_at"],
            "stats": json.loads(last_run["stats_json"] or "null"),
        } if last_run else None,
        "last_job": dict(last_job) if last_job else None,
        "pool": watch_pool_service.stats(conn),
    }
