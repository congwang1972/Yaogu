"""行情抓取编排：按优先级尝试数据源，成功即停，失败降级并留痕。"""
from __future__ import annotations

import sqlite3
import time

from src.core import config
from src.core.db import now_iso, transaction
from src.core.logging import get_logger
from src.integrations.sources import get_adapter
from src.integrations.sources.base import SourceAdapter, SourceError
from src.models.domain import FetchResult, Quote
from src.repositories import data_sources as source_repo
from src.repositories import quotes as quote_repo
from src.repositories import stocks as stock_repo

logger = get_logger(__name__)


class MarketUnavailable(Exception):
    """全部数据源都失败。保留旧快照，由调用方决定如何提示。"""


def _valid(q: Quote) -> bool:
    return (
        len(q.code) == 6
        and q.code.isdigit()
        and bool(q.name)
        and q.close is not None
        and q.close > 0
    )


def _universe(conn: sqlite3.Connection) -> list[str]:
    return [r["code"] for r in conn.execute("SELECT code FROM stocks").fetchall()]


def fetch_market_snapshot(conn: sqlite3.Connection) -> FetchResult:
    sources = source_repo.list_sources(conn, only_enabled=True)
    if not sources:
        raise MarketUnavailable("没有启用任何数据源")

    universe = _universe(conn)
    failures: list[str] = []

    for row in sources:
        name = row["name"]
        adapter: SourceAdapter = get_adapter(name)
        if adapter.requires_universe and not universe:
            # 云机房常把主源（东财）挡掉，批量源若能自行取全集就能独立冷启动，
            # 否则 stocks 永远为空，腾讯/新浪会互相等对方先成功。
            fetcher = getattr(adapter, "fetch_universe", None)
            if fetcher is None:
                failures.append(f"{name}: 缺少代码全集，需先用主源成功抓取一次")
                continue
            started = time.perf_counter()
            try:
                universe = fetcher()
                elapsed = int((time.perf_counter() - started) * 1000)
                logger.info("[DEBUG] 代码全集获取成功 | source=%s count=%s elapsed=%sms", name, len(universe), elapsed)
            except Exception as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                message = str(exc)[:300]
                failures.append(f"{name}: 获取代码全集失败：{message}")
                logger.warning("[DEBUG] 代码全集获取失败 | source=%s error=%s", name, message)
                with transaction(conn):
                    source_repo.mark_failure(conn, name, message)
                    source_repo.log_health(conn, name, False, elapsed, message)
                continue
            if not universe:
                failures.append(f"{name}: 代码全集为空")
                continue
        started = time.perf_counter()
        try:
            quotes = adapter.fetch_all(universe if adapter.requires_universe else None)
            elapsed = int((time.perf_counter() - started) * 1000)
            quotes = [q for q in quotes if _valid(q)]
            if len(quotes) < config.MIN_QUOTE_COUNT:
                raise SourceError(f"有效条目过少：{len(quotes)} < {config.MIN_QUOTE_COUNT}")

            with transaction(conn):
                stock_repo.upsert_stocks(conn, quotes)
                quote_repo.upsert_quotes(conn, quotes)
                source_repo.mark_success(conn, name)
                source_repo.log_health(conn, name, True, elapsed, None)

            logger.info("[DEBUG] fetch_market_snapshot 成功 | source=%s count=%s elapsed=%sms", name, len(quotes), elapsed)
            return FetchResult(quotes=quotes, source=name, count=len(quotes), elapsed_ms=elapsed, failures=failures)
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            message = str(exc)[:300]
            failures.append(f"{name}: {message}")
            logger.warning("[DEBUG] fetch_market_snapshot 源失败 | source=%s error=%s", name, message)
            with transaction(conn):
                source_repo.mark_failure(conn, name, message)
                source_repo.log_health(conn, name, False, elapsed, message)

    raise MarketUnavailable("; ".join(failures))


def refresh_quotes(conn: sqlite3.Connection) -> FetchResult:
    """观察池刷新复用同一抓取流程，语义上单独命名便于日志区分。"""
    return fetch_market_snapshot(conn)
