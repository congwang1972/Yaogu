"""筛选 API：后台批次、候选/落选、导出、个股判定回看。"""
from __future__ import annotations

from conftest import make_quote
from src.models.domain import FetchResult
from src.services import market_service


def fake_fetch(conn=None):
    return FetchResult(
        quotes=[
            make_quote("600001"),
            make_quote("600002", name="ST测试", close=20.0, limit_up=21.5),
        ],
        source="fake",
        count=2,
        elapsed_ms=5,
    )


def prepare(client, seed, monkeypatch, fetch=None):
    seed("600001", name="测试股份")
    seed("600002", name="ST测试", is_st=1)
    theme_id = _theme_id(seed, "商业航天")
    _link_theme(seed, "600001", theme_id)
    monkeypatch.setattr(
        market_service, "fetch_market_snapshot", fetch or (lambda conn: fake_fetch(conn))
    )


def _db(seed):
    # 通过 seed 的闭包拿不到连接，这里直接连 config.DB_PATH
    from src.core import config, db

    return db.connect(config.DB_PATH)


def _theme_id(seed, name: str) -> int:
    conn = _db(seed)
    try:
        return conn.execute("SELECT id FROM themes WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def _link_theme(seed, code: str, theme_id: int) -> None:
    conn = _db(seed)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO stock_themes (code, theme_id, source) VALUES (?, ?, 'manual')",
            (code, theme_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_run_lifecycle_candidates_and_results(client, seed, monkeypatch):
    prepare(client, seed, monkeypatch)

    started = client.post("/api/v1/screening/runs", json={"scope": "all", "with_theme": True})
    assert started.status_code == 202
    run_id = started.json()["run_id"]

    run = client.get(f"/api/v1/screening/runs/{run_id}").json()
    assert run["status"] == "success"
    assert run["stats"]["candidates"] == 1
    assert run["params"]["scope"] == "all"

    candidates = client.get(f"/api/v1/screening/runs/{run_id}/candidates").json()
    assert candidates["total"] == 1
    item = candidates["items"][0]
    assert item["code"] == "600001"
    assert item["themes"] == ["商业航天"]
    assert item["total_score"] > 0

    rejected = client.get(
        f"/api/v1/screening/runs/{run_id}/results?stage=hard_gate&passed=false"
    ).json()
    assert rejected["total"] >= 1
    assert {r["code"] for r in rejected["items"]} == {"600002"}

    listed = client.get("/api/v1/screening/runs?page=1&size=10").json()
    assert listed["total"] == 1


def test_run_export_csv(client, seed, monkeypatch):
    prepare(client, seed, monkeypatch)
    run_id = client.post("/api/v1/screening/runs", json={"scope": "all"}).json()["run_id"]

    response = client.get(f"/api/v1/export/screening/{run_id}.csv")
    assert response.status_code == 200
    assert response.text.startswith("﻿")
    assert "代码,名称" in response.text
    assert "600001" in response.text


def test_stock_gates_and_score_after_run(client, seed, monkeypatch):
    prepare(client, seed, monkeypatch)
    run_id = client.post("/api/v1/screening/runs", json={"scope": "all"}).json()["run_id"]

    gates = client.get("/api/v1/stocks/600001/gates").json()
    assert gates["run_id"] == run_id
    assert {g["gate"] for g in gates["items"]} >= {"total_mv", "price"}

    score = client.get("/api/v1/stocks/600001/score").json()
    assert score["total_score"] is not None
    assert len(score["details"]) == 9
    assert all("points" in d for d in score["details"])


def test_run_validation_and_missing(client):
    assert client.post(
        "/api/v1/screening/runs", json={"scope": "galaxy"}
    ).status_code == 422
    assert client.get("/api/v1/screening/runs/999").status_code == 404


def test_market_failure_marks_run_failed(client, monkeypatch):
    def boom(conn):
        raise market_service.MarketUnavailable("全部数据源不可用")

    monkeypatch.setattr(market_service, "fetch_market_snapshot", boom)
    run_id = client.post("/api/v1/screening/runs", json={"scope": "all"}).json()["run_id"]

    run = client.get(f"/api/v1/screening/runs/{run_id}").json()
    assert run["status"] == "failed"
    assert "全部数据源不可用" in run["stats"]["error"]


def test_background_exception_is_recorded(client, monkeypatch):
    def explode(conn):
        raise RuntimeError("适配器内部错误")

    # execute_run 只有 MarketUnavailable 会吞掉，其他异常冒泡到后台任务兜底
    monkeypatch.setattr(market_service, "fetch_market_snapshot", explode)
    run_id = client.post("/api/v1/screening/runs", json={"scope": "all"}).json()["run_id"]
    run = client.get(f"/api/v1/screening/runs/{run_id}").json()
    assert run["status"] == "failed"
    assert "适配器内部错误" in run["stats"]["error"]
