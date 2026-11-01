"""题材池与股票-题材关联。"""
from __future__ import annotations

import sqlite3


def list_themes(conn: sqlite3.Connection, only_enabled: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM themes"
    if only_enabled:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY branch, sort_order"
    return list(conn.execute(sql).fetchall())


def get_stock_themes(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT t.id, t.name, t.branch, st.source
            FROM stock_themes st JOIN themes t ON t.id = st.theme_id
            WHERE st.code = ? AND t.enabled = 1
            ORDER BY t.branch, t.sort_order
            """,
            (code,),
        ).fetchall()
    )


def set_stock_themes(conn: sqlite3.Connection, code: str, theme_ids: list[int], source: str = "manual") -> None:
    conn.execute("DELETE FROM stock_themes WHERE code = ?", (code,))
    conn.executemany(
        "INSERT OR IGNORE INTO stock_themes (code, theme_id, source) VALUES (?, ?, ?)",
        [(code, tid, source) for tid in theme_ids],
    )


def upsert_theme(conn: sqlite3.Connection, name: str, branch: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO themes (name, branch, enabled, sort_order) VALUES (?, ?, 1, 999)",
        (name, branch),
    )
