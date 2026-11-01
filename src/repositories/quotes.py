"""日行情快照。"""
from __future__ import annotations

import sqlite3

from src.models.domain import Quote


def upsert_quotes(conn: sqlite3.Connection, quotes: list[Quote]) -> None:
    rows = [
        (
            q.code, q.trade_date, q.open, q.high, q.low, q.close, q.pre_close,
            q.pct_chg, q.volume, q.amount, q.turnover_rate, q.total_mv, q.float_mv,
            q.limit_up, q.source, q.fetched_at,
        )
        for q in quotes
    ]
    conn.executemany(
        """
        INSERT INTO daily_quotes (
          code, trade_date, open, high, low, close, pre_close, pct_chg,
          volume, amount, turnover_rate, total_mv, float_mv, limit_up, source, fetched_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code, trade_date) DO UPDATE SET
          open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
          pre_close=excluded.pre_close, pct_chg=excluded.pct_chg, volume=excluded.volume,
          amount=excluded.amount, turnover_rate=excluded.turnover_rate,
          total_mv=excluded.total_mv, float_mv=excluded.float_mv, limit_up=excluded.limit_up,
          source=excluded.source, fetched_at=excluded.fetched_at
        """,
        rows,
    )


def get_latest_quote(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM daily_quotes WHERE code = ? ORDER BY trade_date DESC LIMIT 1", (code,)
    ).fetchone()


def get_quotes(conn: sqlite3.Connection, code: str, days: int = 60) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM daily_quotes WHERE code = ? ORDER BY trade_date DESC LIMIT ?",
        (code, days),
    ).fetchall()
    return list(reversed(rows))


def latest_trade_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(trade_date) AS d FROM daily_quotes").fetchone()
    return row["d"] if row else None


def latest_quotes_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """每只股票最新一条行情，供观察池刷新使用。"""
    d = latest_trade_date(conn)
    if not d:
        return []
    return list(conn.execute("SELECT * FROM daily_quotes WHERE trade_date = ?", (d,)).fetchall())
