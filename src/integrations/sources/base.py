"""行情源适配器契约与归一化工具。

每个适配器负责把外部字段转成内部 Quote：市值统一亿元、涨跌幅/换手率统一百分比、
日期统一 YYYY-MM-DD。适配器只关心外部世界，不碰数据库。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from src.core import config
from src.core.db import now_iso
from src.models.domain import Quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
# 测连用的探针代码。批量源没有代码全集时也要能验证网络与报文格式，
# 不能用全市场抓取（既慢又会被 MIN_QUOTE_COUNT 误判为失败）。
PROBE_UNIVERSE = ["600000"]


class SourceError(Exception):
    """单个数据源抓取失败。调用方据此降级到下一个源。"""


def to_float(value: object) -> float | None:
    """把 '-'、''、None 以及带单位字符串统一成 float。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--", "None"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def normalize_code(raw: str) -> str:
    """去掉 sh/sz/bj 前缀与 .SH/.SZ 后缀，保留 6 位数字。"""
    text = raw.strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if "." in text:
        text = text.split(".")[0]
    return text.strip()


def market_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    if code.startswith(("4", "8")):
        return "bj"
    return "sh"


def limit_ratio(code: str, name: str) -> float:
    """涨跌停幅度：ST 5%、科创/创业 20%、北交所 30%、其余 10%。"""
    if "ST" in name.upper():
        return 0.05
    if code.startswith("688") or code.startswith("300"):
        return 0.20
    if code.startswith(("4", "8")):
        return 0.30
    return 0.10


def calc_limit_up(code: str, name: str, pre_close: float | None) -> float | None:
    if pre_close is None or pre_close <= 0:
        return None
    return round(pre_close * (1 + limit_ratio(code, name)), 2)


def parse_trade_date(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[:4].isdigit():
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")


class SourceAdapter(ABC):
    name: str = "base"
    # 是否需要外部提供代码全集（只有“批量按代码查”的源才需要）
    requires_universe: bool = False

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout or config.HTTP_TIMEOUT_SECONDS

    @abstractmethod
    def fetch_all(self, universe: list[str] | None = None) -> list[Quote]:
        """抓取全市场（或给定代码列表）的行情快照。失败抛 SourceError。"""

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": UA},
            follow_redirects=True,
        )

    def _get(self, client: httpx.Client, url: str, **kwargs) -> httpx.Response:
        """带重试的 GET：只重试网络错误与 5xx，4xx 立即失败。

        免费源在云机房边缘节点上会偶发 502；不重试就会把「一次抖动」
        记成整源不可用，进而错误地降级或跳过当天数据。
        """
        attempts = max(1, config.HTTP_MAX_RETRIES + 1)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = client.get(url, **kwargs)
                if resp.status_code >= 500:
                    raise SourceError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError, SourceError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def fetch_universe(self) -> list[str]:
        """批量源可自行获取代码全集；不支持的源显式失败，由调用方降级。"""
        raise SourceError(f"{self.name} 不支持获取代码全集")

    def test(self) -> tuple[bool, int | None, str | None]:
        start = time.perf_counter()
        try:
            # 批量源用单只探针验证连通性与报文，不依赖数据库里是否已有全集
            universe = PROBE_UNIVERSE if self.requires_universe else None
            quotes = self.fetch_all(universe)
            latency = int((time.perf_counter() - start) * 1000)
            if not quotes:
                return False, latency, "返回空结果"
            # 只有全市场抓取才用最小条目数兜底；探针本来就只有一条
            if universe is None and len(quotes) < config.MIN_QUOTE_COUNT:
                return False, latency, f"返回条目过少：{len(quotes)}"
            return True, latency, None
        except Exception as exc:  # 探测接口不抛异常，把失败原因返回给前端
            latency = int((time.perf_counter() - start) * 1000)
            return False, latency, str(exc)[:300]
