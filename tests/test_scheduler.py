"""定时任务：休市跳过、成功批次、失败留痕、健康检查。"""
from __future__ import annotations

from conftest import make_quote
from src.core import config, db
from src.models.domain import FetchResult
from src.tasks import scheduler


def test_parse_time():
    assert scheduler._parse_time("15:30") == (15, 30)
    assert scheduler._parse_time("09:05") == (9, 5)
    assert scheduler._parse_time("bad") == (15, 30)
    assert scheduler._parse_time(None) == (15, 30)  # type: ignore[arg-type]


def test_daily_refresh_skips_non_trading_day(db_path, monkeypatch):
    yesterday = "2020-01-02"
    monkeypatch.setattr(
        scheduler.market_service,
        "fetch_market_snapshot",
        lambda conn: FetchResult([make_quote(trade_date=yesterday)], "fake", 1, 5),
    )
    result = scheduler.daily_refresh()

    assert result == {"status": "skipped", "trade_date": None}
    conn = db.connect(config.DB_PATH)
    job = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert job["job"] == "daily_refresh"
    assert job["status"] == "skipped"


def _insert_today_quote() -> None:
    from src.repositories import quotes as quote_repo
    from src.repositories import stocks as stock_repo

    quote = make_quote(trade_date=db.today_str())
    conn = db.connect(config.DB_PATH)
    with db.transaction(conn):
        stock_repo.upsert_stocks(conn, [quote])
        quote_repo.upsert_quotes(conn, [quote])
    conn.close()


def test_daily_refresh_runs_screening(db_path, monkeypatch):
    _insert_today_quote()
    monkeypatch.setattr(
        scheduler.market_service,
        "fetch_market_snapshot",
        lambda conn: FetchResult([make_quote(trade_date=db.today_str())], "fake", 1, 5),
    )
    result = scheduler.daily_refresh()

    assert result["status"] == "success"
    conn = db.connect(config.DB_PATH)
    run = conn.execute("SELECT * FROM screening_runs WHERE id = ?", (result["run_id"],)).fetchone()
    job = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert run["status"] == "success"
    assert job["status"] == "success"


def test_daily_refresh_stale_fallback_does_not_auto_screen(db_path, monkeypatch):
    """定时任务拿到旧快照时应停止自动筛选，避免用过期行情产出新结论。"""
    monkeypatch.setattr(
        scheduler.market_service,
        "fetch_market_snapshot",
        lambda conn: FetchResult(
            [make_quote(trade_date="2026-10-30")], "cache", 1, 5,
            failures=["tencent: 超时"], stale=True, as_of="2026-10-30",
        ),
    )
    result = scheduler.daily_refresh()

    assert result["status"] == "partial"
    assert result["stale"] is True
    assert result["trade_date"] == "2026-10-30"
    conn = db.connect(config.DB_PATH)
    job = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
    runs = conn.execute("SELECT COUNT(*) AS c FROM screening_runs").fetchone()["c"]
    conn.close()
    assert job["status"] == "partial"
    assert "回退" in job["error"]
    assert runs == 0


def test_daily_refresh_failure_is_recorded(db_path, monkeypatch):
    def boom(conn):
        raise RuntimeError("网络中断")

    monkeypatch.setattr(scheduler.market_service, "fetch_market_snapshot", boom)
    result = scheduler.daily_refresh()

    assert result["status"] == "failed"
    assert "网络中断" in result["error"]
    conn = db.connect(config.DB_PATH)
    job = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert job["status"] == "failed"
    assert "网络中断" in job["error"]


def test_weekly_health_success_and_failure(db_path, monkeypatch):
    monkeypatch.setattr(
        scheduler.source_health, "check_all", lambda conn: [{"source": "eastmoney", "ok": True}]
    )
    assert scheduler.weekly_health() == [{"source": "eastmoney", "ok": True}]

    def boom(conn):
        raise RuntimeError("探针异常")

    monkeypatch.setattr(scheduler.source_health, "check_all", boom)
    result = scheduler.weekly_health()
    assert result[0]["ok"] is False
    assert "探针异常" in result[0]["error"]

    conn = db.connect(config.DB_PATH)
    jobs = conn.execute("SELECT status FROM job_runs ORDER BY id").fetchall()
    conn.close()
    assert [j["status"] for j in jobs] == ["success", "failed"]


def test_start_and_shutdown(db_path):
    started = scheduler.start()
    assert started.running is True
    # 重复调用返回同一实例
    assert scheduler.start() is started
    scheduler.shutdown()
    assert scheduler._scheduler is None
