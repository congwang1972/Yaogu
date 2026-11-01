"""数据源适配器：用 MockTransport 固定报文，验证字段归一化。"""
from __future__ import annotations

import httpx
import pytest

from src.integrations.sources import SOURCE_REGISTRY, get_adapter
from src.integrations.sources.base import PROBE_UNIVERSE, SourceAdapter, SourceError
from src.integrations.sources.eastmoney import EastmoneyAdapter
from src.integrations.sources.sina import SinaAdapter
from src.integrations.sources.tencent import TencentAdapter
from src.models.domain import Quote


def mock_client(handler, monkeypatch, adapter_cls):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(adapter_cls, "_client", lambda self: client)
    return client


def em_row(**overrides) -> dict:
    row = {
        "f2": 5.0, "f3": 2.04, "f4": 0.1, "f5": 123456, "f6": 9.9e8, "f8": 18.5,
        "f12": "600001", "f13": 1, "f14": "测试股份", "f15": 5.2, "f16": 4.8,
        "f17": 5.0, "f18": 4.9, "f20": 3.0e9, "f21": 2.5e9, "f124": 1793318400,
    }
    row.update(overrides)
    return row


def test_eastmoney_parses_and_converts_units(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"total": 2, "diff": [em_row(), em_row(f12="000002", f14="万科", f2=0)]}})

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    quotes = EastmoneyAdapter().fetch_all()

    assert len(quotes) == 2
    first = quotes[0]
    assert first.code == "600001"
    assert first.name == "测试股份"
    # 东财市值单位是元，内部统一成亿元
    assert first.total_mv == pytest.approx(30.0)
    assert first.float_mv == pytest.approx(25.0)
    assert first.limit_up == pytest.approx(5.39)
    assert first.status == "normal"
    assert quotes[1].status == "suspended"


def test_eastmoney_supports_dict_diff_and_universe_filter(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"total": 2, "diff": {"0": em_row(), "1": em_row(f12="000002")}}})

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    quotes = EastmoneyAdapter().fetch_all(universe=["000002"])
    assert [q.code for q in quotes] == ["000002"]


def test_eastmoney_paginates_until_total(monkeypatch):
    """接口固定每页 100 条，必须按 total 翻页而不是按返回条数判断末页。"""
    total = 250

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pn"])
        start = (page - 1) * 100
        count = max(0, min(100, total - start))
        diff = [em_row(f12=str(600000 + start + i)) for i in range(count)]
        return httpx.Response(200, json={"data": {"total": total, "diff": diff}})

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    quotes = EastmoneyAdapter().fetch_all()
    assert len(quotes) == total
    assert quotes[-1].code == "600249"


def test_eastmoney_test_probes_one_small_page(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["pn"] = request.url.params["pn"]
        seen["pz"] = request.url.params["pz"]
        return httpx.Response(200, json={"data": {"total": 5926, "diff": [em_row()]}})

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    ok, _, error = EastmoneyAdapter().test()
    assert ok is True
    assert error is None
    assert seen == {"pn": "1", "pz": "5"}


def test_eastmoney_retries_transient_5xx(monkeypatch):
    monkeypatch.setattr("src.integrations.sources.base.time.sleep", lambda _: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"data": {"total": 1, "diff": [em_row()]}})

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    quotes = EastmoneyAdapter().fetch_all()
    assert calls["n"] == 3
    assert len(quotes) == 1


def test_eastmoney_request_error_becomes_source_error(monkeypatch):
    monkeypatch.setattr("src.integrations.sources.base.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    mock_client(handler, monkeypatch, EastmoneyAdapter)
    with pytest.raises(SourceError):
        EastmoneyAdapter().fetch_all()


def tencent_payload(code="600001", name="测试股份") -> str:
    parts = [""] * 49
    parts[1] = name
    parts[2] = code
    parts[3] = "5.10"
    parts[4] = "5.00"
    parts[5] = "5.02"
    parts[30] = "20261030150000"
    parts[32] = "2.00"
    parts[33] = "5.20"
    parts[34] = "4.90"
    parts[36] = "12345"
    parts[38] = "18.5"
    parts[44] = "25.0"
    parts[45] = "30.0"
    parts[47] = "5.50"
    return f'v_sh{code}="' + "~".join(parts) + '";'


def test_tencent_parses_limit_up_and_mv(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tencent_payload().encode("gbk"))

    mock_client(handler, monkeypatch, TencentAdapter)
    quotes = TencentAdapter().fetch_all(["600001"])
    q = quotes[0]
    assert q.code == "600001"
    assert q.close == 5.10
    assert q.limit_up == 5.50  # 腾讯直接提供涨停价
    assert q.total_mv == 30.0
    assert q.trade_date == "2026-10-30"


def test_tencent_requires_universe():
    with pytest.raises(SourceError):
        TencentAdapter().fetch_all([])


def test_tencent_fetches_universe_by_paging(monkeypatch):
    total = 250

    def handler(request: httpx.Request) -> httpx.Response:
        assert "getBoardRankList" in str(request.url)
        offset = int(request.url.params["offset"])
        count = max(0, min(200, total - offset))
        rows = [{"code": f"sh{600001 + offset + i}"} for i in range(count)]
        return httpx.Response(200, json={"code": 0, "data": {"total": total, "rank_list": rows}})

    mock_client(handler, monkeypatch, TencentAdapter)
    codes = TencentAdapter().fetch_universe()
    assert len(codes) == total
    assert codes[0] == "600001"
    assert codes[-1] == "600250"


def test_tencent_incomplete_response_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"v_sh600001=\"\";")

    mock_client(handler, monkeypatch, TencentAdapter)
    with pytest.raises(SourceError):
        TencentAdapter().fetch_all(["600001", "600002"])


def sina_payload(code="600001", close="5.10") -> str:
    parts = [""] * 32
    parts[0] = "测试股份"
    parts[1] = "5.02"
    parts[2] = "5.00"
    parts[3] = close
    parts[4] = "5.20"
    parts[5] = "4.90"
    parts[8] = "12345"
    parts[9] = "600000"
    parts[30] = "2026-10-30"
    parts[31] = "15:00:00"
    return f'var hq_str_sh{code}="' + ",".join(parts) + '";'


def test_sina_parses_without_market_cap(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sina_payload().encode("gbk"))

    mock_client(handler, monkeypatch, SinaAdapter)
    quotes = SinaAdapter().fetch_all(["600001"])
    q = quotes[0]
    assert q.close == 5.10
    assert q.pct_chg == pytest.approx(2.0)
    # 新浪没有市值字段，必须为 None 而不是 0
    assert q.total_mv is None
    assert q.limit_up == pytest.approx(5.50)


def test_sina_requires_universe_and_rejects_incomplete(monkeypatch):
    with pytest.raises(SourceError):
        SinaAdapter().fetch_all(None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    mock_client(handler, monkeypatch, SinaAdapter)
    with pytest.raises(SourceError):
        SinaAdapter().fetch_all(["600001", "600002", "600003"])


class _GoodAdapter(SourceAdapter):
    name = "good"

    def fetch_all(self, universe=None):
        return [Quote(code="600001", name="测试", trade_date="2026-10-30", close=5.0)]


class _BadAdapter(SourceAdapter):
    name = "bad"

    def fetch_all(self, universe=None):
        raise RuntimeError("network down")


def test_adapter_test_reports_ok(db_path):
    ok, latency, error = _GoodAdapter().test()
    assert ok is True
    assert latency is not None
    assert error is None


def test_adapter_test_reports_failure(db_path):
    ok, latency, error = _BadAdapter().test()
    assert ok is False
    assert "network down" in (error or "")


def test_adapter_test_requires_enough_quotes(db_path, monkeypatch):
    from src.core import config

    monkeypatch.setattr(config, "MIN_QUOTE_COUNT", 10)
    ok, _, error = _GoodAdapter().test()
    assert ok is False
    assert "过少" in (error or "")


def test_batch_adapter_test_probes_single_code(db_path, monkeypatch):
    """批量源测连只取一只探针，不能被全市场最小条目数误判。"""
    from src.core import config

    monkeypatch.setattr(config, "MIN_QUOTE_COUNT", 10)

    class _BatchAdapter(SourceAdapter):
        name = "batch"
        requires_universe = True

        def __init__(self):
            super().__init__()
            self.universes = []

        def fetch_all(self, universe=None):
            self.universes.append(universe)
            return [Quote(code="600000", name="浦发银行", trade_date="2026-10-30", close=10.0)]

    adapter = _BatchAdapter()
    ok, _, error = adapter.test()
    assert ok is True
    assert error is None
    assert adapter.universes == [PROBE_UNIVERSE]


def test_registry():
    assert get_adapter("eastmoney").name == "eastmoney"
    assert set(SOURCE_REGISTRY) == {"eastmoney", "tencent", "sina"}
    with pytest.raises(SourceError):
        get_adapter("unknown")
