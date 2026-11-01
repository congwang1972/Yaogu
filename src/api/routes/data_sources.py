"""数据源健康与启停。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_db, require_login
from src.core import db
from src.repositories import data_sources as source_repo
from src.services import source_health

router = APIRouter(prefix="/data-sources", tags=["data_sources"])


class SourcePatch(BaseModel):
    enabled: bool | None = None
    priority: int | None = None


def _serialize(row: sqlite3.Row, conn: sqlite3.Connection) -> dict:
    data = dict(row)
    latest = source_repo.recent_health(conn, row["name"], limit=1)
    data["last_health"] = dict(latest[0]) if latest else None
    return data


@router.get("")
def list_sources(
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return {"items": [_serialize(r, conn) for r in source_repo.list_sources(conn)]}


@router.patch("/{name}", status_code=204)
def patch_source(
    name: str,
    body: SourcePatch,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> None:
    if source_repo.get_source(conn, name) is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    with db.transaction(conn):
        source_repo.update_source(conn, name, body.enabled, body.priority)


@router.post("/{name}/test")
def test_source(
    name: str,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    try:
        return source_health.check_source(conn, name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
