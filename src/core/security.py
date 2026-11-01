"""密码哈希与会话签名。

只依赖标准库：pbkdf2_hmac 做密码哈希，hmac + base64 做无状态会话签名。
无状态会话的好处是不用再建 sessions 表；代价是改密码后旧会话不会自动失效，
这里通过把密码哈希的前 8 位混入签名来补上这个缺口。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import threading
import time

from src.core import config
from src.core.logging import get_logger

logger = get_logger(__name__)

PBKDF2_ITERATIONS = 390_000

_session_secret: bytes | None = None
_secret_lock = threading.Lock()

# 登录失败计数：单用户场景下按全局计数即可，进程重启后清零可接受
_login_failures: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _secret() -> bytes:
    global _session_secret
    if _session_secret is None:
        with _secret_lock:
            if _session_secret is None:
                if config.APP_SECRET:
                    _session_secret = config.APP_SECRET.encode("utf-8")
                else:
                    # 未配置 APP_SECRET 时退化为进程内随机密钥：重启后会话失效，
                    # 但绝不会出现“所有人都知道密钥”的情况。
                    _session_secret = secrets.token_bytes(32)
                    logger.warning("[DEBUG] 未设置 APP_SECRET，已生成临时密钥，重启后需重新登录")
    return _session_secret


def set_session_secret(secret: str | bytes) -> None:
    """测试用：固定密钥。"""
    global _session_secret
    _session_secret = secret.encode("utf-8") if isinstance(secret, str) else secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        logger.error("[DEBUG] verify_password 解析哈希失败")
        return False


def _fingerprint(password_hash: str) -> str:
    return password_hash[:8]


def create_session(password_hash: str, ttl: int | None = None) -> str:
    ttl = ttl or config.SESSION_TTL_SECONDS
    exp = int(time.time()) + ttl
    payload = f"{exp}.{_fingerprint(password_hash)}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}.{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_session(token: str, password_hash: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        exp_str, fp, sig = raw.split(".")
        expected = hmac.new(
            _secret(), f"{exp_str}.{fp}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        if int(exp_str) < int(time.time()):
            return False
        # 密码修改后旧会话自动失效
        return hmac.compare_digest(fp, _fingerprint(password_hash))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False


def register_login_failure(key: str = "global") -> None:
    with _login_lock:
        _login_failures.setdefault(key, []).append(time.time())


def login_locked_until(key: str = "global") -> float | None:
    """仍在锁定期则返回解锁时间戳，否则返回 None。"""
    with _login_lock:
        stamps = _login_failures.get(key, [])
        cutoff = time.time() - config.LOGIN_LOCK_SECONDS
        recent = [s for s in stamps if s > cutoff]
        _login_failures[key] = recent
        if len(recent) >= config.LOGIN_MAX_ATTEMPTS:
            return recent[-1] + config.LOGIN_LOCK_SECONDS
        return None


def clear_login_failures(key: str = "global") -> None:
    with _login_lock:
        _login_failures.pop(key, None)
