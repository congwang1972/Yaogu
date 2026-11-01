"""硬门槛规则注册表。

每条门槛都是纯函数：输入行情 + 阈值，输出结构化判定。纯函数的收益是
可以直接单测边界值，也让「淘汰原因」与「实测值」天然成对，保证 AC-04。
"""
from __future__ import annotations

from typing import Callable

from src.models.domain import GateResult, PatternResult, Quote

Thresholds = dict[str, float | bool]


def _fmt(value: float | None, unit: str) -> str:
    return f"{value:g}{unit}" if value is not None else "缺失"


def gate_total_mv(q: Quote, t: Thresholds) -> GateResult:
    lo, hi = float(t["min_total_mv"]), float(t["max_total_mv"])
    threshold = f"{lo:g}–{hi:g}亿元（含边界）"
    if q.total_mv is None:
        return GateResult("total_mv", "总市值", "unavailable", None, threshold, "总市值数据缺失")
    ok = lo <= q.total_mv <= hi
    return GateResult(
        "total_mv", "总市值", "pass" if ok else "fail", _fmt(q.total_mv, "亿"), threshold,
        "在区间内" if ok else f"{q.total_mv:g}亿 不在 {lo:g}–{hi:g}亿 区间",
    )


def gate_price(q: Quote, t: Thresholds) -> GateResult:
    lo, hi = float(t["min_price"]), float(t["max_price"])
    threshold = f"{lo:g}–{hi:g}元（含边界）"
    if q.close is None or q.close <= 0:
        return GateResult("price", "收盘价", "unavailable", None, threshold, "收盘价数据缺失")
    ok = lo <= q.close <= hi
    return GateResult(
        "price", "收盘价", "pass" if ok else "fail", _fmt(q.close, "元"), threshold,
        "在区间内" if ok else f"{q.close:g}元 不在 {lo:g}–{hi:g}元 区间",
    )


def gate_st_suspended(q: Quote, t: Thresholds) -> GateResult:
    threshold = "非 ST / 非退市风险 / 未停牌"
    if q.is_st:
        return GateResult("st_suspended", "ST 与交易状态", "fail", q.name, threshold, "名称含 ST，属于风险警示股")
    if q.status in {"suspended", "delisting"}:
        return GateResult(
            "st_suspended", "ST 与交易状态", "fail", q.status, threshold,
            "停牌或退市风险" if q.status == "suspended" else "退市风险",
        )
    return GateResult("st_suspended", "ST 与交易状态", "pass", "正常交易", threshold, "正常交易")


def gate_float_mv(q: Quote, t: Thresholds) -> GateResult:
    hi = float(t["max_float_mv"])
    threshold = f"≤{hi:g}亿元（含边界）"
    if not t.get("enable_float_mv", False):
        return GateResult("float_mv", "流通市值", "skipped", _fmt(q.float_mv, "亿"), threshold, "该门槛未启用")
    if q.float_mv is None:
        return GateResult("float_mv", "流通市值", "unavailable", None, threshold, "流通市值数据缺失")
    ok = q.float_mv <= hi
    return GateResult(
        "float_mv", "流通市值", "pass" if ok else "fail", _fmt(q.float_mv, "亿"), threshold,
        "在区间内" if ok else f"{q.float_mv:g}亿 > {hi:g}亿",
    )


HARD_GATES: list[Callable[[Quote, Thresholds], GateResult]] = [
    gate_total_mv,
    gate_price,
    gate_st_suspended,
    gate_float_mv,
]


def evaluate_hard_gates(q: Quote, thresholds: Thresholds) -> list[GateResult]:
    """全部门槛都执行，不短路——详情页需要完整判定，而不只是第一个失败项。"""
    return [gate(q, thresholds) for gate in HARD_GATES]


def all_passed(results: list[GateResult]) -> bool:
    return all(r.passed for r in results)


def detect_patterns(q: Quote, prev: Quote | None = None) -> list[PatternResult]:
    """形态判据。数据不足时返回 unavailable，绝不猜测。"""
    results: list[PatternResult] = []

    if q.limit_up is None or q.pre_close is None:
        results.append(PatternResult("first_board", "近 1 个月首板涨停", "unavailable", "缺少涨停价"))
        results.append(PatternResult("one_word", "连续缩量一字", "unavailable", "缺少涨停价"))
    else:
        is_limit = abs(q.close - q.limit_up) < 0.005
        prev_limit = (
            prev is not None
            and prev.limit_up is not None
            and abs(prev.close - prev.limit_up) < 0.005
        )
        results.append(
            PatternResult(
                "first_board", "近期首板涨停", "pass" if (is_limit and not prev_limit) else "fail",
                "今日涨停且前一交易日未涨停" if (is_limit and not prev_limit) else "非首板",
            )
        )
        one_word = is_limit and q.open is not None and q.low is not None and abs(q.open - q.close) < 0.005 and abs(q.low - q.close) < 0.005
        results.append(
            PatternResult(
                "one_word", "连续缩量一字", "pass" if one_word else "fail",
                "一字封板且无换手" if one_word else "存在换手",
            )
        )

    if q.turnover_rate is None:
        results.append(PatternResult("healthy_turnover", "换手率 15%-30%", "unavailable", "换手率缺失"))
    else:
        ok = 15 <= q.turnover_rate <= 30
        results.append(
            PatternResult(
                "healthy_turnover", "换手率 15%-30%", "pass" if ok else "fail",
                f"当前换手 {q.turnover_rate:g}%",
            )
        )

    # 免费源不提供概念板块成分与连板名单，梯队只能人工确认
    results.append(PatternResult("ladder", "板块跟风梯队", "unavailable", "缺少板块成分数据"))
    return results


def pattern_as_gate_result(p: PatternResult) -> GateResult:
    """把形态结果落库时复用 screening_results 的结构。"""
    return GateResult(
        gate=p.key,
        label=p.label,
        status=p.status,
        actual_value=p.evidence,
        threshold="见 PRD §3.2 形态判据",
        reason=p.evidence or "",
    )
