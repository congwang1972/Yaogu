"""个股查询。"""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db, require_login
from src.repositories import quotes as quote_repo
from src.repositories import screening as screening_repo
from src.repositories import stocks as stock_repo
from src.repositories import themes as theme_repo
from src.repositories import watch_pool as pool_repo
from src.schemas.common import page_response

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("")
def list_stocks(
    q: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    rows, total = stock_repo.list_stocks(conn, q, page, size)
    items = []
    for r in rows:
        latest = quote_repo.get_latest_quote(conn, r["code"])
        items.append({**dict(r), "quote": dict(latest) if latest else None})
    return page_response(items, total, page, size)


@router.get("/{code}")
def get_stock(
    code: str,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    stock = stock_repo.get_stock(conn, code)
    if stock is None:
        raise HTTPException(status_code=404, detail="股票不存在")
    latest = quote_repo.get_latest_quote(conn, code)
    pool = pool_repo.get_by_code(conn, code)
    return {
        "stock": dict(stock),
        "quote": dict(latest) if latest else None,
        "themes": [dict(t) for t in theme_repo.get_stock_themes(conn, code)],
        "watch_pool": dict(pool) if pool else None,
    }


@router.get("/{code}/quotes")
def get_quotes(
    code: str,
    days: int = Query(60, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return {"items": [dict(r) for r in quote_repo.get_quotes(conn, code, days)]}


@router.get("/{code}/gates")
def get_gates(
    code: str,
    run_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    rid = run_id if run_id is not None else screening_repo.latest_run_id(conn)
    if rid is None:
        return {"run_id": None, "items": []}
    rows = conn.execute(
        "SELECT * FROM screening_results WHERE code = ? AND run_id = ? ORDER BY stage, id",
        (code, rid),
    ).fetchall()
    return {"run_id": rid, "items": [dict(r) for r in rows]}


@router.get("/{code}/score")
def get_score(
    code: str,
    run_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    row = screening_repo.get_score(conn, code, run_id)
    if row is None:
        return {"run_id": None, "total_score": None, "details": []}
    data = dict(row)
    data["details"] = json.loads(data.pop("details_json") or "[]")
    return data
