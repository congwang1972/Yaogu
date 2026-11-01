"""筛选批次。"""
from __future__ import annotations

import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps import get_db, require_login
from src.core import db
from src.core.logging import get_logger
from src.repositories import screening as screening_repo
from src.schemas.common import page_response
from src.services import screening_service

router = APIRouter(prefix="/screening", tags=["screening"])
logger = get_logger(__name__)


class RunRequest(BaseModel):
    scope: Literal["all", "board"] = "all"
    board: str | None = None
    with_theme: bool = False


def _serialize_run(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["params"] = json.loads(data.pop("params_json") or "{}")
    data["stats"] = json.loads(data.pop("stats_json") or "null")
    return data


def _execute_in_background(run_id: int) -> None:
    conn = db.connect()
    try:
        screening_service.execute_run(conn, run_id)
    except Exception as exc:  # 后台任务不能把异常抛回请求线程
        logger.exception("[DEBUG] 后台筛选失败 | run_id=%s error=%s", run_id, exc)
        try:
            with db.transaction(conn):
                screening_repo.finish_run(
                    conn, run_id, "failed", {"error": str(exc)[:500]}
                )
        except Exception:
            logger.exception("[DEBUG] 标记批次失败状态时再次出错 | run_id=%s", run_id)
    finally:
        conn.close()


@router.post("/runs", status_code=202)
def start_run(
    body: RunRequest,
    background: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    run_id = screening_service.create_run(conn, body.model_dump())
    background.add_task(_execute_in_background, run_id)
    return {"run_id": run_id}


@router.get("/runs")
def list_runs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    rows, total = screening_repo.list_runs(conn, page, size)
    return page_response([_serialize_run(r) for r in rows], total, page, size)


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    row = screening_repo.get_run(conn, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return _serialize_run(row)


@router.get("/runs/{run_id}/results")
def get_results(
    run_id: int,
    stage: str | None = None,
    passed: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    rows, total = screening_repo.query_results(conn, run_id, stage, passed, page, size)
    return page_response([dict(r) for r in rows], total, page, size)


@router.get("/runs/{run_id}/candidates")
def get_candidates(
    run_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    total = screening_repo.candidate_count(conn, run_id)
    rows = screening_repo.list_candidates(conn, run_id, page, size)
    items = []
    for r in rows:
        item = dict(r)
        item["themes"] = item["themes"].split(",") if item.get("themes") else []
        items.append(item)
    return page_response(items, total, page, size)
