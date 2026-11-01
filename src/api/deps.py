"""FastAPI 依赖：数据库连接与会话校验。"""
from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Depends, HTTPException, Request

from src.core import config, db, security


def get_db() -> Iterator[sqlite3.Connection]:
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def get_user(conn: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="用户未初始化")
    return row


def require_login(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    token = request.cookies.get(config.SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    if user is None or not security.verify_session(token, user["password_hash"]):
        raise HTTPException(status_code=401, detail="登录已过期")
    return user


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
