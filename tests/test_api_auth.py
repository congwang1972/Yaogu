"""认证与通用错误处理。"""
from __future__ import annotations

from conftest import TEST_PASSWORD


def test_health_is_public(anon_client):
    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_route_requires_login(anon_client):
    response = anon_client.get("/api/v1/system/status")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HTTP_401"


def test_unknown_route_uses_unified_error(anon_client):
    response = anon_client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_login_validation_error(anon_client):
    response = anon_client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_wrong_password(anon_client):
    response = anon_client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "密码错误"


def test_login_locks_after_too_many_failures(anon_client):
    statuses = [
        anon_client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code
        for _ in range(5)
    ]
    assert statuses[:4] == [401, 401, 401, 401]
    assert statuses[4] == 429
    assert "尝试次数过多" in anon_client.post(
        "/api/v1/auth/login", json={"password": TEST_PASSWORD}
    ).json()["error"]["message"]


def test_me_and_logout(client):
    assert client.get("/api/v1/auth/me").json() == {"logged_in": True}
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_change_password_requires_old_password(client):
    response = client.post(
        "/api/v1/auth/password",
        json={"old_password": "nope", "new_password": "new-password-1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "原密码错误"


def test_change_password_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/password",
        json={"old_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


def test_change_password_invalidates_session(client):
    response = client.post(
        "/api/v1/auth/password",
        json={"old_password": TEST_PASSWORD, "new_password": "new-password-1"},
    )
    assert response.status_code == 204

    # 密码指纹变化后旧 Cookie 立即失效
    assert client.get("/api/v1/auth/me").status_code == 401

    relogin = client.post("/api/v1/auth/login", json={"password": "new-password-1"})
    assert relogin.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200
