"""Планировщик парсинга (APScheduler 3.x)."""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

import constants
import database
from config import settings
from models import Vacancy
from services import parser_service
from services.exceptions import ParsingAlreadyRunningError

logger = logging.getLogger("jobpulse.scheduler")

MAIN_JOB_ID = "parsing_main"
STARTUP_JOB_ID = "parsing_startup"
RETRY_JOB_ID = "parsing_retry"

_scheduler: AsyncIOScheduler | None = None
_retry_count = 0


def _count_vacancies() -> int:
    with database.SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Vacancy)) or 0


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    scheduler = AsyncIOScheduler(timezone=settings.APP_TIMEZONE)
    if settings.PARSING_SCHEDULE == "daily":
        trigger = CronTrigger(hour=settings.PARSING_DAILY_HOUR, minute=0, timezone=settings.APP_TIMEZONE)
    else:
        trigger = IntervalTrigger(hours=settings.PARSING_INTERVAL_HOURS, timezone=settings.APP_TIMEZONE)
    scheduler.add_job(
        run_parsing_job,
        trigger,
        args=["scheduler"],
        id=MAIN_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    if settings.PARSING_RUN_ON_STARTUP_IF_EMPTY and _count_vacancies() == 0:
        scheduler.add_job(
            run_parsing_job,
            DateTrigger(
                run_date=datetime.now(timezone.utc) + timedelta(seconds=constants.STARTUP_PARSING_DELAY_SECONDS)
            ),
            args=["startup"],
            id=STARTUP_JOB_ID,
            replace_existing=True,
        )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Планировщик запущен. Следующий запуск: %s", get_next_run_time())


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running


def get_next_run_time() -> datetime | None:
    """Время следующего планового запуска (naive UTC) или None."""
    if _scheduler is None or not _scheduler.running:
        return None
    job = _scheduler.get_job(MAIN_JOB_ID)
    next_time = getattr(job, "next_run_time", None) if job else None
    if next_time is None:
        return None
    return next_time.astimezone(timezone.utc).replace(tzinfo=None)


def _schedule_retry() -> None:
    global _retry_count
    if _retry_count >= settings.MAX_JOB_RETRIES:
        logger.error("Исчерпаны повторы парсинга")
        _retry_count = 0
        return
    _retry_count += 1
    if _scheduler is None or not _scheduler.running:
        logger.warning("Планировщик не запущен, повтор парсинга не запланирован")
        return
    run_date = datetime.now(timezone.utc) + timedelta(minutes=settings.RETRY_DELAY_MINUTES)
    _scheduler.add_job(
        run_parsing_job,
        DateTrigger(run_date=run_date),
        args=["retry"],
        id=RETRY_JOB_ID,
        replace_existing=True,
    )
    logger.warning(
        "Парсинг не удался, повтор %s/%s через %s мин.",
        _retry_count,
        settings.MAX_JOB_RETRIES,
        settings.RETRY_DELAY_MINUTES,
    )


async def run_parsing_job(trigger: str, force: bool = False) -> None:
    global _retry_count
    logger.info("Начало парсинга (trigger=%s)", trigger)
    try:
        report = await parser_service.run_parsing(trigger, force=force)
    except ParsingAlreadyRunningError:
        logger.info("Парсинг уже выполняется, запуск пропущен")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Необработанная ошибка задачи парсинга")
        _schedule_retry()
        return

    logger.info("Отчёт парсинга: %s", report.summary_line())
    if report.status in ("failed", "blocked") and report.retryable:
        _schedule_retry()
    elif report.status in ("success", "partial", "skipped"):
        _retry_count = 0


def reset_retry_counter() -> None:
    global _retry_count
    _retry_count = 0


def get_retry_count() -> int:
    return _retry_count
