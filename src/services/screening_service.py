"""筛选编排：一次 run 依次完成 硬门槛 → 题材 → 形态 → 评分。

每个阶段的结果都落 screening_results，保证「为什么淘汰」可回看。
评分只对通过硬门槛的候选计算，避免为 5000 只股票都算一遍。
"""
from __future__ import annotations

import json
import sqlite3
import time

from src.core.db import transaction
from src.core.logging import get_logger
from src.models.domain import Quote
from src.repositories import manual_metrics as manual_repo
from src.repositories import screening as screening_repo
from src.repositories import settings as settings_repo
from src.repositories import themes as theme_repo
from src.services import gates, market_service, scoring_service

logger = get_logger(__name__)

FLUSH_EVERY = 1000
PROGRESS_EVERY = 200


def create_run(conn: sqlite3.Connection, params: dict) -> int:
    with transaction(conn):
        return screening_repo.create_run(conn, params)


def execute_run(
    conn: sqlite3.Connection, run_id: int, prefetched: market_service.FetchResult | None = None
) -> None:
    """同步执行一个批次。API 层把它放进后台线程并传入独立连接。

    prefetched 用于定时任务：行情已经抓过一次，直接复用，避免同一天抓两遍。
    """
    run = screening_repo.get_run(conn, run_id)
    if run is None:
        raise ValueError(f"批次不存在：{run_id}")

    params = json.loads(run["params_json"] or "{}")
    settings = settings_repo.get_all(conn)
    thresholds = settings.get("thresholds", {})
    scoring_cfg = settings.get("scoring", {})

    started = time.perf_counter()
    try:
        fetch = prefetched or market_service.fetch_market_snapshot(conn)
    except market_service.MarketUnavailable as exc:
        stats = {"error": str(exc)[:500], "processed": 0, "total": 0}
        with transaction(conn):
            screening_repo.finish_run(conn, run_id, "failed", stats)
        logger.error("[DEBUG] execute_run 行情不可用 | run_id=%s error=%s", run_id, exc)
        return

    quotes = _apply_scope(fetch.quotes, params)
    theme_map = _load_theme_map(conn)
    manual_map = _load_manual_map(conn)
    tier_map = {r["code"]: r["tier"] for r in conn.execute("SELECT code, tier FROM watch_pool")}
    prev_map = _load_prev_quotes(conn, quotes)

    total = len(quotes)
    passed_hard = 0
    pending_rows: list[tuple] = []
    stats = {"total": total, "processed": 0, "passed_hard": 0, "source": fetch.source,
             "failures": fetch.failures, "elapsed_ms": 0}

    try:
        for idx, quote in enumerate(quotes, start=1):
            hard = gates.evaluate_hard_gates(quote, thresholds)
            for r in hard:
                pending_rows.append((run_id, quote.code, "hard_gate", *r.to_row()))

            if not gates.all_passed(hard):
                if len(pending_rows) >= FLUSH_EVERY * 4:
                    _flush(conn, pending_rows)
                if idx % PROGRESS_EVERY == 0:
                    stats.update(processed=idx, passed_hard=passed_hard,
                                 elapsed_ms=int((time.perf_counter() - started) * 1000))
                    _progress(conn, run_id, stats)
                continue

            passed_hard += 1
            theme_names = theme_map.get(quote.code, [])
            theme_gate = gates.GateResult(
                "theme_match", "题材匹配", "pass" if theme_names else "fail",
                "、".join(theme_names) or None,
                "命中 2026 题材池",
                "命中主线题材" if theme_names else "未命中题材池",
            )
            pending_rows.append((run_id, quote.code, "theme", *theme_gate.to_row()))

            patterns = {
                p.key: p for p in gates.detect_patterns(quote, prev_map.get(quote.code))
            }
            for p in patterns.values():
                pending_rows.append((run_id, quote.code, "pattern", *gates.pattern_as_gate_result(p).to_row()))

            score = scoring_service.compute_score(
                quote.code, quote, theme_names, patterns,
                manual_map.get(quote.code, {}), scoring_cfg, tier=tier_map.get(quote.code),
            )
            screening_repo.save_score(conn, run_id, score)

            if len(pending_rows) >= FLUSH_EVERY * 4:
                _flush(conn, pending_rows)
            if idx % PROGRESS_EVERY == 0:
                stats.update(processed=idx, passed_hard=passed_hard,
                             elapsed_ms=int((time.perf_counter() - started) * 1000))
                _progress(conn, run_id, stats)
    finally:
        if pending_rows:
            _flush(conn, pending_rows)

    stats.update(
        processed=total,
        passed_hard=passed_hard,
        # 候选数与候选接口同源：开启 with_theme 时已扣除未命中题材的标的
        candidates=screening_repo.candidate_count(conn, run_id),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    status = "partial" if fetch.failures else "success"
    with transaction(conn):
        screening_repo.finish_run(conn, run_id, status, stats)
    logger.info(
        "[DEBUG] execute_run 完成 | run_id=%s total=%s passed=%s status=%s elapsed=%sms",
        run_id, total, passed_hard, status, stats["elapsed_ms"],
    )


def _flush(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    with transaction(conn):
        screening_repo.bulk_insert_gate_rows(conn, rows)
    rows.clear()


def _progress(conn: sqlite3.Connection, run_id: int, stats: dict) -> None:
    with transaction(conn):
        screening_repo.update_progress(conn, run_id, stats)


def _apply_scope(quotes: list[Quote], params: dict) -> list[Quote]:
    board = (params.get("board") or "").upper()
    if params.get("scope") != "board" or not board:
        return quotes
    return [q for q in quotes if _market_of(q.code) == board]


def _market_of(code: str) -> str:
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    return "BJ"


def _load_theme_map(conn: sqlite3.Connection) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    rows = conn.execute(
        """
        SELECT st.code, t.name FROM stock_themes st
        JOIN themes t ON t.id = st.theme_id WHERE t.enabled = 1
        ORDER BY t.branch, t.sort_order
        """
    ).fetchall()
    for r in rows:
        result.setdefault(r["code"], []).append(r["name"])
    return result


def _load_manual_map(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """每只股票每项指标取最新值。人工补录数据量小，全量读取后覆盖即可。"""
    result: dict[str, dict[str, float]] = {}
    rows = conn.execute(
        "SELECT code, metric, value FROM manual_metrics ORDER BY trade_date ASC"
    ).fetchall()
    for r in rows:
        if r["value"] is not None:
            result.setdefault(r["code"], {})[r["metric"]] = r["value"]
    return result


def _load_prev_quotes(conn: sqlite3.Connection, quotes: list[Quote]) -> dict[str, Quote]:
    if not quotes:
        return {}
    current = max(q.trade_date for q in quotes)
    row = conn.execute(
        "SELECT MAX(trade_date) AS d FROM daily_quotes WHERE trade_date < ?", (current,)
    ).fetchone()
    prev_date = row["d"] if row else None
    if not prev_date:
        return {}
    prev: dict[str, Quote] = {}
    for r in conn.execute(
        "SELECT code, close, limit_up FROM daily_quotes WHERE trade_date = ?", (prev_date,)
    ):
        prev[r["code"]] = Quote(
            code=r["code"], name="", trade_date=prev_date,
            close=r["close"], limit_up=r["limit_up"],
        )
    return prev
