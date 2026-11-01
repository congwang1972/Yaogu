"""测试夹具：每个用例独立的临时 sqlite 库 + 已登录的 TestClient。"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.core import config, db, security
from src.models.domain import Quote
from src.repositories import quotes as quote_repo

TEST_PASSWORD = "test-password-123"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "INITIAL_PASSWORD", TEST_PASSWORD)
    monkeypatch.setattr(config, "SCHEDULER_ENABLED", False)
    # 测试数据集远小于真实全市场，避免 MIN_QUOTE_COUNT 把有效结果判成失败
    monkeypatch.setattr(config, "MIN_QUOTE_COUNT", 1)
    security.set_session_secret("unit-test-secret")
    security.clear_login_failures()
    db.init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    connection = db.connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def client(db_path):
    from src.main import app

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        assert response.status_code == 204, response.text
        yield test_client


@pytest.fixture
def anon_client(db_path):
    from src.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed(db_path):
    """插入股票与可选行情，返回（构造后的）Quote。"""

    def _seed(
        code: str,
        name: str = "测试股份",
        is_st: int = 0,
        status: str = "normal",
        quote: Quote | None = None,
    ) -> Quote:
        connection = db.connect(db_path)
        try:
            with db.transaction(connection):
                connection.execute(
                    """
                    INSERT INTO stocks (code, name, market, list_date, is_st, status, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                      name = excluded.name, is_st = excluded.is_st, status = excluded.status,
                      updated_at = excluded.updated_at
                    """,
                    (
                        code,
                        name,
                        "SH" if code.startswith("6") else "SZ",
                        is_st,
                        status,
                        db.now_iso(),
                    ),
                )
                if quote is not None:
                    quote_repo.upsert_quotes(connection, [quote])
        finally:
            connection.close()
        return quote or make_quote(code, name=name)

    return _seed


def make_quote(
    code: str = "600001",
    *,
    name: str = "测试股份",
    trade_date: str = "2026-10-30",
    close: float = 5.0,
    pre_close: float | None = 4.9,
    open_: float | None = 5.0,
    high: float | None = 5.2,
    low: float | None = 4.8,
    pct_chg: float | None = 2.04,
    turnover_rate: float | None = 20.0,
    total_mv: float | None = 30.0,
    float_mv: float | None = 25.0,
    limit_up: float | None = 5.39,
    status: str = "normal",
    source: str = "test",
) -> Quote:
    return Quote(
        code=code,
        name=name,
        trade_date=trade_date,
        close=close,
        pre_close=pre_close,
        open=open_,
        high=high,
        low=low,
        pct_chg=pct_chg,
        turnover_rate=turnover_rate,
        total_mv=total_mv,
        float_mv=float_mv,
        limit_up=limit_up,
        status=status,
        source=source,
        fetched_at=db.now_iso(),
    )


def enable_only_source(conn: sqlite3.Connection, name: str = "eastmoney") -> None:
    conn.execute("UPDATE data_sources SET enabled = 0")
    conn.execute("UPDATE data_sources SET enabled = 1 WHERE name = ?", (name,))
    conn.commit()
