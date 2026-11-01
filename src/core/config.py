"""运行期配置。

所有可变项来自环境变量，代码里不出现凭据，也不写死部署路径。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "yaogu.db"))

# 会话签名密钥。生产必须由环境变量注入，否则进程重启后所有会话失效（这比用默认密钥安全）。
APP_SECRET = os.getenv("APP_SECRET", "")
INITIAL_PASSWORD = os.getenv("INITIAL_PASSWORD", "")

SESSION_COOKIE = "yaogu_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600
# 生产走 HTTPS 时置 1；本地 HTTP 调试必须为 0，否则浏览器不会回传 Cookie
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCK_SECONDS = int(os.getenv("LOGIN_LOCK_SECONDS", "300"))

HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "2"))
HTTP_CONCURRENCY = int(os.getenv("HTTP_CONCURRENCY", "3"))

# 收盘后刷新时间，格式 HH:MM
DAILY_REFRESH_TIME = os.getenv("DAILY_REFRESH_TIME", "15:30")
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1") == "1"

# 免费源返回条目数低于该阈值视为失败，防止“空数组也算成功”导致整池被清空
MIN_QUOTE_COUNT = int(os.getenv("MIN_QUOTE_COUNT", "1000"))
