"""筛选批次、逐条判定、评分。"""
from __future__ import annotations

import json
import sqlite3

from src.core.db import now_iso
from src.models.domain import GateResult, ScoreResult


def create_run(conn: sqlite3.Connection, params: dict) -> int:
    cur = conn.execute(
        "INSERT INTO screening_runs (started_at, status, params_json) VALUES (?, 'running', ?)",
        (now_iso(), json.dumps(params, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def update_progress(conn: sqlite3.Connection, run_id: int, stats: dict) -> None:
    conn.execute(
        "UPDATE screening_runs SET stats_json = ? WHERE id = ?",
        (json.dumps(stats, ensure_ascii=False), run_id),
    )


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        "UPDATE screening_runs SET finished_at = ?, status = ?, stats_json = ? WHERE id = ?",
        (now_iso(), status, json.dumps(stats, ensure_ascii=False), run_id),
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM screening_runs WHERE id = ?", (run_id,)).fetchone()


def list_runs(conn: sqlite3.Connection, page: int = 1, size: int = 20) -> tuple[list[sqlite3.Row], int]:
    total = conn.execute("SELECT COUNT(*) AS c FROM screening_runs").fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM screening_runs ORDER BY id DESC LIMIT ? OFFSET ?", (size, (page - 1) * size)
    ).fetchall()
    return list(rows), total


def insert_gate_results(
    conn: sqlite3.Connection, run_id: int, code: str, stage: str, results: list[GateResult]
) -> None:
    conn.executemany(
        """
        INSERT INTO screening_results (run_id, code, stage, gate, passed, actual_value, threshold, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(run_id, code, stage, *r.to_row()) for r in results],
    )


def bulk_insert_gate_rows(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (run_id, code, stage, gate, passed, actual_value, threshold, reason)"""
    conn.executemany(
        """
        INSERT INTO screening_results (run_id, code, stage, gate, passed, actual_value, threshold, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def query_results(
    conn: sqlite3.Connection,
    run_id: int,
    stage: str | None = None,
    passed: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[sqlite3.Row], int]:
    where, params = ["run_id = ?"], [run_id]
    if stage:
        where.append("stage = ?")
        params.append(stage)
    if passed is not None:
        where.append("passed = ?")
        params.append(1 if passed else 0)
    clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) AS c FROM screening_results WHERE {clause}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM screening_results WHERE {clause} ORDER BY id LIMIT ? OFFSET ?",
        [*params, size, (page - 1) * size],
    ).fetchall()
    return list(rows), total


_CANDIDATE_SQL = """
FROM (SELECT code FROM screening_results
      WHERE run_id = ? AND stage = 'hard_gate'
      GROUP BY code HAVING MIN(passed) = 1) r
JOIN stocks s ON s.code = r.code
LEFT JOIN scores sc ON sc.code = r.code AND sc.run_id = ?
LEFT JOIN daily_quotes q ON q.code = r.code
     AND q.trade_date = (SELECT MAX(trade_date) FROM daily_quotes)
"""

# 批次参数 with_theme=true 时，未命中题材池的标的不能进入候选
_THEME_FILTER = """
WHERE NOT EXISTS (
  SELECT 1 FROM screening_results t
  WHERE t.run_id = ? AND t.code = r.code AND t.stage = 'theme' AND t.passed = 0
)
"""


def _candidate_clause(conn: sqlite3.Connection, run_id: int) -> tuple[str, tuple]:
    row = conn.execute("SELECT params_json FROM screening_runs WHERE id = ?", (run_id,)).fetchone()
    with_theme = bool(row and json.loads(row["params_json"] or "{}").get("with_theme"))
    if with_theme:
        return f"{_CANDIDATE_SQL}{_THEME_FILTER}", (run_id, run_id, run_id)
    return _CANDIDATE_SQL, (run_id, run_id)


def candidate_count(conn: sqlite3.Connection, run_id: int) -> int:
    clause, params = _candidate_clause(conn, run_id)
    return conn.execute(f"SELECT COUNT(*) AS c {clause}", params).fetchone()["c"]


def list_candidates(conn: sqlite3.Connection, run_id: int, page: int = 1, size: int = 50) -> list[sqlite3.Row]:
    clause, params = _candidate_clause(conn, run_id)
    return list(
        conn.execute(
            f"""
            SELECT r.code, s.name, s.is_st, q.close, q.pct_chg, q.total_mv,
                   q.turnover_rate, q.trade_date,
                   COALESCE(sc.total_score, 0) AS total_score,
                   (SELECT group_concat(t.name, ',') FROM stock_themes st
                    JOIN themes t ON t.id = st.theme_id WHERE st.code = r.code) AS themes
            {clause}
            ORDER BY total_score DESC, r.code
            LIMIT ? OFFSET ?
            """,
            (*params, size, (page - 1) * size),
        ).fetchall()
    )


def save_score(conn: sqlite3.Connection, run_id: int, score: ScoreResult) -> None:
    conn.execute(
        "INSERT INTO scores (code, run_id, total_score, details_json, calculated_at) VALUES (?, ?, ?, ?, ?)",
        (
            score.code,
            run_id,
            score.total,
            json.dumps(
                [
                    {
                        "key": d.key, "label": d.label, "type": d.type, "delta": d.delta,
                        "weight": d.weight, "source": d.source, "available": d.available,
                        "evidence": d.evidence, "points": d.points,
                    }
                    for d in score.details
                ],
                ensure_ascii=False,
            ),
            now_iso(),
        ),
    )


def get_score(conn: sqlite3.Connection, code: str, run_id: int | None = None) -> sqlite3.Row | None:
    if run_id is not None:
        return conn.execute(
            "SELECT * FROM scores WHERE code = ? AND run_id = ?", (code, run_id)
        ).fetchone()
    return conn.execute(
        "SELECT * FROM scores WHERE code = ? ORDER BY id DESC LIMIT 1", (code,)
    ).fetchone()


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(id) AS i FROM screening_runs WHERE status IN ('success','partial')").fetchone()
    return row["i"] if row else None
