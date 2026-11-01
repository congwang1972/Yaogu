"""筛选编排：硬门槛 → 题材 → 形态 → 评分全链路。"""
from __future__ import annotations

import json

from conftest import make_quote
from src.models.domain import FetchResult, Quote
from src.services import market_service, screening_service


def add_theme(conn, code: str, theme_name: str = "商业航天") -> None:
    theme_id = conn.execute("SELECT id FROM themes WHERE name = ?", (theme_name,)).fetchone()["id"]
    conn.execute(
        "INSERT OR IGNORE INTO stock_themes (code, theme_id, source) VALUES (?, ?, 'manual')",
        (code, theme_id),
    )
    conn.commit()


def quotes() -> list[Quote]:
    return [
        make_quote("600001"),                                      # 全部门槛通过
        make_quote("600002", close=20.0, limit_up=21.5),           # 价格超上限
        make_quote("600003", name="ST测试"),                        # ST 淘汰
        make_quote("000001", name="深市测试", close=50.0, limit_up=55.0),  # 高价，用于板块过滤
    ]


def test_execute_run_full_pipeline(conn, seed):
    for q in quotes():
        seed(q.code, name=q.name)
    seed("600002", name="高价股")
    add_theme(conn, "600001", "商业航天")
    add_theme(conn, "600001", "低空经济")
    # 前一交易日行情，覆盖「首板」判定的 prev 分支
    conn.execute(
        """INSERT INTO daily_quotes
           (code, trade_date, close, pre_close, limit_up, source, fetched_at)
           VALUES ('600001', '2026-10-29', 4.9, 4.85, 5.34, 'test', ?)""",
        ("2026-10-29T15:00:00",),
    )
    conn.commit()

    run_id = screening_service.create_run(conn, {"scope": "all", "with_theme": True})
    fetch = FetchResult(quotes=quotes(), source="test", count=4, elapsed_ms=12)
    screening_service.execute_run(conn, run_id, prefetched=fetch)

    run = conn.execute("SELECT * FROM screening_runs WHERE id = ?", (run_id,)).fetchone()
    stats = json.loads(run["stats_json"])
    assert run["status"] == "success"
    assert stats["total"] == 4
    assert stats["candidates"] == 1
    assert stats["passed_hard"] == 1
    assert stats["source"] == "test"

    stages = {r["stage"] for r in conn.execute(
        "SELECT stage FROM screening_results WHERE run_id = ?", (run_id,)
    ).fetchall()}
    assert stages == {"hard_gate", "theme", "pattern"}

    theme_row = conn.execute(
        "SELECT * FROM screening_results WHERE run_id = ? AND code='600001' AND gate='theme_match'",
        (run_id,),
    ).fetchone()
    assert theme_row["passed"] == 1
    assert "商业航天" in theme_row["actual_value"]
    assert "低空经济" in theme_row["actual_value"]

    score = conn.execute(
        "SELECT * FROM scores WHERE run_id = ? AND code = '600001'", (run_id,)
    ).fetchone()
    assert score is not None
    assert score["total_score"] > 60
    details = json.loads(score["details_json"])
    assert any(d["key"] == "multi_theme" and d["points"] == 8 for d in details)

    # 失败的门槛也必须留痕，方便解释淘汰原因
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM screening_results WHERE run_id = ? AND code='600002' AND passed=0",
        (run_id,),
    ).fetchone()["c"] >= 1


def test_execute_run_skips_unavailable_gate_instead_of_passing(conn, seed):
    seed("600001")
    q = make_quote("600001", total_mv=None)
    run_id = screening_service.create_run(conn, {"scope": "all"})
    screening_service.execute_run(
        conn, run_id, prefetched=FetchResult([q], "test", 1, 1)
    )
    row = conn.execute(
        "SELECT * FROM screening_results WHERE run_id = ? AND code='600001' AND gate='total_mv'",
        (run_id,),
    ).fetchone()
    assert row["passed"] == 0
    assert "缺失" in row["reason"]
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM scores WHERE run_id = ?", (run_id,)
    ).fetchone()["c"] == 0


def test_board_scope_filters_other_markets(conn, seed):
    seed("600001")
    seed("000001", name="深市测试")
    run_id = screening_service.create_run(conn, {"scope": "board", "board": "SH"})
    screening_service.execute_run(
        conn, run_id, prefetched=FetchResult(quotes(), "test", 4, 3)
    )
    codes = {r["code"] for r in conn.execute(
        "SELECT DISTINCT code FROM screening_results WHERE run_id = ?", (run_id,)
    ).fetchall()}
    assert codes == {"600001", "600002", "600003"}


def test_with_theme_excludes_unmatched_hard_gate_passers(conn, seed):
    seed("600001", name="有题材")
    seed("600002", name="无题材")
    add_theme(conn, "600001")

    both = FetchResult(
        [make_quote("600001", name="有题材"), make_quote("600002", name="无题材")],
        "test", 2, 1,
    )
    themed_run = screening_service.create_run(conn, {"scope": "all", "with_theme": True})
    screening_service.execute_run(conn, themed_run, prefetched=both)
    assert screening_service.screening_repo.candidate_count(conn, themed_run) == 1

    plain_run = screening_service.create_run(conn, {"scope": "all", "with_theme": False})
    screening_service.execute_run(conn, plain_run, prefetched=both)
    assert screening_service.screening_repo.candidate_count(conn, plain_run) == 2


def test_market_unavailable_marks_run_failed(conn, monkeypatch):
    def boom(_conn):
        raise market_service.MarketUnavailable("全部源失败")

    monkeypatch.setattr(market_service, "fetch_market_snapshot", boom)
    run_id = screening_service.create_run(conn, {"scope": "all"})
    screening_service.execute_run(conn, run_id)

    run = conn.execute("SELECT * FROM screening_runs WHERE id = ?", (run_id,)).fetchone()
    assert run["status"] == "failed"
    assert "全部源失败" in json.loads(run["stats_json"])["error"]


def test_unknown_run_raises(conn):
    import pytest

    with pytest.raises(ValueError):
        screening_service.execute_run(conn, 999, prefetched=FetchResult([], "test", 0, 0))


def test_partial_status_when_source_had_failures(conn, seed):
    seed("600001")
    run_id = screening_service.create_run(conn, {"scope": "all"})
    screening_service.execute_run(
        conn,
        run_id,
        prefetched=FetchResult([make_quote()], "tencent", 1, 1, failures=["eastmoney: 超时"]),
    )
    run = conn.execute("SELECT status, stats_json FROM screening_runs WHERE id = ?", (run_id,)).fetchone()
    assert run["status"] == "partial"
    assert json.loads(run["stats_json"])["failures"] == ["eastmoney: 超时"]


def test_stale_snapshot_is_recorded_in_run_stats(conn, seed):
    seed("600001")
    run_id = screening_service.create_run(conn, {"scope": "all"})
    screening_service.execute_run(
        conn,
        run_id,
        prefetched=FetchResult(
            [make_quote()], "cache", 1, 1,
            failures=["tencent: 超时"], stale=True, as_of="2026-10-30",
        ),
    )
    run = conn.execute("SELECT status, stats_json FROM screening_runs WHERE id = ?", (run_id,)).fetchone()
    stats = json.loads(run["stats_json"])
    assert run["status"] == "partial"
    assert stats["stale"] is True
    assert stats["as_of"] == "2026-10-30"
