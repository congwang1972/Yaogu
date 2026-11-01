"""股票基础信息与日行情。"""
from __future__ import annotations

import sqlite3

from src.core.db import now_iso
from src.models.domain import Quote


def upsert_stocks(conn: sqlite3.Connection, quotes: list[Quote]) -> None:
    ts = now_iso()
    rows = [
        (q.code, q.name, _market(q.code), None, 1 if q.is_st else 0, q.status, ts)
        for q in quotes
    ]
    conn.executemany(
        """
        INSERT INTO stocks (code, name, market, list_date, is_st, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
          name = excluded.name,
          is_st = excluded.is_st,
          status = excluded.status,
          updated_at = excluded.updated_at
        """,
        rows,
    )


def _market(code: str) -> str:
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "UNKNOWN"


def get_stock(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM stocks WHERE code = ?", (code,)).fetchone()


def list_stocks(conn: sqlite3.Connection, q: str = "", page: int = 1, size: int = 50) -> tuple[list[sqlite3.Row], int]:
    where, params = "", []
    if q:
        where = "WHERE code LIKE ? OR name LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    total = conn.execute(f"SELECT COUNT(*) AS c FROM stocks {where}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM stocks {where} ORDER BY code LIMIT ? OFFSET ?",
        [*params, size, (page - 1) * size],
    ).fetchall()
    return list(rows), total
