"""sqlite 连接、表结构与种子数据。

设计取舍：表结构变更不引迁移框架，用 PRAGMA user_version 做版本号，
每个版本的 DDL 追加在 MIGRATIONS 里，启动时顺序执行到最新版本。
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from src.core import config
from src.core.logging import get_logger
from src.core.security import hash_password

logger = get_logger(__name__)

# sqlite 同一时刻只允许一个写者；用进程内锁把写操作串行化，避免 database is locked 抖动。
_WRITE_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """写事务。持锁 + 提交/回滚成对出现，调用方只管写。"""
    with _WRITE_LOCK:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE IF NOT EXISTS users (
      id            INTEGER PRIMARY KEY CHECK (id = 1),
      password_hash TEXT    NOT NULL,
      updated_at    TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
      key         TEXT PRIMARY KEY,
      value_json  TEXT NOT NULL,
      updated_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS data_sources (
      name            TEXT PRIMARY KEY,
      enabled         INTEGER NOT NULL DEFAULT 1,
      priority        INTEGER NOT NULL,
      last_success_at TEXT,
      last_error      TEXT,
      updated_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS source_health_logs (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      source      TEXT    NOT NULL,
      checked_at  TEXT    NOT NULL,
      ok          INTEGER NOT NULL,
      latency_ms  INTEGER,
      error       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_health_source_time ON source_health_logs(source, checked_at);

    CREATE TABLE IF NOT EXISTS stocks (
      code       TEXT PRIMARY KEY,
      name       TEXT NOT NULL,
      market     TEXT NOT NULL,
      list_date  TEXT,
      is_st      INTEGER NOT NULL DEFAULT 0,
      status     TEXT NOT NULL DEFAULT 'normal',
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS daily_quotes (
      code          TEXT NOT NULL REFERENCES stocks(code),
      trade_date    TEXT NOT NULL,
      open REAL, high REAL, low REAL, close REAL, pre_close REAL,
      pct_chg       REAL,
      volume        INTEGER,
      amount        REAL,
      turnover_rate REAL,
      total_mv      REAL,
      float_mv      REAL,
      limit_up      REAL,
      source        TEXT NOT NULL,
      fetched_at    TEXT NOT NULL,
      PRIMARY KEY (code, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_quotes_date ON daily_quotes(trade_date);

    CREATE TABLE IF NOT EXISTS themes (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      name       TEXT    NOT NULL UNIQUE,
      branch     TEXT    NOT NULL,
      enabled    INTEGER NOT NULL DEFAULT 1,
      sort_order INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS stock_themes (
      code     TEXT    NOT NULL,
      theme_id INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
      source   TEXT    NOT NULL,
      PRIMARY KEY (code, theme_id)
    );

    CREATE TABLE IF NOT EXISTS screening_runs (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at   TEXT NOT NULL,
      finished_at  TEXT,
      status       TEXT NOT NULL,
      params_json  TEXT NOT NULL,
      stats_json   TEXT
    );

    CREATE TABLE IF NOT EXISTS screening_results (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id       INTEGER NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
      code         TEXT    NOT NULL,
      stage        TEXT    NOT NULL,
      gate         TEXT    NOT NULL,
      passed       INTEGER NOT NULL,
      actual_value TEXT,
      threshold    TEXT,
      reason       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_results_run ON screening_results(run_id);
    CREATE INDEX IF NOT EXISTS idx_results_code ON screening_results(code, run_id);

    CREATE TABLE IF NOT EXISTS scores (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      code          TEXT    NOT NULL,
      run_id        INTEGER NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
      total_score   REAL    NOT NULL,
      details_json  TEXT    NOT NULL,
      calculated_at TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_scores_run ON scores(run_id);

    CREATE TABLE IF NOT EXISTS watch_pool (
      id               INTEGER PRIMARY KEY AUTOINCREMENT,
      code             TEXT    NOT NULL UNIQUE REFERENCES stocks(code),
      status           TEXT    NOT NULL DEFAULT 'keep',
      theme_side       TEXT,
      first_board_date TEXT,
      tier             TEXT,
      added_at         TEXT    NOT NULL,
      updated_at       TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_pool_status ON watch_pool(status);

    CREATE TABLE IF NOT EXISTS watch_pool_history (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      pool_id     INTEGER NOT NULL REFERENCES watch_pool(id) ON DELETE CASCADE,
      from_status TEXT,
      to_status   TEXT NOT NULL,
      reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),
      created_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_history_pool ON watch_pool_history(pool_id, created_at);

    CREATE TABLE IF NOT EXISTS manual_metrics (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      code        TEXT NOT NULL,
      trade_date  TEXT NOT NULL,
      metric      TEXT NOT NULL,
      value       REAL,
      entered_at  TEXT NOT NULL,
      UNIQUE (code, trade_date, metric)
    );

    CREATE TABLE IF NOT EXISTS job_runs (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      job         TEXT NOT NULL,
      started_at  TEXT NOT NULL,
      finished_at TEXT,
      status      TEXT NOT NULL,
      error       TEXT
    );
    """,
]

DEFAULT_SETTINGS: dict[str, object] = {
    "thresholds": {
        "min_total_mv": 20.0,
        "max_total_mv": 45.0,
        "min_price": 3.0,
        "max_price": 10.0,
        "max_float_mv": 40.0,
        "enable_float_mv": False,
    },
    "scoring": {
        "base": 60.0,
        "items": [
            {"key": "multi_theme", "label": "多概念叠加", "type": "add", "delta": 8, "weight": 1.0, "source": "auto"},
            {"key": "leader", "label": "板块梯队龙头", "type": "add", "delta": 6, "weight": 1.0, "source": "auto"},
            {"key": "healthy_turnover", "label": "健康换手 15%-30%", "type": "add", "delta": 5, "weight": 1.0, "source": "auto"},
            {"key": "sub_new", "label": "次新（上市 2-5 年）", "type": "add", "delta": 4, "weight": 1.0, "source": "auto"},
            {"key": "name_recog", "label": "名字辨识度高", "type": "add", "delta": 3, "weight": 1.0, "source": "manual"},
            {"key": "event_catalyst", "label": "年末事件催化", "type": "add", "delta": 5, "weight": 1.0, "source": "manual"},
            {"key": "one_word", "label": "连续缩量一字", "type": "minus", "delta": 10, "weight": 1.0, "source": "auto"},
            {"key": "near_200", "label": "滚动30日涨幅接近200%", "type": "minus", "delta": 8, "weight": 1.0, "source": "auto"},
            {"key": "no_ladder", "label": "板块无跟风梯队", "type": "minus", "delta": 6, "weight": 1.0, "source": "auto"},
        ],
    },
    "pool": {
        "capacity": 30,
        "stages": [
            {"name": "建池期", "start": "10-20", "end": "10-31", "target": 30},
            {"name": "精简期", "start": "11-01", "end": "11-15", "target": 12},
            {"name": "收敛期", "start": "11-16", "end": "11-30", "target": 5},
            {"name": "锁定期", "start": "12-01", "end": "01-10", "target": 2},
        ],
    },
    "schedule": {"enabled": True, "refresh_time": config.DAILY_REFRESH_TIME},
}

SEED_THEMES: list[tuple[str, str]] = [
    ("商业航天", "main1"), ("低空经济", "main1"), ("卫星组网", "main1"),
    ("AI算力", "main1"), ("液冷", "main1"), ("国产算力硬件", "main1"),
    ("人形机器人", "main1"), ("智能制造", "main1"), ("工业自动化", "main1"),
    ("自贸港", "main2"), ("区域振兴", "main2"), ("年末消费复苏", "main2"),
    ("文旅", "main2"), ("零售", "main2"), ("国企改革", "main2"),
    ("资产重组", "main2"), ("股权变更", "main2"),
    ("储能", "main3"), ("核电", "main3"), ("军工", "main3"),
    ("新能源拐点", "main3"), ("大宗商品周期反转", "main3"),
]

SEED_SOURCES: list[tuple[str, int, int]] = [
    ("eastmoney", 1, 1),
    ("tencent", 2, 1),
    ("sina", 3, 1),
]


def init_db(db_path: Path | str | None = None) -> None:
    """建表 + 种子数据。可重复执行（幂等）。"""
    conn = connect(db_path)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version in range(current, len(MIGRATIONS)):
            conn.executescript(MIGRATIONS[version])
            conn.execute(f"PRAGMA user_version={version + 1}")
        conn.commit()
        _seed(conn)
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    ts = now_iso()

    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    if row["c"] == 0:
        password = config.INITIAL_PASSWORD or secrets.token_urlsafe(12)
        conn.execute(
            "INSERT INTO users (id, password_hash, updated_at) VALUES (1, ?, ?)",
            (hash_password(password), ts),
        )
        if not config.INITIAL_PASSWORD:
            # 仅在未显式配置时输出一次，提示用户立即修改
            logger.warning("[DEBUG] 首次启动生成随机登录密码：%s（请登录后立即修改）", password)

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), ts),
        )

    for idx, (name, branch) in enumerate(SEED_THEMES):
        conn.execute(
            "INSERT OR IGNORE INTO themes (name, branch, enabled, sort_order) VALUES (?, ?, 1, ?)",
            (name, branch, idx),
        )

    for name, priority, enabled in SEED_SOURCES:
        conn.execute(
            "INSERT OR IGNORE INTO data_sources (name, enabled, priority, updated_at) VALUES (?, ?, ?, ?)",
            (name, enabled, priority, ts),
        )
    conn.commit()
