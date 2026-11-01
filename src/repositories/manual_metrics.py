"""人工补录指标。"""
from __future__ import annotations

import sqlite3

from src.core.db import now_iso

VALID_METRICS = ("pct_30d", "touch_200", "turnover_history", "name_recog", "event_catalyst")


def upsert(
    conn: sqlite3.Connection, code: str, trade_date: str, metric: str, value: float | None
) -> None:
    conn.execute(
        """
        INSERT INTO manual_metrics (code, trade_date, metric, value, entered_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code, trade_date, metric) DO UPDATE SET
          value = excluded.value, entered_at = excluded.entered_at
        """,
        (code, trade_date, metric, value, now_iso()),
    )


def list_for_code(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM manual_metrics WHERE code = ? ORDER BY trade_date DESC, metric", (code,)
        ).fetchall()
    )


def latest_map(conn: sqlite3.Connection, code: str) -> dict[str, float]:
    """取每项指标最新一条值，评分计算使用。"""
    rows = conn.execute(
        """
        SELECT metric, value FROM manual_metrics m
        WHERE code = ? AND trade_date = (
          SELECT MAX(trade_date) FROM manual_metrics WHERE code = m.code AND metric = m.metric
        )
        """,
        (code,),
    ).fetchall()
    return {r["metric"]: r["value"] for r in rows if r["value"] is not None}
