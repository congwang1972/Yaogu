"""数据源配置与健康流水。"""
from __future__ import annotations

import sqlite3

from src.core.db import now_iso


def list_sources(conn: sqlite3.Connection, only_enabled: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM data_sources"
    if only_enabled:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY priority"
    return list(conn.execute(sql).fetchall())


def get_source(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM data_sources WHERE name = ?", (name,)).fetchone()


def update_source(conn: sqlite3.Connection, name: str, enabled: bool | None = None, priority: int | None = None) -> None:
    fields, params = ["updated_at = ?"], [now_iso()]
    if enabled is not None:
        fields.append("enabled = ?")
        params.append(1 if enabled else 0)
    if priority is not None:
        fields.append("priority = ?")
        params.append(priority)
    params.append(name)
    conn.execute(f"UPDATE data_sources SET {', '.join(fields)} WHERE name = ?", params)


def mark_success(conn: sqlite3.Connection, name: str) -> None:
    now = now_iso()
    conn.execute(
        "UPDATE data_sources SET last_success_at = ?, last_error = NULL, updated_at = ? WHERE name = ?",
        (now, now, name),
    )


def mark_failure(conn: sqlite3.Connection, name: str, error: str) -> None:
    conn.execute(
        "UPDATE data_sources SET last_error = ?, updated_at = ? WHERE name = ?",
        (error[:500], now_iso(), name),
    )


def log_health(conn: sqlite3.Connection, source: str, ok: bool, latency_ms: int | None, error: str | None) -> None:
    conn.execute(
        "INSERT INTO source_health_logs (source, checked_at, ok, latency_ms, error) VALUES (?, ?, ?, ?, ?)",
        (source, now_iso(), 1 if ok else 0, latency_ms, (error or "")[:500] or None),
    )


def recent_health(conn: sqlite3.Connection, source: str, limit: int = 1) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM source_health_logs WHERE source = ? ORDER BY checked_at DESC LIMIT ?",
            (source, limit),
        ).fetchall()
    )
