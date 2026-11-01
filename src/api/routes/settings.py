"""系统配置读写。"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_db, require_login
from src.core import db
from src.repositories import settings as settings_repo

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED_KEYS = {"thresholds", "scoring", "pool", "schedule"}


@router.get("")
def get_settings(
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return settings_repo.get_all(conn)


@router.put("")
def update_settings(
    body: dict[str, Any],
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    unknown = set(body) - ALLOWED_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"不支持的配置项：{', '.join(sorted(unknown))}")
    with db.transaction(conn):
        settings_repo.set_values(conn, body)
    return settings_repo.get_all(conn)
