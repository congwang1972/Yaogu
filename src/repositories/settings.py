"""配置键值读写。"""
from __future__ import annotations

import json
import sqlite3

from src.core.db import now_iso


def get_all(conn: sqlite3.Connection) -> dict[str, object]:
    rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
    return {r["key"]: json.loads(r["value_json"]) for r in rows}


def get_key(conn: sqlite3.Connection, key: str, default: object = None) -> object:
    row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else default


def set_values(conn: sqlite3.Connection, values: dict[str, object]) -> None:
    ts = now_iso()
    conn.executemany(
        """
        INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
        """,
        [(k, json.dumps(v, ensure_ascii=False), ts) for k, v in values.items()],
    )
