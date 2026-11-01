"""定时任务：每日收盘后刷新行情并重算评分；每周探测数据源。

交易日判断不维护节假日表：抓回来的 trade_date 不是今天，就说明当天休市。
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core import config, db
from src.core.logging import get_logger
from src.repositories import jobs as job_repo
from src.repositories import quotes as quote_repo
from src.repositories import screening as screening_repo
from src.services import market_service, screening_service, source_health

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def daily_refresh() -> dict:
    conn = db.connect()
    job_id = job_repo.start_job(conn, "daily_refresh")
    try:
        fetch = market_service.fetch_market_snapshot(conn)
        if fetch.stale:
            # 自动任务拿到旧快照时不再自动产出新结论；保留批次给人工判断，
            # 同时在 job_runs 留一条 partial，界面据此显示行情降级。
            message = f"行情源全部失败，回退 {fetch.as_of or '历史'} 快照，未执行自动筛选"
            job_repo.finish_job(conn, job_id, "partial", message)
            conn.commit()
            logger.warning("[DEBUG] daily_refresh 降级 | as_of=%s failures=%s", fetch.as_of, fetch.failures)
            return {"status": "partial", "stale": True, "trade_date": fetch.as_of}

        today = db.today_str()
        latest = quote_repo.latest_trade_date(conn)
        if latest != today:
            job_repo.finish_job(conn, job_id, "skipped")
            conn.commit()
            logger.info("[DEBUG] daily_refresh 跳过：最新交易日 %s != 今天 %s", latest, today)
            return {"status": "skipped", "trade_date": latest}

        conn.commit()
        run_id = screening_service.create_run(conn, {"scope": "all", "with_theme": True})
        screening_service.execute_run(conn, run_id, prefetched=fetch)
        job_repo.finish_job(conn, job_id, "success")
        conn.commit()
        logger.info("[DEBUG] daily_refresh 完成 | run_id=%s quotes=%s", run_id, fetch.count)
        return {"status": "success", "run_id": run_id, "count": fetch.count}
    except Exception as exc:
        logger.exception("[DEBUG] daily_refresh 失败 | error=%s", exc)
        try:
            job_repo.finish_job(conn, job_id, "failed", str(exc))
            conn.commit()
        except Exception:
            logger.exception("[DEBUG] daily_refresh 写入失败状态时再次出错")
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        conn.close()


def weekly_health() -> list[dict]:
    conn = db.connect()
    job_id = job_repo.start_job(conn, "weekly_health")
    try:
        results = source_health.check_all(conn)
        ok = any(r["ok"] for r in results)
        job_repo.finish_job(conn, job_id, "success" if ok else "failed")
        conn.commit()
        return results
    except Exception as exc:
        logger.exception("[DEBUG] weekly_health 失败 | error=%s", exc)
        job_repo.finish_job(conn, job_id, "failed", str(exc))
        conn.commit()
        return [{"ok": False, "error": str(exc)[:300]}]
    finally:
        conn.close()


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    hour, minute = _parse_time(config.DAILY_REFRESH_TIME)
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        daily_refresh,
        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute),
        id="daily_refresh",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        weekly_health,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_health",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("[DEBUG] 定时任务已启动 | daily_refresh=%02d:%02d", hour, minute)
    return scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _parse_time(text: str) -> tuple[int, int]:
    try:
        hour, minute = text.split(":")
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        logger.warning("[DEBUG] 非法刷新时间 %s，回退 15:30", text)
        return 15, 30
