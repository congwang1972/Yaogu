"""观察池状态机：容量、理由必填、软移出、阶段目标。"""
from __future__ import annotations

from datetime import date

import pytest

from src.repositories import settings as settings_repo
from src.services import watch_pool_service as svc


def test_add_writes_history(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001", "main", "2026-10-28", "leader")

    history = conn.execute(
        "SELECT * FROM watch_pool_history WHERE pool_id = ?", (pool_id,)
    ).fetchall()
    assert len(history) == 1
    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == "keep"
    assert history[0]["reason"] == "加入观察池"


def test_duplicate_add_rejected(conn, seed):
    seed("600001")
    svc.add(conn, "600001")
    with pytest.raises(svc.AlreadyInPool):
        svc.add(conn, "600001")


def test_pool_capacity_enforced(conn, seed):
    seed("600001")
    seed("600002")
    settings_repo.set_values(conn, {"pool": {"capacity": 1, "stages": []}})
    conn.commit()
    svc.add(conn, "600001")
    with pytest.raises(svc.PoolFull):
        svc.add(conn, "600002")


def test_change_status_requires_reason(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    with pytest.raises(svc.PoolError):
        svc.change_status(conn, pool_id, "watch", "   ")


def test_change_status_rejects_unknown_status(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    with pytest.raises(svc.PoolError):
        svc.change_status(conn, pool_id, "sold", "卖出")


def test_change_status_unknown_id(conn):
    with pytest.raises(svc.PoolNotFound):
        svc.change_status(conn, 999, "drop", "不存在")


def test_change_status_same_status_rejected(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    with pytest.raises(svc.InvalidStatusChange):
        svc.change_status(conn, pool_id, "keep", "没变化")


def test_change_status_writes_history_atomically(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    row = svc.change_status(conn, pool_id, "drop", "跟风位，无梯队")

    assert row["status"] == "drop"
    history = conn.execute(
        "SELECT * FROM watch_pool_history WHERE pool_id = ? ORDER BY id", (pool_id,)
    ).fetchall()
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        (None, "keep"),
        ("keep", "drop"),
    ]
    assert history[-1]["reason"] == "跟风位，无梯队"


def test_remove_is_soft_drop(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    row = svc.remove(conn, pool_id, "手动剔除")
    assert row["status"] == "drop"
    # 记录仍在，历史可回看
    assert conn.execute("SELECT COUNT(*) AS c FROM watch_pool WHERE id = ?", (pool_id,)).fetchone()["c"] == 1


def test_remove_uses_default_reason_when_empty(conn, seed):
    seed("600001")
    pool_id = svc.add(conn, "600001")
    svc.remove(conn, pool_id, "")
    reason = conn.execute(
        "SELECT reason FROM watch_pool_history WHERE pool_id = ? ORDER BY id DESC LIMIT 1", (pool_id,)
    ).fetchone()["reason"]
    assert reason == "移出观察池"


def test_stats_counts_and_gap(conn, seed):
    seed("600001")
    seed("600002")
    pool_id = svc.add(conn, "600001")
    svc.add(conn, "600002")
    svc.change_status(conn, pool_id, "drop", "淘汰")

    stats = svc.stats(conn, today=date(2026, 10, 25))
    assert stats["active"] == 1
    assert stats["counts"] == {"keep": 1, "watch": 0, "drop": 1}
    assert stats["stage"]["name"] == "建池期"
    assert stats["target"] == 30
    assert stats["gap"] == 1 - 30


@pytest.mark.parametrize(
    ("today", "stage_name"),
    [
        (date(2026, 10, 25), "建池期"),
        (date(2026, 11, 10), "精简期"),
        (date(2026, 11, 20), "收敛期"),
        (date(2026, 12, 20), "锁定期"),
        (date(2027, 1, 5), "锁定期"),   # 跨年区间
        (date(2026, 9, 1), None),
    ],
)
def test_current_stage(today, stage_name, conn):
    stages = settings_repo.get_key(conn, "pool")["stages"]
    stage = svc.current_stage(stages, today)
    assert (stage or {}).get("name") == stage_name


def test_current_stage_empty_and_invalid():
    assert svc.current_stage([], date(2026, 10, 25)) is None
    assert svc.current_stage([{"name": "坏数据", "start": "", "end": ""}], date(2026, 10, 25)) is None
