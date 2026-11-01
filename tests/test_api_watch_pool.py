"""观察池 API：加入、筛选、状态变更必须带理由、软移出。"""
from __future__ import annotations


def add_stock(client, seed, code="600001", name="测试股份"):
    seed(code, name=name)
    return client.post("/api/v1/watch-pool", json={"code": code})


def test_add_requires_six_digit_code(client):
    response = client.post("/api/v1/watch-pool", json={"code": "6000"})
    assert response.status_code == 422


def test_add_list_and_duplicate(client, seed):
    response = add_stock(client, seed)
    assert response.status_code == 201
    pool_id = response.json()["id"]

    listing = client.get("/api/v1/watch-pool").json()["items"]
    assert [item["code"] for item in listing] == ["600001"]
    assert listing[0]["status"] == "keep"

    duplicate = client.post("/api/v1/watch-pool", json={"code": "600001"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ALREADYINPOOL"

    history = client.get(f"/api/v1/watch-pool/{pool_id}/history").json()["items"]
    assert history[0]["reason"] == "加入观察池"


def test_pool_full_returns_conflict(client, seed):
    seed("600001")
    seed("600002")
    client.put("/api/v1/settings", json={"pool": {"capacity": 1, "stages": []}})
    assert client.post("/api/v1/watch-pool", json={"code": "600001"}).status_code == 201
    response = client.post("/api/v1/watch-pool", json={"code": "600002"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POOLFULL"


def test_change_status_with_reason(client, seed):
    pool_id = add_stock(client, seed).json()["id"]
    response = client.patch(
        f"/api/v1/watch-pool/{pool_id}",
        json={"status": "watch", "reason": "缩量，继续观察"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "watch"

    history = client.get(f"/api/v1/watch-pool/{pool_id}/history").json()["items"]
    assert history[0]["reason"] == "缩量，继续观察"


def test_change_status_requires_reason(client, seed):
    pool_id = add_stock(client, seed).json()["id"]

    missing = client.patch(f"/api/v1/watch-pool/{pool_id}", json={"status": "drop"})
    assert missing.status_code == 422

    blank = client.patch(
        f"/api/v1/watch-pool/{pool_id}", json={"status": "drop", "reason": "   "}
    )
    assert blank.status_code == 400


def test_change_status_rejects_same_status(client, seed):
    pool_id = add_stock(client, seed).json()["id"]
    response = client.patch(
        f"/api/v1/watch-pool/{pool_id}", json={"status": "keep", "reason": "无变化"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALIDSTATUSCHANGE"


def test_change_status_unknown_id(client):
    response = client.patch(
        "/api/v1/watch-pool/999", json={"status": "drop", "reason": "不存在"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "POOLNOTFOUND"


def test_remove_is_soft_drop(client, seed):
    pool_id = add_stock(client, seed).json()["id"]
    response = client.request(
        "DELETE", f"/api/v1/watch-pool/{pool_id}", json={"reason": "题材退潮"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "drop"

    # 记录仍在，可继续查看历史
    assert client.get("/api/v1/watch-pool").json()["items"][0]["status"] == "drop"


def test_list_filter(client, seed):
    first = add_stock(client, seed, "600001").json()["id"]
    add_stock(client, seed, "600002", "第二只")
    client.patch(
        f"/api/v1/watch-pool/{first}", json={"status": "drop", "reason": "淘汰"}
    )

    dropped = client.get("/api/v1/watch-pool?status=drop").json()["items"]
    assert [i["code"] for i in dropped] == ["600001"]


def test_stats(client, seed):
    pool_id = add_stock(client, seed).json()["id"]
    client.patch(f"/api/v1/watch-pool/{pool_id}", json={"status": "watch", "reason": "观察"})
    stats = client.get("/api/v1/watch-pool/stats").json()
    assert stats["active"] == 1
    assert stats["counts"]["watch"] == 1
    assert stats["capacity"] == 30
