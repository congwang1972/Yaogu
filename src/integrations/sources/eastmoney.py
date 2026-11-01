"""东方财富全市场快照（主源）。

选它的理由：一次请求可拿到全市场约 5000 只股票，且同时提供总市值、
流通市值、换手率，正是硬门槛所需字段。免费、无需鉴权，但对出口 IP 敏感。
"""
from __future__ import annotations

import time
from datetime import datetime

from src.core.db import now_iso
from src.integrations.sources.base import (
    SourceAdapter,
    SourceError,
    calc_limit_up,
    normalize_code,
    parse_trade_date,
    to_float,
    to_int,
)
from src.models.domain import Quote

LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
# 沪深主板 + 创业板 + 科创板 + 北交所
MARKET_FILTER = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FIELDS = "f2,f3,f4,f5,f6,f8,f12,f13,f14,f15,f16,f17,f18,f20,f21,f124"
# 2026-11 实测：接口无视 pz，固定每页 100 条（且会 302 到 push2delay）。
# 不能再拿「返回条数 < 请求条数」判断末页，否则永远只抓第一页。
PAGE_SIZE = 100
MAX_PAGES = 200


class EastmoneyAdapter(SourceAdapter):
    name = "eastmoney"

    def fetch_all(self, universe: list[str] | None = None) -> list[Quote]:
        quotes: list[Quote] = []
        page = 1
        with self._client() as client:
            while page <= MAX_PAGES:
                payload = self._request(client, page)
                data = payload.get("data") or {}
                diff = data.get("diff") or []
                if isinstance(diff, dict):  # 某些参数组合返回以序号为 key 的 dict
                    diff = list(diff.values())
                if not diff:
                    break
                quotes.extend(self._parse_row(row) for row in diff)
                total = int(data.get("total") or 0)
                # 以接口返回的 total 为准分页；total 缺失时靠下一页返回空数组收敛
                if total and len(quotes) >= total:
                    break
                page += 1
            else:
                raise SourceError(f"东方财富分页超过 {MAX_PAGES} 页仍未结束")

        if universe:
            wanted = set(universe)
            quotes = [q for q in quotes if q.code in wanted]
        return quotes

    def test(self) -> tuple[bool, int | None, str | None]:
        """探活只取 5 条：全量分页要 60 次请求，不能拿来做连接测试。"""
        start = time.perf_counter()
        try:
            with self._client() as client:
                payload = self._request(client, 1, page_size=5)
            data = payload.get("data") or {}
            diff = data.get("diff") or []
            if isinstance(diff, dict):
                diff = list(diff.values())
            latency = int((time.perf_counter() - start) * 1000)
            if not diff:
                return False, latency, "返回空结果"
            return True, latency, None
        except Exception as exc:
            latency = int((time.perf_counter() - start) * 1000)
            return False, latency, str(exc)[:300]

    def _request(self, client, page: int, page_size: int = PAGE_SIZE) -> dict:
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": MARKET_FILTER,
            "fields": FIELDS,
        }
        try:
            return self._get(client, LIST_URL, params=params).json()
        except Exception as exc:
            raise SourceError(f"东方财富请求失败：{exc}") from exc

    def _parse_row(self, row: dict) -> Quote:
        code = normalize_code(str(row.get("f12") or ""))
        name = str(row.get("f14") or "").strip()
        pre_close = to_float(row.get("f18"))
        total_mv = to_float(row.get("f20"))
        float_mv = to_float(row.get("f21"))
        return Quote(
            code=code,
            name=name,
            trade_date=parse_trade_date(_epoch_to_date(row.get("f124"))),
            close=to_float(row.get("f2")) or 0.0,
            pre_close=pre_close,
            open=to_float(row.get("f17")),
            high=to_float(row.get("f15")),
            low=to_float(row.get("f16")),
            pct_chg=to_float(row.get("f3")),
            volume=to_int(row.get("f5")),
            amount=to_float(row.get("f6")),
            turnover_rate=to_float(row.get("f8")),
            # 东财返回单位为「元」，统一换算成「亿元」
            total_mv=round(total_mv / 1e8, 4) if total_mv is not None else None,
            float_mv=round(float_mv / 1e8, 4) if float_mv is not None else None,
            limit_up=calc_limit_up(code, name, pre_close),
            status="suspended" if to_float(row.get("f2")) in (None, 0) else "normal",
            source=self.name,
            fetched_at=now_iso(),
        )


def _epoch_to_date(value: object) -> str | None:
    ts = to_int(value)
    if not ts:
        return None
    return datetime.fromtimestamp(ts).strftime("%Y%m%d")
