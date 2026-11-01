"""定时任务执行记录。"""
from __future__ import annotations

import sqlite3

from src.core.db import now_iso


def start_job(conn: sqlite3.Connection, job: str) -> int:
    cur = conn.execute(
        "INSERT INTO job_runs (job, started_at, status) VALUES (?, ?, 'running')",
        (job, now_iso()),
    )
    return int(cur.lastrowid)


def finish_job(conn: sqlite3.Connection, job_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE job_runs SET finished_at = ?, status = ?, error = ? WHERE id = ?",
        (now_iso(), status, (error or "")[:500] or None, job_id),
    )


def recent_jobs(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall())
