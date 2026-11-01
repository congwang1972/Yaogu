"""观察池。"""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import get_db, require_login
from src.repositories import watch_pool as pool_repo
from src.services import watch_pool_service

router = APIRouter(prefix="/watch-pool", tags=["watch_pool"])


class AddRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    theme_side: Literal["main", "branch"] | None = None
    first_board_date: str | None = None
    tier: Literal["leader", "follower"] | None = None


class StatusRequest(BaseModel):
    status: Literal["keep", "watch", "drop"]
    reason: str = Field(min_length=1, max_length=500)


class RemoveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.get("/stats")
def get_stats(
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return watch_pool_service.stats(conn)


@router.get("")
def list_pool(
    status: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    rows = pool_repo.list_pool(conn, status)
    return {"items": [dict(r) for r in rows]}


@router.post("", status_code=201)
def add_to_pool(
    body: AddRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    pool_id = watch_pool_service.add(
        conn, body.code, body.theme_side, body.first_board_date, body.tier
    )
    return {"id": pool_id}


@router.get("/{pool_id}/history")
def get_history(
    pool_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return {"items": [dict(r) for r in pool_repo.get_history(conn, pool_id)]}


@router.patch("/{pool_id}")
def change_status(
    pool_id: int,
    body: StatusRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    row = watch_pool_service.change_status(conn, pool_id, body.status, body.reason)
    return dict(row)


@router.delete("/{pool_id}")
def remove_from_pool(
    pool_id: int,
    body: RemoveRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    row = watch_pool_service.remove(conn, pool_id, body.reason)
    return dict(row)
