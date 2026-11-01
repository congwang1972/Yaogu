"""CSV 导出。带 UTF-8 BOM，Excel 直接打开不乱码。"""
from __future__ import annotations

import csv
import io
import sqlite3

from src.repositories import screening as screening_repo
from src.repositories import watch_pool as pool_repo

BOM = "﻿"


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return BOM + buf.getvalue()


def watch_pool_csv(conn: sqlite3.Connection) -> str:
    header = ["代码", "名称", "总市值(亿)", "现价", "涨跌幅(%)", "题材方向",
              "首板日期", "梯队地位", "评分", "状态", "加入时间", "更新时间"]
    rows = [
        [r["code"], r["name"], r["total_mv"], r["close"], r["pct_chg"],
         r["theme_side"], r["first_board_date"], r["tier"], r["total_score"],
         r["status"], r["added_at"], r["updated_at"]]
        for r in pool_repo.list_pool(conn)
    ]
    return _csv(header, rows)


def screening_csv(conn: sqlite3.Connection, run_id: int) -> str:
    header = ["代码", "名称", "现价", "涨跌幅(%)", "总市值(亿)", "换手率(%)", "题材", "评分", "数据日期"]
    candidates = screening_repo.list_candidates(conn, run_id, page=1, size=100000)
    rows = [
        [r["code"], r["name"], r["close"], r["pct_chg"], r["total_mv"],
         r["turnover_rate"], r["themes"], r["total_score"], r["trade_date"]]
        for r in candidates
    ]
    return _csv(header, rows)
