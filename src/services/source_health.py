"""数据源健康检查。"""
from __future__ import annotations

import sqlite3

from src.core.db import transaction
from src.integrations.sources import get_adapter
from src.repositories import data_sources as source_repo


def check_source(conn: sqlite3.Connection, name: str) -> dict:
    row = source_repo.get_source(conn, name)
    if row is None:
        raise ValueError(f"未知数据源：{name}")

    ok, latency, error = get_adapter(name).test()
    with transaction(conn):
        source_repo.log_health(conn, name, ok, latency, error)
        if ok:
            source_repo.mark_success(conn, name)
        else:
            source_repo.mark_failure(conn, name, error or "探测失败")
    return {"source": name, "ok": ok, "latency_ms": latency, "error": error}


def check_all(conn: sqlite3.Connection) -> list[dict]:
    results = []
    for row in source_repo.list_sources(conn, only_enabled=True):
        try:
            results.append(check_source(conn, row["name"]))
        except Exception as exc:
            results.append({"source": row["name"], "ok": False, "latency_ms": None, "error": str(exc)[:300]})
    return results
