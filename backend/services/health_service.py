"""Статус последнего парсинга."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import constants
from database import utcnow
from models import ParsingRun, Vacancy


def get_health(
    db: Session,
    *,
    is_parsing_now: bool = False,
    scheduler_running: bool = False,
    next_run_at=None,
) -> dict:
    total = db.scalar(select(func.count()).select_from(Vacancy)) or 0
    active = db.scalar(select(func.count()).select_from(Vacancy).where(Vacancy.is_active.is_(True))) or 0

    last_run = db.scalar(
        select(ParsingRun)
        .where(ParsingRun.status.not_in(("skipped", "running")))
        .order_by(ParsingRun.started_at.desc(), ParsingRun.id.desc())
        .limit(1)
    )
    last_success = db.scalar(
        select(ParsingRun)
        .where(ParsingRun.status.in_(("success", "partial")))
        .order_by(ParsingRun.started_at.desc(), ParsingRun.id.desc())
        .limit(1)
    )

    if total == 0 and last_success is None:
        status = "no_data"
    elif last_run is not None and last_run.status in ("failed", "blocked"):
        status = "degraded"
    elif last_success is not None and (
        (last_success.finished_at or last_success.started_at)
        < utcnow() - timedelta(hours=constants.HEALTH_STALE_HOURS)
    ):
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "last_parsing_at": (last_success.finished_at or last_success.started_at) if last_success else None,
        "last_run_status": last_run.status if last_run else None,
        "vacancies_added": last_success.added if last_success else None,
        "vacancies_updated": last_success.updated if last_success else None,
        "vacancies_deactivated": last_success.deactivated if last_success else None,
        "errors": last_success.errors_count if last_success else None,
        "total_vacancies": total,
        "active_vacancies": active,
        "is_parsing_now": is_parsing_now,
        "scheduler_running": scheduler_running,
        "next_run_at": next_run_at,
    }
