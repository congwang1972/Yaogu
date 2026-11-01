"""认证：单用户密码登录、登出、改密。"""
from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.deps import get_db, require_login
from src.core import config, db, security
from src.schemas.common import ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=204)
def login(body: LoginRequest, response: Response, conn: sqlite3.Connection = Depends(get_db)) -> None:
    locked_until = security.login_locked_until()
    if locked_until:
        remaining = max(1, int(locked_until - time.time()))
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {remaining} 秒后重试")

    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    if user is None:
        raise HTTPException(status_code=500, detail="用户未初始化")

    if not security.verify_password(body.password, user["password_hash"]):
        security.register_login_failure()
        locked_now = security.login_locked_until()
        if locked_now:
            raise HTTPException(status_code=429, detail="尝试次数过多，请稍后重试")
        raise HTTPException(status_code=401, detail="密码错误")

    security.clear_login_failures()
    token = security.create_session(user["password_hash"])
    response.set_cookie(
        config.SESSION_COOKIE,
        token,
        max_age=config.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(config.SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: sqlite3.Row = Depends(require_login)) -> dict:
    return {"logged_in": True}


@router.post("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> None:
    if not security.verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码错误")
    new_hash = security.hash_password(body.new_password)
    with db.transaction(conn):
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = 1",
            (new_hash, db.now_iso()),
        )
    # 旧会话因密码指纹变化自动失效，这里顺手清掉当前 Cookie
    response.delete_cookie(config.SESSION_COOKIE, path="/")
