"""腾讯行情（备用源）。

腾讯没有「一次拿全市场」的公开接口，因此需要先有代码全集：
首次运行时由主源建库，之后主源故障可用库内代码作为 universe 降级。
字段里自带涨停价（索引 47），比分比推断更可靠。
"""
from __future__ import annotations

from src.core.db import now_iso
from src.integrations.sources.base import (
    SourceAdapter,
    SourceError,
    market_prefix,
    normalize_code,
    parse_trade_date,
    to_float,
    to_int,
)
from src.models.domain import Quote

BATCH_SIZE = 800
URL = "https://qt.gtimg.cn/q="
# 代码全集接口。东财被云 IP 屏蔽时，腾讯可独立完成冷启动，不再卡在「缺代码全集」。
RANK_URL = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
RANK_PAGE = 200


class TencentAdapter(SourceAdapter):
    name = "tencent"
    requires_universe = True

    def fetch_all(self, universe: list[str] | None = None) -> list[Quote]:
        if not universe:
            raise SourceError("腾讯源需要代码全集，请在主源成功后再试")
        quotes: list[Quote] = []
        with self._client() as client:
            for start in range(0, len(universe), BATCH_SIZE):
                batch = universe[start:start + BATCH_SIZE]
                text = self._request(client, batch)
                quotes.extend(self._parse_text(text))
        if len(quotes) < len(universe) * 0.8:
            raise SourceError(f"腾讯源返回不完整：{len(quotes)}/{len(universe)}")
        return quotes

    def fetch_universe(self) -> list[str]:
        """用腾讯涨幅榜翻页拿到 A 股代码全集（约 4600 只）。"""
        codes: list[str] = []
        seen: set[str] = set()
        offset = 0
        with self._client() as client:
            while True:
                try:
                    payload = self._get(
                        client,
                        RANK_URL,
                        params={
                            "board_code": "aStock",
                            "sort_type": "price",
                            "direct": "down",
                            "offset": offset,
                            "count": RANK_PAGE,
                        },
                    ).json()
                except Exception as exc:
                    raise SourceError(f"腾讯源获取代码全集失败：{exc}") from exc
                if payload.get("code") != 0:
                    raise SourceError(f"腾讯源代码全集返回异常：{payload.get('msg') or payload.get('code')}")
                data = payload.get("data") or {}
                rows = data.get("rank_list") or []
                if not rows:
                    break
                for row in rows:
                    code = normalize_code(str(row.get("code") or ""))
                    if code and code not in seen:
                        seen.add(code)
                        codes.append(code)
                offset += len(rows)
                total = int(data.get("total") or 0)
                if total and offset >= total:
                    break
        if not codes:
            raise SourceError("腾讯源代码全集为空")
        return codes

    def _request(self, client, codes: list[str]) -> str:
        query = ",".join(f"{market_prefix(c)}{c}" for c in codes)
        try:
            resp = self._get(client, URL + query)
            return resp.content.decode("gbk", errors="replace")
        except Exception as exc:
            raise SourceError(f"腾讯源请求失败：{exc}") from exc

    def _parse_text(self, text: str) -> list[Quote]:
        quotes = []
        for line in text.split(";"):
            if "=" not in line:
                continue
            payload = line.split('="', 1)[-1].strip('"\n ')
            parts = payload.split("~")
            if len(parts) < 49:
                continue
            quote = self._parse_parts(parts)
            if quote:
                quotes.append(quote)
        return quotes

    def _parse_parts(self, p: list[str]) -> Quote | None:
        code = normalize_code(p[2])
        name = p[1].strip()
        if not code:
            return None
        close = to_float(p[3])
        if close is None:
            return None
        return Quote(
            code=code,
            name=name,
            trade_date=parse_trade_date(p[30]),
            close=close,
            pre_close=to_float(p[4]),
            open=to_float(p[5]),
            high=to_float(p[33]),
            low=to_float(p[34]),
            pct_chg=to_float(p[32]),
            volume=to_int(p[36]),
            amount=None,
            turnover_rate=to_float(p[38]),
            total_mv=to_float(p[45]),   # 腾讯单位为「亿元」
            float_mv=to_float(p[44]),
            limit_up=to_float(p[47]),
            status="normal",
            source=self.name,
            fetched_at=now_iso(),
        )
