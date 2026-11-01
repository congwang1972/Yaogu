"""通用响应结构。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class OkResponse(BaseModel):
    ok: bool = True


def page_response(items: list, total: int, page: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page, "size": size}


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)
