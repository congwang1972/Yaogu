"""人工补录：单条写入与 CSV 导入。"""
from __future__ import annotations

import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.deps import get_db, require_login
from src.core import db
from src.repositories import manual_metrics as manual_repo

router = APIRouter(prefix="/manual-metrics", tags=["manual_metrics"])


class MetricRequest(BaseModel):
    trade_date: str
    metric: str
    value: float | None = None


@router.get("/{code}")
def list_metrics(
    code: str,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    return {"items": [dict(r) for r in manual_repo.list_for_code(conn, code)]}


@router.put("/{code}", status_code=204)
def upsert_metric(
    code: str,
    body: MetricRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> None:
    if body.metric not in manual_repo.VALID_METRICS:
        raise HTTPException(status_code=422, detail=f"不支持的指标：{body.metric}")
    with db.transaction(conn):
        manual_repo.upsert(conn, code, body.trade_date, body.metric, body.value)


@router.post("/import")
def import_csv(
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_login),
) -> dict:
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件需为 UTF-8 编码的 CSV")

    reader = csv.DictReader(io.StringIO(text))
    required = {"code", "trade_date", "metric", "value"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=422, detail="CSV 表头需包含 code,trade_date,metric,value")

    imported, skipped = 0, 0
    with db.transaction(conn):
        for row in reader:
            metric = (row.get("metric") or "").strip()
            if metric not in manual_repo.VALID_METRICS or not row.get("code"):
                skipped += 1
                continue
            try:
                value = float(row["value"]) if row.get("value") not in (None, "") else None
            except ValueError:
                skipped += 1
                continue
            manual_repo.upsert(conn, row["code"].strip(), row["trade_date"].strip(), metric, value)
            imported += 1
    return {"imported": imported, "skipped": skipped}
