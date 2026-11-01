"""抓取编排：多源降级、条目校验、失败留痕。"""
from __future__ import annotations

import pytest

from conftest import enable_only_source, make_quote
from src.core import config
from src.integrations.sources.base import SourceError
from src.models.domain import Quote
from src.services import market_service


class FakeAdapter:
    def __init__(self, quotes=None, error: Exception | None = None, requires_universe=False):
        self.quotes = quotes or []
        self.error = error
        self.requires_universe = requires_universe
        self.calls: list[list[str] | None] = []

    def fetch_all(self, universe=None):
        self.calls.append(universe)
        if self.error:
            raise self.error
        return self.quotes


def use_adapter(monkeypatch, adapter):
    monkeypatch.setattr(market_service, "get_adapter", lambda name: adapter)
    return adapter


def test_no_enabled_source_raises(conn):
    conn.execute("UPDATE data_sources SET enabled = 0")
    conn.commit()
    with pytest.raises(market_service.MarketUnavailable, match="没有启用任何数据源"):
        market_service.fetch_market_snapshot(conn)


def test_success_persists_stocks_quotes_and_health(conn, monkeypatch):
    enable_only_source(conn, "eastmoney")
    adapter = use_adapter(monkeypatch, FakeAdapter([make_quote()]))

    result = market_service.fetch_market_snapshot(conn)

    assert result.source == "eastmoney"
    assert result.count == 1
    assert result.failures == []
    assert result.stale is False
    assert result.as_of is None
    assert conn.execute("SELECT COUNT(*) AS c FROM stocks").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) AS c FROM daily_quotes").fetchone()["c"] == 1
    health = conn.execute("SELECT * FROM source_health_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert health["ok"] == 1
    source = conn.execute("SELECT * FROM data_sources WHERE name = 'eastmoney'").fetchone()
    assert source["last_success_at"] is not None
    assert source["last_error"] is None


def test_invalid_quotes_are_filtered(conn, monkeypatch):
    enable_only_source(conn, "eastmoney")
    bad_code = make_quote(code="123", name="坏代码")
    no_name = make_quote(code="600002", name="")
    zero_close = make_quote(code="600003", close=0)
    use_adapter(monkeypatch, FakeAdapter([make_quote(), bad_code, no_name, zero_close]))

    result = market_service.fetch_market_snapshot(conn)
    assert result.count == 1


def test_too_few_quotes_marks_failure(conn, monkeypatch):
    from src.core import config as cfg

    monkeypatch.setattr(cfg, "MIN_QUOTE_COUNT", 100)
    enable_only_source(conn, "eastmoney")
    use_adapter(monkeypatch, FakeAdapter([make_quote()]))

    with pytest.raises(market_service.MarketUnavailable, match="有效条目过少"):
        market_service.fetch_market_snapshot(conn)

    source = conn.execute("SELECT * FROM data_sources WHERE name = 'eastmoney'").fetchone()
    assert "有效条目过少" in source["last_error"]
    health = conn.execute("SELECT * FROM source_health_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert health["ok"] == 0
    # 失败不能写入行情，避免用不完整快照覆盖旧数据
    assert conn.execute("SELECT COUNT(*) AS c FROM daily_quotes").fetchone()["c"] == 0


def test_fallback_to_next_source_and_keep_failure_reason(conn, monkeypatch):
    conn.execute("UPDATE data_sources SET enabled = 0")
    conn.execute("UPDATE data_sources SET enabled = 1 WHERE name IN ('eastmoney','tencent')")
    conn.commit()

    failing = FakeAdapter(error=SourceError("被墙"))
    succeed = FakeAdapter([make_quote()])
    adapters = {"eastmoney": failing, "tencent": succeed}
    monkeypatch.setattr(market_service, "get_adapter", lambda name: adapters[name])

    result = market_service.fetch_market_snapshot(conn)
    assert result.source == "tencent"
    assert any("eastmoney" in f for f in result.failures)
    assert result.failures[0].startswith("eastmoney: 被墙")


def test_universe_required_source_skipped_when_db_empty(conn, monkeypatch):
    enable_only_source(conn, "tencent")
    adapter = use_adapter(monkeypatch, FakeAdapter([make_quote()], requires_universe=True))

    with pytest.raises(market_service.MarketUnavailable, match="缺少代码全集"):
        market_service.fetch_market_snapshot(conn)
    assert adapter.calls == []


class BootstrappingAdapter(FakeAdapter):
    """模拟腾讯：自己拿代码全集后再批量抓行情。"""

    def __init__(self, quotes=None, universe_codes=None, universe_error=None):
        super().__init__(quotes, requires_universe=True)
        self.universe_codes = universe_codes or []
        self.universe_error = universe_error

    def fetch_universe(self):
        if self.universe_error:
            raise self.universe_error
        return self.universe_codes


def test_batch_source_bootstraps_universe_when_db_empty(conn, monkeypatch):
    enable_only_source(conn, "tencent")
    adapter = use_adapter(
        monkeypatch,
        BootstrappingAdapter([make_quote()], universe_codes=["600001", "600002"]),
    )

    result = market_service.fetch_market_snapshot(conn)
    assert result.source == "tencent"
    assert adapter.calls == [["600001", "600002"]]
    assert conn.execute("SELECT COUNT(*) AS c FROM stocks").fetchone()["c"] == 1


def test_universe_bootstrap_failure_is_recorded(conn, monkeypatch):
    enable_only_source(conn, "tencent")
    use_adapter(
        monkeypatch,
        BootstrappingAdapter(universe_error=SourceError("榜单接口超时")),
    )

    with pytest.raises(market_service.MarketUnavailable, match="获取代码全集失败"):
        market_service.fetch_market_snapshot(conn)

    source = conn.execute("SELECT * FROM data_sources WHERE name = 'tencent'").fetchone()
    assert "榜单接口超时" in source["last_error"]


def test_universe_passed_to_batch_adapter(conn, monkeypatch, seed):
    seed("600001", quote=make_quote())
    enable_only_source(conn, "tencent")
    adapter = use_adapter(
        monkeypatch,
        FakeAdapter([make_quote()], requires_universe=True),
    )

    market_service.fetch_market_snapshot(conn)
    assert adapter.calls == [["600001"]]


def test_all_sources_failed_falls_back_to_latest_snapshot(conn, seed, monkeypatch):
    """源全挂时不能把批次直接判死：回退上一份完整快照，并标记 stale。"""
    seed("600001", quote=make_quote())
    enable_only_source(conn, "tencent")
    use_adapter(monkeypatch, FakeAdapter(error=SourceError("超时")))

    result = market_service.fetch_market_snapshot(conn)

    assert result.source == "cache"
    assert result.stale is True
    assert result.as_of == "2026-10-30"
    assert result.count == 1
    assert result.quotes[0].code == "600001"
    assert result.quotes[0].name == "测试股份"
    assert result.failures == ["tencent: 超时"]
    # 回退只读旧数据，不能把旧快照重新写一遍或覆盖原记录
    assert conn.execute("SELECT COUNT(*) AS c FROM daily_quotes").fetchone()["c"] == 1
    # 失败必须留痕，不能因为回退成功就把源标成健康
    source = conn.execute("SELECT * FROM data_sources WHERE name = 'tencent'").fetchone()
    assert source["last_error"] == "超时"
    assert source["last_success_at"] is None
    health = conn.execute("SELECT * FROM source_health_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert health["ok"] == 0


def test_stale_snapshot_below_min_count_raises(conn, seed, monkeypatch):
    seed("600001", quote=make_quote())
    enable_only_source(conn, "tencent")
    use_adapter(monkeypatch, FakeAdapter(error=SourceError("超时")))
    monkeypatch.setattr(config, "MIN_QUOTE_COUNT", 2)

    with pytest.raises(market_service.MarketUnavailable, match="回退快照"):
        market_service.fetch_market_snapshot(conn)


def test_refresh_quotes_delegates(conn, monkeypatch):
    enable_only_source(conn, "eastmoney")
    use_adapter(monkeypatch, FakeAdapter([make_quote()]))
    assert market_service.refresh_quotes(conn).count == 1


def test_all_sources_unavailable_lists_each_failure(conn, monkeypatch):
    monkeypatch.setattr(config, "MIN_QUOTE_COUNT", 1)
    use_adapter(monkeypatch, FakeAdapter(error=SourceError("超时")))
    with pytest.raises(market_service.MarketUnavailable) as excinfo:
        market_service.fetch_market_snapshot(conn)
    message = str(excinfo.value)
    assert message.count("超时") == 3
