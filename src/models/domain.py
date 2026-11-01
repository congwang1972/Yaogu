"""领域模型：服务层内部流通的数据结构，与数据库行、HTTP 契约解耦。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

GateStatus = Literal["pass", "fail", "skipped", "unavailable"]


@dataclass(slots=True)
class Quote:
    """归一化后的行情快照。市值统一为亿元，涨跌幅/换手率为百分比。"""

    code: str
    name: str
    trade_date: str
    close: float
    pre_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pct_chg: float | None = None
    volume: int | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    total_mv: float | None = None
    float_mv: float | None = None
    limit_up: float | None = None
    status: str = "normal"
    source: str = ""
    fetched_at: str = ""

    @property
    def is_st(self) -> bool:
        return "ST" in self.name.upper()


@dataclass(slots=True)
class GateResult:
    gate: str
    label: str
    status: GateStatus
    actual_value: str | None
    threshold: str
    reason: str

    @property
    def passed(self) -> bool:
        # 这里表示「是否否决」而不是「数据是否合格」：
        # skipped 是门槛未启用，不能一票否决；unavailable 数据缺失则必须人工确认，不能放行。
        return self.status in ("pass", "skipped")

    def to_row(self) -> tuple:
        return (self.gate, 1 if self.passed else 0, self.actual_value, self.threshold, self.reason)


@dataclass(slots=True)
class PatternResult:
    key: str
    label: str
    status: GateStatus
    evidence: str | None = None


@dataclass(slots=True)
class ScoreDetail:
    key: str
    label: str
    type: Literal["add", "minus"]
    delta: float
    weight: float
    source: str
    available: bool      # 计算依据是否可得（不可得时界面显示“待确认”，且不计分）
    met: bool = False    # 规则是否满足
    evidence: str | None = None

    @property
    def points(self) -> float:
        if not self.available or not self.met:
            return 0.0
        return self.delta * self.weight


@dataclass(slots=True)
class ScoreResult:
    code: str
    total: float
    details: list[ScoreDetail] = field(default_factory=list)


@dataclass(slots=True)
class FetchResult:
    quotes: list[Quote]
    source: str
    count: int
    elapsed_ms: int
    failures: list[str] = field(default_factory=list)
    # 所有源都失败时回退最近一份快照；stale=True 表示这批数据不是本次抓取的，
    # 调用方必须把 as_of 和降级原因透出给界面，不能当作当日行情使用。
    stale: bool = False
    as_of: str | None = None
