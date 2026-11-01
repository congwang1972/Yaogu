"""观察池状态机。

所有状态变更都走这里：同一事务里改 watch_pool 并追加 watch_pool_history，
理由由数据库 CHECK 兜底。移出观察池是「软移出」（置为 drop），不物理删除，
否则历史留痕会随级联删除一起消失，违背 AC-05。
"""
from __future__ import annotations

import sqlite3
from datetime import date

from src.core.db import transaction
from src.repositories import watch_pool as pool_repo
from src.repositories import settings as settings_repo

VALID_STATUSES = ("keep", "watch", "drop")
STATUS_LABELS = {"keep": "保留", "watch": "观察", "drop": "淘汰"}


class PoolError(Exception):
    """观察池业务异常，API 层统一转成 4xx。"""


class PoolFull(PoolError):
    pass


class AlreadyInPool(PoolError):
    pass


class PoolNotFound(PoolError):
    pass


class InvalidStatusChange(PoolError):
    pass


def add(
    conn: sqlite3.Connection,
    code: str,
    theme_side: str | None = None,
    first_board_date: str | None = None,
    tier: str | None = None,
) -> int:
    existing = pool_repo.get_by_code(conn, code)
    if existing:
        raise AlreadyInPool(f"{code} 已在观察池（状态：{STATUS_LABELS.get(existing['status'], existing['status'])}）")

    capacity = int(_pool_cfg(conn).get("capacity", 30))
    if pool_repo.count_active(conn) >= capacity:
        raise PoolFull(f"观察池已满（{capacity} 只），请先精简")

    with transaction(conn):
        pool_id = pool_repo.insert(conn, code, theme_side, first_board_date, tier)
        pool_repo.add_history(conn, pool_id, None, "keep", "加入观察池")
    return pool_id


def change_status(conn: sqlite3.Connection, pool_id: int, status: str, reason: str) -> sqlite3.Row:
    if status not in VALID_STATUSES:
        raise PoolError(f"非法状态：{status}")
    if not reason or not reason.strip():
        raise PoolError("必须填写变更理由")

    row = pool_repo.get_by_id(conn, pool_id)
    if row is None:
        raise PoolNotFound(f"观察池记录不存在：{pool_id}")
    if row["status"] == status:
        raise InvalidStatusChange(f"状态已经是「{STATUS_LABELS[status]}」，无需变更")

    with transaction(conn):
        pool_repo.update_status(conn, pool_id, status)
        pool_repo.add_history(conn, pool_id, row["status"], status, reason)

    updated = pool_repo.get_by_id(conn, pool_id)
    assert updated is not None
    return updated


def remove(conn: sqlite3.Connection, pool_id: int, reason: str) -> sqlite3.Row:
    """软移出：置为 drop 并留痕，保证历史不丢。"""
    return change_status(conn, pool_id, "drop", reason or "移出观察池")


def stats(conn: sqlite3.Connection, today: date | None = None) -> dict:
    cfg = _pool_cfg(conn)
    stage = current_stage(cfg.get("stages", []), today or date.today())
    counts = pool_repo.status_counts(conn)
    active = counts["keep"] + counts["watch"]
    target = int(stage["target"]) if stage else int(cfg.get("capacity", 30))
    return {
        "capacity": int(cfg.get("capacity", 30)),
        "active": active,
        "counts": counts,
        "stage": stage,
        "target": target,
        "gap": active - target,
    }


def _pool_cfg(conn: sqlite3.Connection) -> dict:
    return settings_repo.get_key(conn, "pool", {}) or {}


def current_stage(stages: list[dict], today: date) -> dict | None:
    """按 MM-DD 区间判断所处阶段；支持跨年（如 12-01 → 01-10）。"""
    if not stages:
        return None
    now = today.strftime("%m-%d")
    for stage in stages:
        start, end = stage.get("start", ""), stage.get("end", "")
        if not start or not end:
            continue
        if start <= end:
            if start <= now <= end:
                return stage
        elif now >= start or now <= end:  # 跨年
            return stage
    return None
