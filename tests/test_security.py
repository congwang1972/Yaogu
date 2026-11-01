"""密码哈希、会话签名、登录锁定。"""
from __future__ import annotations

import time

from src.core import config, security


def test_hash_and_verify_password():
    stored = security.hash_password("s3cret-pass")
    assert stored.startswith("pbkdf2$")
    assert security.verify_password("s3cret-pass", stored) is True
    assert security.verify_password("wrong", stored) is False


def test_verify_malformed_hash_returns_false():
    assert security.verify_password("x", "not-a-hash") is False
    assert security.verify_password("x", "md5$1$aa$bb") is False


def test_session_roundtrip():
    security.set_session_secret("fixed")
    token = security.create_session("hash-value")
    assert security.verify_session(token, "hash-value") is True


def test_session_invalid_after_password_change():
    security.set_session_secret("fixed")
    token = security.create_session("old-hash")
    assert security.verify_session(token, "new-hash") is False


def test_expired_session_rejected():
    security.set_session_secret("fixed")
    token = security.create_session("h", ttl=-1)
    assert security.verify_session(token, "h") is False


def test_tampered_or_garbage_token_rejected():
    security.set_session_secret("fixed")
    token = security.create_session("h")
    assert security.verify_session(token[:-2] + "AA", "h") is False
    assert security.verify_session("!!!not-base64!!!", "h") is False


def test_login_lockout_and_clear(monkeypatch):
    monkeypatch.setattr(config, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(config, "LOGIN_LOCK_SECONDS", 60)
    security.clear_login_failures("demo")
    assert security.login_locked_until("demo") is None
    for _ in range(3):
        security.register_login_failure("demo")
    locked_until = security.login_locked_until("demo")
    assert locked_until is not None
    assert locked_until > time.time()
    security.clear_login_failures("demo")
    assert security.login_locked_until("demo") is None


def test_old_failures_expire(monkeypatch):
    monkeypatch.setattr(config, "LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(config, "LOGIN_LOCK_SECONDS", 1)
    security.clear_login_failures("expired")
    security.register_login_failure("expired")
    time.sleep(1.1)
    security.register_login_failure("expired")
    # 第一次失败已超出窗口被清理，第二次不足以触发锁定
    assert security.login_locked_until("expired") is None
    security.clear_login_failures("expired")
