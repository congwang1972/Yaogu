"""评分：可用性、加减分、不可得项不计分。"""
from __future__ import annotations

from src.core.db import DEFAULT_SETTINGS
from src.models.domain import Quote
from src.services import gates, scoring_service

SCORING = DEFAULT_SETTINGS["scoring"]  # type: ignore[index]


def quote(**kwargs) -> Quote:
    base = dict(
        code="600001",
        name="测试股份",
        trade_date="2026-10-30",
        close=5.39,
        pre_close=4.9,
        open=5.39,
        low=5.39,
        turnover_rate=20.0,
        total_mv=30.0,
        limit_up=5.39,
    )
    base.update(kwargs)
    return Quote(**base)


def patterns(q: Quote, prev: Quote | None = None) -> dict:
    return {p.key: p for p in gates.detect_patterns(q, prev)}


def test_full_score_adds_and_minus():
    q = quote()
    score = scoring_service.compute_score(
        q.code,
        q,
        ["商业航天", "低空经济"],
        patterns(q),
        {"name_recog": 1, "event_catalyst": 1, "pct_30d": 160},
        SCORING,
        tier="leader",
    )
    # 60 基准 +8 多题材 +6 龙头 +5 换手 +3 辨识度 +5 催化 −10 一字 −8 近 200% = 69
    assert score.total == 69
    assert len(score.details) == len(SCORING["items"])  # type: ignore[index]
    assert all(d.available or d.points == 0 for d in score.details)


def test_unavailable_items_never_change_score():
    q = quote(limit_up=None, pre_close=None, turnover_rate=None)
    score = scoring_service.compute_score(
        q.code, q, [], {}, {"ladder": None}, SCORING, tier=None
    )
    # 全部加减分项都不可得或未满足，只剩基准分
    assert score.total == 60
    unavailable = {d.key for d in score.details if not d.available}
    assert {"leader", "healthy_turnover", "sub_new", "name_recog", "event_catalyst", "one_word", "near_200", "no_ladder"} <= unavailable


def test_multi_theme_requires_two():
    q = quote()
    one = scoring_service.compute_score(q.code, q, ["商业航天"], patterns(q), {}, SCORING)
    two = scoring_service.compute_score(q.code, q, ["商业航天", "低空经济"], patterns(q), {}, SCORING)
    assert two.total - one.total == 8


def test_tier_follower_does_not_add_points():
    q = quote()
    leader = scoring_service.compute_score(q.code, q, [], patterns(q), {}, SCORING, tier="leader")
    follower = scoring_service.compute_score(q.code, q, [], patterns(q), {}, SCORING, tier="follower")
    assert leader.total - follower.total == 6


def test_manual_flags_only_score_when_met():
    q = quote()
    base = scoring_service.compute_score(q.code, q, [], patterns(q), {"name_recog": 0}, SCORING)
    met = scoring_service.compute_score(q.code, q, [], patterns(q), {"name_recog": 1}, SCORING)
    assert met.total - base.total == 3


def test_near_200_threshold():
    q = quote()
    below = scoring_service.compute_score(q.code, q, [], patterns(q), {"pct_30d": 149}, SCORING)
    above = scoring_service.compute_score(q.code, q, [], patterns(q), {"pct_30d": 150}, SCORING)
    assert below.total - above.total == 8  # 高于 150% 才扣分，below 反而更高


def test_no_ladder_penalty_when_pattern_is_fail():
    q = quote()
    pat = patterns(q)
    # ladder 免费源不可得，构造一个 fail 覆盖减分分支
    pat["ladder"].status = "fail"
    pat["ladder"].evidence = "有跟风"
    score = scoring_service.compute_score(q.code, q, [], pat, {}, SCORING)
    detail = next(d for d in score.details if d.key == "no_ladder")
    assert detail.available is True
    assert detail.points == 6


def test_unknown_item_is_unavailable():
    cfg = {"base": 50, "items": [{"key": "mystery", "label": "未知", "type": "add", "delta": 9}]}
    score = scoring_service.compute_score("600001", quote(), [], {}, {}, cfg)
    assert score.total == 50
    assert score.details[0].available is False


def test_custom_weight_applies():
    cfg = {
        "base": 0,
        "items": [
            {"key": "multi_theme", "label": "多题材", "type": "add", "delta": 10, "weight": 0.5},
        ],
    }
    score = scoring_service.compute_score("600001", quote(), ["a", "b"], {}, {}, cfg)
    assert score.total == 5
