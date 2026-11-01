"""观察池与状态流转留痕。

注意：这里只提供「改一行」和「追加历史」两个原子操作，
把它们放进同一个事务由 service 负责，Repository 不暴露裸 UPDATE。
"""
from __future__ import annotations

import sqlite3

from src.core.db import now_iso

ACTIVE_STATUSES = ("keep", "watch")


def count_active(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM watch_pool WHERE status IN ('keep','watch')"
    ).fetchone()
    return rows["c"]


def get_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM watch_pool WHERE code = ?", (code,)).fetchone()


def get_by_id(conn: sqlite3.Connection, pool_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM watch_pool WHERE id = ?", (pool_id,)).fetchone()


def insert(
    conn: sqlite3.Connection,
    code: str,
    theme_side: str | None,
    first_board_date: str | None,
    tier: str | None,
) -> int:
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO watch_pool (code, status, theme_side, first_board_date, tier, added_at, updated_at)
        VALUES (?, 'keep', ?, ?, ?, ?, ?)
        """,
        (code, theme_side, first_board_date, tier, ts, ts),
    )
    return int(cur.lastrowid)


def update_status(conn: sqlite3.Connection, pool_id: int, status: str) -> None:
    conn.execute(
        "UPDATE watch_pool SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), pool_id)
    )


def delete(conn: sqlite3.Connection, pool_id: int) -> None:
    conn.execute("DELETE FROM watch_pool WHERE id = ?", (pool_id,))


def add_history(
    conn: sqlite3.Connection, pool_id: int, from_status: str | None, to_status: str, reason: str
) -> None:
    conn.execute(
        "INSERT INTO watch_pool_history (pool_id, from_status, to_status, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (pool_id, from_status, to_status, reason.strip(), now_iso()),
    )


def get_history(conn: sqlite3.Connection, pool_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM watch_pool_history WHERE pool_id = ? ORDER BY id DESC", (pool_id,)
        ).fetchall()
    )


def list_pool(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    where, params = "", []
    if status:
        where, params = "WHERE w.status = ?", [status]
    return list(
        conn.execute(
            f"""
            SELECT w.*, s.name, s.is_st, q.close, q.pct_chg, q.total_mv, q.turnover_rate,
                   COALESCE(sc.total_score, 0) AS total_score
            FROM watch_pool w
            LEFT JOIN stocks s ON s.code = w.code
            LEFT JOIN daily_quotes q ON q.code = w.code
                 AND q.trade_date = (SELECT MAX(trade_date) FROM daily_quotes)
            LEFT JOIN scores sc ON sc.code = w.code
                 AND sc.run_id = (SELECT MAX(id) FROM screening_runs WHERE status IN ('success','partial'))
            {where}
            ORDER BY total_score DESC, w.added_at DESC
            """,
            params,
        ).fetchall()
    )


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS c FROM watch_pool GROUP BY status").fetchall()
    counts = {"keep": 0, "watch": 0, "drop": 0}
    counts.update({r["status"]: r["c"] for r in rows})
    return counts


def codes_active(conn: sqlite3.Connection) -> list[str]:
    return [
        r["code"]
        for r in conn.execute(
            "SELECT code FROM watch_pool WHERE status IN ('keep','watch')"
        ).fetchall()
    ]
