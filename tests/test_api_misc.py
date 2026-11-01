"""配置、数据源、个股、人工补录、导出、系统状态。"""
from __future__ import annotations

import io

from conftest import make_quote
from src.core import config, db
from src.services import source_health


def test_settings_roundtrip(client):
    current = client.get("/api/v1/settings").json()
    assert set(current) == {"thresholds", "scoring", "pool", "schedule"}
    assert current["thresholds"]["min_total_mv"] == 20.0

    updated = client.put(
        "/api/v1/settings", json={"thresholds": {**current["thresholds"], "min_price": 4.0}}
    ).json()
    assert updated["thresholds"]["min_price"] == 4.0
    assert client.get("/api/v1/settings").json()["thresholds"]["min_price"] == 4.0


def test_settings_reject_unknown_key(client):
    response = client.put("/api/v1/settings", json={"evil": 1})
    assert response.status_code == 422
    assert "evil" in response.json()["error"]["message"]


def test_sources_list_patch_and_test(client, monkeypatch):
    items = client.get("/api/v1/data-sources").json()["items"]
    assert {i["name"] for i in items} == {"eastmoney", "tencent", "sina"}
    assert items[0]["last_health"] is None

    assert client.patch("/api/v1/data-sources/eastmoney", json={"enabled": False}).status_code == 204
    refreshed = client.get("/api/v1/data-sources").json()["items"]
    assert next(i for i in refreshed if i["name"] == "eastmoney")["enabled"] == 0

    assert client.patch("/api/v1/data-sources/nope", json={"enabled": True}).status_code == 404

    class FakeAdapter:
        def test(self):
            return True, 12, None

    monkeypatch.setattr(source_health, "get_adapter", lambda name: FakeAdapter())
    result = client.post("/api/v1/data-sources/eastmoney/test").json()
    assert result == {"source": "eastmoney", "ok": True, "latency_ms": 12, "error": None}

    source = next(
        i for i in client.get("/api/v1/data-sources").json()["items"] if i["name"] == "eastmoney"
    )
    assert source["last_health"]["ok"] == 1
    assert source["last_success_at"] is not None

    assert client.post("/api/v1/data-sources/nope/test").status_code == 404


def test_stock_endpoints(client, seed):
    seed("600001", name="测试股份", quote=make_quote())
    conn = db.connect(config.DB_PATH)
    theme_id = conn.execute("SELECT id FROM themes WHERE name = '商业航天'").fetchone()["id"]
    conn.execute(
        "INSERT INTO stock_themes (code, theme_id, source) VALUES ('600001', ?, 'manual')",
        (theme_id,),
    )
    conn.commit()
    conn.close()

    listing = client.get("/api/v1/stocks?q=测试").json()
    assert listing["total"] == 1
    assert listing["items"][0]["quote"]["close"] == 5.0

    detail = client.get("/api/v1/stocks/600001").json()
    assert detail["stock"]["name"] == "测试股份"
    assert detail["quote"]["total_mv"] == 30.0
    assert detail["themes"][0]["name"] == "商业航天"
    assert detail["watch_pool"] is None

    client.post("/api/v1/watch-pool", json={"code": "600001"})
    assert client.get("/api/v1/stocks/600001").json()["watch_pool"]["status"] == "keep"

    quotes = client.get("/api/v1/stocks/600001/quotes?days=30").json()["items"]
    assert len(quotes) == 1

    assert client.get("/api/v1/stocks/999999").status_code == 404

    gates = client.get("/api/v1/stocks/600001/gates").json()
    assert gates == {"run_id": None, "items": []}
    score = client.get("/api/v1/stocks/600001/score").json()
    assert score == {"run_id": None, "total_score": None, "details": []}


def test_manual_metrics_upsert_and_list(client):
    response = client.put(
        "/api/v1/manual-metrics/600001",
        json={"trade_date": "2026-10-30", "metric": "name_recog", "value": 1},
    )
    assert response.status_code == 204

    items = client.get("/api/v1/manual-metrics/600001").json()["items"]
    assert items[0] == {
        "id": items[0]["id"], "code": "600001", "trade_date": "2026-10-30",
        "metric": "name_recog", "value": 1.0, "entered_at": items[0]["entered_at"],
    }

    invalid = client.put(
        "/api/v1/manual-metrics/600001",
        json={"trade_date": "2026-10-30", "metric": "unknown", "value": 1},
    )
    assert invalid.status_code == 422
    assert "不支持的指标" in invalid.json()["error"]["message"]


def test_manual_metrics_csv_import(client):
    csv_content = (
        "code,trade_date,metric,value\n"
        "600001,2026-10-30,name_recog,1\n"
        "600002,2026-10-30,event_catalyst,1\n"
        "600003,2026-10-30,unknown_metric,1\n"
        "600004,2026-10-30,pct_30d,abc\n"
    )
    response = client.post(
        "/api/v1/manual-metrics/import",
        files={"file": ("metrics.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 2, "skipped": 2}


def test_manual_metrics_import_rejects_bad_header_and_encoding(client):
    bad_header = client.post(
        "/api/v1/manual-metrics/import",
        files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert bad_header.status_code == 422
    assert "表头" in bad_header.json()["error"]["message"]

    bad_encoding = client.post(
        "/api/v1/manual-metrics/import",
        files={"file": ("bad.csv", b"\xff\xfe\x00", "text/csv")},
    )
    assert bad_encoding.status_code == 422
    assert "UTF-8" in bad_encoding.json()["error"]["message"]


def test_watch_pool_export(client, seed):
    seed("600001", name="测试股份", quote=make_quote())
    client.post("/api/v1/watch-pool", json={"code": "600001"})
    response = client.get("/api/v1/export/watch-pool.csv")
    assert response.status_code == 200
    assert response.text.startswith("﻿")
    assert "代码,名称" in response.text
    assert "600001" in response.text
    assert "测试股份" in response.text


def test_system_status(client, seed):
    seed("600001")
    client.post("/api/v1/watch-pool", json={"code": "600001"})
    status = client.get("/api/v1/system/status").json()
    assert status["sources"]["total"] == 3
    assert status["sources"]["enabled"] == 3
    assert status["pool"]["active"] == 1
    assert status["last_run"] is None
    assert status["last_job"] is None
