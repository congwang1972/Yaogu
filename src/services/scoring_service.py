"""评分：规则加减分。

每个评分项都会落一条明细，包含：是否可得（available）、是否满足（met）、
依据（evidence）、数据来源（auto/manual）。不可得的项不计分，界面显示“待确认”，
这样分数不会因为数据缺失被悄悄抬高或压低。
"""
from __future__ import annotations

from src.models.domain import PatternResult, Quote, ScoreDetail, ScoreResult

PatternMap = dict[str, PatternResult]


def _pattern(patterns: PatternMap, key: str) -> PatternResult | None:
    return patterns.get(key)


def compute_score(
    code: str,
    quote: Quote,
    themes: list[str],
    patterns: PatternMap,
    manual: dict[str, float],
    scoring_cfg: dict,
    tier: str | None = None,
) -> ScoreResult:
    base = float(scoring_cfg.get("base", 60.0))
    details: list[ScoreDetail] = []

    for item in scoring_cfg.get("items", []):
        key = item["key"]
        available, met, evidence = _evaluate_item(key, quote, themes, patterns, manual, tier)
        details.append(
            ScoreDetail(
                key=key,
                label=item["label"],
                type=item["type"],
                delta=float(item["delta"]),
                weight=float(item.get("weight", 1.0)),
                source=item.get("source", "auto"),
                available=available,
                met=met,
                evidence=evidence,
            )
        )

    total = base
    for d in details:
        total += d.points if d.type == "add" else -d.points
    return ScoreResult(code=code, total=round(total, 2), details=details)


def _evaluate_item(
    key: str,
    quote: Quote,
    themes: list[str],
    patterns: PatternMap,
    manual: dict[str, float],
    tier: str | None,
) -> tuple[bool, bool, str | None]:
    if key == "multi_theme":
        n = len(themes)
        return True, n >= 2, f"命中 {n} 个题材" + (f"：{'、'.join(themes)}" if themes else "")

    if key == "leader":
        if tier is None:
            return False, False, "梯队地位未录入"
        return True, tier == "leader", f"梯队地位：{tier}"

    if key == "healthy_turnover":
        if quote.turnover_rate is None:
            return False, False, "换手率数据缺失"
        t = quote.turnover_rate
        return True, 15 <= t <= 30, f"当前换手 {t:g}%"

    if key == "sub_new":
        # 免费快照接口不返回上市日期，一期不做推断
        return False, False, "缺少上市日期"

    if key == "name_recog":
        if "name_recog" not in manual:
            return False, False, "未人工标记"
        return True, manual["name_recog"] >= 1, "已人工标记辨识度高"

    if key == "event_catalyst":
        if "event_catalyst" not in manual:
            return False, False, "未人工标记"
        return True, manual["event_catalyst"] >= 1, "已人工标记年末催化"

    if key == "one_word":
        p = _pattern(patterns, "one_word")
        if p is None or p.status == "unavailable":
            return False, False, p.evidence if p else "数据不可得"
        return True, p.status == "pass", p.evidence

    if key == "near_200":
        if "pct_30d" not in manual:
            return False, False, "未补录滚动 30 日涨幅"
        v = manual["pct_30d"]
        return True, v >= 150, f"滚动 30 日涨幅 {v:g}%"

    if key == "no_ladder":
        p = _pattern(patterns, "ladder")
        if p is None or p.status == "unavailable":
            return False, False, "板块梯队数据不可得，待人工确认"
        return True, p.status == "fail", p.evidence

    return False, False, "未知评分项"
