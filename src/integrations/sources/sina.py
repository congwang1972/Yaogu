"""新浪行情（第三备用源）。

新浪只返回价格与成交量，不提供市值与换手率，因此作为最后兜底：
能被抓到的字段填上，缺失字段留 None，由门槛层标记为「数据缺失」而不是默认放行。
"""
from __future__ import annotations

from src.core.db import now_iso
from src.integrations.sources.base import (
    SourceAdapter,
    SourceError,
    calc_limit_up,
    market_prefix,
    normalize_code,
    parse_trade_date,
    to_float,
    to_int,
)
from src.models.domain import Quote

BATCH_SIZE = 500
URL = "https://hq.sinajs.cn/list="


class SinaAdapter(SourceAdapter):
    name = "sina"
    requires_universe = True

    def fetch_all(self, universe: list[str] | None = None) -> list[Quote]:
        if not universe:
            raise SourceError("新浪源需要代码全集，请在主源成功后再试")
        quotes: list[Quote] = []
        with self._client() as client:
            for start in range(0, len(universe), BATCH_SIZE):
                batch = universe[start:start + BATCH_SIZE]
                text = self._request(client, batch)
                quotes.extend(self._parse_text(text))
        if len(quotes) < len(universe) * 0.5:
            raise SourceError(f"新浪源返回不完整：{len(quotes)}/{len(universe)}")
        return quotes

    def _request(self, client, codes: list[str]) -> str:
        query = ",".join(f"{market_prefix(c)}{c}" for c in codes)
        try:
            # 新浪要求带 Referer，否则返回 403
            resp = client.get(URL + query, headers={"Referer": "https://finance.sina.com.cn"})
            resp.raise_for_status()
            return resp.content.decode("gbk", errors="replace")
        except Exception as exc:
            raise SourceError(f"新浪源请求失败：{exc}") from exc

    def _parse_text(self, text: str) -> list[Quote]:
        quotes = []
        for line in text.split(";"):
            if "=" not in line:
                continue
            head, payload = line.split('="', 1)
            payload = payload.strip('"\n ')
            parts = payload.split(",")
            if len(parts) < 32:
                continue
            code = normalize_code(head.rsplit("_", 1)[-1])
            name = parts[0].strip()
            close = to_float(parts[3])
            if not code or close is None or close == 0:
                continue
            pre_close = to_float(parts[2])
            quotes.append(
                Quote(
                    code=code,
                    name=name,
                    trade_date=parse_trade_date(parts[30].replace("-", "")),
                    close=close,
                    pre_close=pre_close,
                    open=to_float(parts[1]),
                    high=to_float(parts[4]),
                    low=to_float(parts[5]),
                    pct_chg=round((close - pre_close) / pre_close * 100, 2) if pre_close else None,
                    volume=to_int(parts[8]),
                    amount=to_float(parts[9]),
                    turnover_rate=None,
                    total_mv=None,
                    float_mv=None,
                    limit_up=calc_limit_up(code, name, pre_close),
                    status="normal",
                    source=self.name,
                    fetched_at=now_iso(),
                )
            )
        return quotes
