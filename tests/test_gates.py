"""硬门槛与形态判据：重点覆盖边界值（PRD §3.2 含边界）。"""
from __future__ import annotations

import pytest

from src.models.domain import Quote
from src.services import gates

THRESHOLDS = {
    "min_total_mv": 20.0,
    "max_total_mv": 45.0,
    "min_price": 3.0,
    "max_price": 10.0,
    "max_float_mv": 40.0,
    "enable_float_mv": False,
}


def quote(**kwargs) -> Quote:
    base = dict(
        code="600001",
        name="测试股份",
        trade_date="2026-10-30",
        close=5.0,
        pre_close=4.9,
        open=5.0,
        high=5.2,
        low=4.8,
        turnover_rate=20.0,
        total_mv=30.0,
        float_mv=25.0,
        limit_up=5.39,
    )
    base.update(kwargs)
    return Quote(**base)


@pytest.mark.parametrize(
    ("mv", "status"),
    [
        (20.0, "pass"),   # 下边界含
        (45.0, "pass"),   # 上边界含
        (19.99, "fail"),
        (45.01, "fail"),
    ],
)
def test_total_mv_boundaries(mv, status):
    result = gates.gate_total_mv(quote(total_mv=mv), THRESHOLDS)
    assert result.status == status
    assert result.gate == "total_mv"


def test_total_mv_missing_is_unavailable():
    result = gates.gate_total_mv(quote(total_mv=None), THRESHOLDS)
    assert result.status == "unavailable"
    assert result.passed is False
    assert "缺失" in result.reason


@pytest.mark.parametrize(
    ("price", "status"),
    [(3.0, "pass"), (10.0, "pass"), (2.99, "fail"), (10.01, "fail")],
)
def test_price_boundaries(price, status):
    assert gates.gate_price(quote(close=price), THRESHOLDS).status == status


@pytest.mark.parametrize("price", [None, 0.0, -1.0])
def test_price_missing_or_invalid_is_unavailable(price):
    assert gates.gate_price(quote(close=price), THRESHOLDS).status == "unavailable"


def test_st_stock_fails():
    result = gates.gate_st_suspended(quote(name="*ST测试"), THRESHOLDS)
    assert result.status == "fail"
    assert "ST" in result.reason


@pytest.mark.parametrize("state", ["suspended", "delisting"])
def test_suspended_and_delisting_fail(state):
    assert gates.gate_st_suspended(quote(status=state), THRESHOLDS).status == "fail"


def test_normal_stock_passes():
    result = gates.gate_st_suspended(quote(), THRESHOLDS)
    assert result.status == "pass"
    assert result.passed is True


def test_float_mv_disabled_is_skipped_and_does_not_veto():
    result = gates.gate_float_mv(quote(float_mv=999), THRESHOLDS)
    assert result.status == "skipped"
    assert result.passed is True  # 未启用 ≠ 不合格，不能因此淘汰
    assert gates.all_passed([result]) is True


def test_float_mv_enabled_boundaries():
    t = {**THRESHOLDS, "enable_float_mv": True}
    assert gates.gate_float_mv(quote(float_mv=40.0), t).status == "pass"
    assert gates.gate_float_mv(quote(float_mv=40.01), t).status == "fail"
    assert gates.gate_float_mv(quote(float_mv=None), t).status == "unavailable"


def test_evaluate_hard_gates_does_not_short_circuit():
    results = gates.evaluate_hard_gates(quote(name="ST测试", total_mv=None), THRESHOLDS)
    assert len(results) == len(gates.HARD_GATES)
    assert {r.gate for r in results} == {"total_mv", "price", "st_suspended", "float_mv"}


def test_all_passed():
    assert gates.all_passed([gates.gate_total_mv(quote(), THRESHOLDS)]) is True
    assert gates.all_passed([gates.gate_total_mv(quote(total_mv=1), THRESHOLDS)]) is False


def test_detect_patterns_first_board_one_word_and_turnover():
    # 今日涨停、昨日未涨停、开=收=低 → 首板 + 一字 + 健康换手
    q = quote(close=5.39, pre_close=4.9, open=5.39, low=5.39, limit_up=5.39, turnover_rate=20.0)
    prev = quote(close=4.9, pre_close=4.85, limit_up=5.34)
    patterns = {p.key: p for p in gates.detect_patterns(q, prev)}
    assert patterns["first_board"].status == "pass"
    assert patterns["one_word"].status == "pass"
    assert patterns["healthy_turnover"].status == "pass"
    assert patterns["ladder"].status == "unavailable"


def test_detect_patterns_not_first_board_when_previous_also_limit():
    q = quote(close=5.39, pre_close=4.9, limit_up=5.39)
    prev = quote(close=4.9, pre_close=4.45, limit_up=4.9)
    patterns = {p.key: p for p in gates.detect_patterns(q, prev)}
    assert patterns["first_board"].status == "fail"


def test_detect_patterns_missing_fields_are_unavailable():
    q = quote(limit_up=None, pre_close=None, turnover_rate=None)
    patterns = {p.key: p for p in gates.detect_patterns(q, None)}
    assert patterns["first_board"].status == "unavailable"
    assert patterns["one_word"].status == "unavailable"
    assert patterns["healthy_turnover"].status == "unavailable"


def test_detect_patterns_without_prev_quote_still_judges_first_board():
    q = quote(close=5.39, pre_close=4.9, limit_up=5.39, open=5.0, low=4.8)
    patterns = {p.key: p for p in gates.detect_patterns(q, None)}
    assert patterns["first_board"].status == "pass"
    assert patterns["one_word"].status == "fail"


def test_pattern_as_gate_result():
    pattern = gates.detect_patterns(quote(), None)[-1]
    result = gates.pattern_as_gate_result(pattern)
    assert result.gate == "ladder"
    assert result.status == "unavailable"
    assert result.passed is False
