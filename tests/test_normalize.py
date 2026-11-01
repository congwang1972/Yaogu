"""来源字段归一化：单位、前缀、涨跌停幅度、交易日期。"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.integrations.sources.base import (
    calc_limit_up,
    limit_ratio,
    market_prefix,
    normalize_code,
    parse_trade_date,
    to_float,
    to_int,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), (3, 3.0), (4.5, 4.5), ("", None), ("-", None), ("--", None),
     ("None", None), ("1,234.5", 1234.5), ("abc", None), (" 5.2 ", 5.2)],
)
def test_to_float(raw, expected):
    assert to_float(raw) == expected


def test_to_int():
    assert to_int("12.9") == 12
    assert to_int(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("sh600001", "600001"), ("SZ000001", "000001"), ("600001.SH", "600001"),
     ("bj430047", "430047"), (" 300750 ", "300750")],
)
def test_normalize_code(raw, expected):
    assert normalize_code(raw) == expected


@pytest.mark.parametrize(
    ("code", "prefix"),
    [("600001", "sh"), ("900901", "sh"), ("000001", "sz"), ("300750", "sz"),
     ("830799", "bj"), ("430047", "bj"), ("700000", "sh")],
)
def test_market_prefix(code, prefix):
    assert market_prefix(code) == prefix


@pytest.mark.parametrize(
    ("code", "name", "ratio"),
    [("600001", "测试", 0.10), ("600001", "*ST测试", 0.05), ("300750", "宁德", 0.20),
     ("688001", "科创", 0.20), ("830799", "北交", 0.30)],
)
def test_limit_ratio(code, name, ratio):
    assert limit_ratio(code, name) == ratio


def test_calc_limit_up():
    assert calc_limit_up("600001", "测试", 10.0) == 11.0
    assert calc_limit_up("300750", "宁德", 10.0) == 12.0
    assert calc_limit_up("600001", "测试", None) is None
    assert calc_limit_up("600001", "测试", 0) is None


def test_parse_trade_date():
    assert parse_trade_date("20261030") == "2026-10-30"
    assert parse_trade_date("2026-10-30") == "2026-10-30"
    # 非法输入回退当天，保证入库字段永远是 YYYY-MM-DD
    assert parse_trade_date("") == datetime.now().strftime("%Y-%m-%d")
    assert parse_trade_date(None) == datetime.now().strftime("%Y-%m-%d")
