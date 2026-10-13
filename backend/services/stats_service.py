"""Все расчёты статистики (раздел 11.3 ТЗ)."""
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import constants
from config import settings
from models import ParsingRun, Technology, Vacancy, VacancyCity, vacancy_technologies
from services.vacancy_service import apply_common_filters


def salary_point(salary_min: int | None, salary_max: int | None) -> float | None:
    if salary_min is not None and salary_max is not None:
        return (salary_min + salary_max) / 2
    if salary_min is not None:
        return float(salary_min)
    if salary_max is not None:
        return float(salary_max)
    return None


def bucket_date(published_at: datetime, period: str, tz: tzinfo | str | None = None) -> date:
    if tz is None:
        tz = settings.APP_TIMEZONE
    if isinstance(tz, str):
        tz = ZoneInfo(tz)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    local = published_at.astimezone(tz).date()
    if period == "day":
        return local
    if period == "week":
        return local - timedelta(days=local.weekday())
    if period == "month":
        return local.replace(day=1)
    raise ValueError(f"Неизвестный период: {period}")


def _money(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def _percent(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _salary_stats(points: list[float]) -> dict[str, int | None]:
    if not points:
        return {"avg_salary": None, "median_salary": None, "min_salary": None, "max_salary": None}
    return {
        "avg_salary": _money(sum(points) / len(points)),
        "median_salary": _money(statistics.median(points)),
        "min_salary": _money(min(points)),
        "max_salary": _money(max(points)),
    }


def _filtered_ids(**filters):
    return apply_common_filters(select(Vacancy.id), **filters)


def _total(db: Session, **filters) -> int:
    return db.scalar(select(func.count()).select_from(_filtered_ids(**filters).subquery())) or 0


def salary_trend(
    db: Session,
    *,
    tech: str | None = None,
    city: str | None = None,
    experience_level: str | None = None,
    currency: str = "RUR",
    period: str = "week",
    days: int | None = None,
) -> list[dict]:
    days = days or settings.DEFAULT_STATS_DAYS
    stmt = apply_common_filters(
        select(Vacancy.published_at, Vacancy.salary_min, Vacancy.salary_max, Vacancy.currency),
        tech=tech,
        city=city,
        experience_level=experience_level,
        days=days,
    )
    tz = ZoneInfo(settings.APP_TIMEZONE)
    counts: dict[date, int] = defaultdict(int)
    points: dict[date, list[float]] = defaultdict(list)
    for published_at, s_min, s_max, cur in db.execute(stmt):
        bucket = bucket_date(published_at, period, tz)
        counts[bucket] += 1
        if cur == currency:
            point = salary_point(s_min, s_max)
            if point is not None:
                points[bucket].append(point)
    return [
        {
            "date": bucket,
            **_salary_stats(points.get(bucket, [])),
            "vacancy_count": counts[bucket],
            "salary_count": len(points.get(bucket, [])),
        }
        for bucket in sorted(counts)
    ]


def tech_distribution(
    db: Session,
    *,
    city: str | None = None,
    experience_level: str | None = None,
    days: int | None = None,
    limit: int = 10,
) -> tuple[list[dict], int]:
    days = days or settings.DEFAULT_STATS_DAYS
    filters = {"city": city, "experience_level": experience_level, "days": days}
    total = _total(db, **filters)
    if total == 0:
        return [], 0
    count = func.count(vacancy_technologies.c.vacancy_id)
    rows = db.execute(
        select(Technology.name, count.label("cnt"))
        .select_from(vacancy_technologies)
        .join(Technology, Technology.id == vacancy_technologies.c.technology_id)
        .where(vacancy_technologies.c.vacancy_id.in_(_filtered_ids(**filters)))
        .group_by(Technology.id, Technology.name)
        .order_by(count.desc(), Technology.name.asc())
        .limit(limit)
    ).all()
    return [{"name": n, "count": c, "percentage": _percent(c, total)} for n, c in rows], total


def _city_counts(db: Session, ids_stmt) -> list[dict]:
    """Города (без «Удалёнки» и «Не указан») по убыванию count, затем name."""
    rows = db.execute(
        select(VacancyCity.city_normalized, VacancyCity.city, func.count())
        .where(VacancyCity.vacancy_id.in_(ids_stmt))
        .group_by(VacancyCity.city_normalized, VacancyCity.city)
    ).all()
    totals: Counter[str] = Counter()
    spellings: dict[str, tuple[int, str]] = {}
    for normalized, city, cnt in rows:
        totals[normalized] += cnt
        best = spellings.get(normalized)
        if best is None or cnt > best[0] or (cnt == best[0] and city < best[1]):
            spellings[normalized] = (cnt, city)
    items = [{"name": spellings[n][1], "value": spellings[n][1], "count": c} for n, c in totals.items()]
    items.sort(key=lambda i: (-i["count"], i["name"]))
    return items


def city_distribution(
    db: Session,
    *,
    tech: str | None = None,
    experience_level: str | None = None,
    days: int | None = None,
    limit: int = 10,
) -> tuple[list[dict], int]:
    days = days or settings.DEFAULT_STATS_DAYS
    filters = {"tech": tech, "experience_level": experience_level, "days": days}
    total = _total(db, **filters)
    if total == 0:
        return [], 0
    ids = _filtered_ids(**filters)
    items = _city_counts(db, ids)

    remote = db.scalar(
        select(func.count()).select_from(ids.where(Vacancy.is_remote.is_(True)).subquery())
    ) or 0
    if remote:
        items.append({"name": constants.REMOTE_LABEL, "value": constants.REMOTE_CITY_VALUE, "count": remote})

    unspecified = db.scalar(
        select(func.count()).select_from(
            ids.where(Vacancy.is_remote.is_(False), ~Vacancy.cities.any()).subquery()
        )
    ) or 0
    if unspecified:
        items.append({"name": constants.CITY_NOT_SPECIFIED_LABEL, "value": None, "count": unspecified})

    items.sort(key=lambda i: (-i["count"], i["name"]))
    items = items[:limit]
    for item in items:
        item["percentage"] = _percent(item["count"], total)
    return items, total


def experience_distribution(
    db: Session,
    *,
    tech: str | None = None,
    city: str | None = None,
    days: int | None = None,
) -> tuple[list[dict], int]:
    days = days or settings.DEFAULT_STATS_DAYS
    filters = {"tech": tech, "city": city, "days": days}
    total = _total(db, **filters)
    counts: dict[str | None, int] = {}
    if total:
        stmt = apply_common_filters(select(Vacancy.experience_level, func.count()), **filters).group_by(
            Vacancy.experience_level
        )
        counts = {level: cnt for level, cnt in db.execute(stmt)}

    items = [
        {
            "level": level,
            "label": constants.EXPERIENCE_LABELS[level],
            "count": counts.get(level, 0),
            "percentage": _percent(counts.get(level, 0), total),
        }
        for level in constants.EXPERIENCE_LEVELS
    ]
    unspecified = counts.get(None, 0)
    if unspecified > 0:
        items.append(
            {
                "level": constants.NOT_SPECIFIED_LEVEL,
                "label": constants.EXPERIENCE_LABELS[constants.NOT_SPECIFIED_LEVEL],
                "count": unspecified,
                "percentage": _percent(unspecified, total),
            }
        )
    return items, total


def summary(
    db: Session,
    *,
    tech: str | None = None,
    city: str | None = None,
    experience_level: str | None = None,
    currency: str = "RUR",
    days: int | None = None,
) -> dict:
    days = days or settings.DEFAULT_STATS_DAYS
    filters = {"tech": tech, "city": city, "experience_level": experience_level, "days": days}

    rows = db.execute(
        apply_common_filters(
            select(Vacancy.salary_min, Vacancy.salary_max, Vacancy.currency, Vacancy.experience_level), **filters
        )
    ).all()
    points = [
        p
        for s_min, s_max, cur, _lvl in rows
        if cur == currency and (p := salary_point(s_min, s_max)) is not None
    ]

    ids = _filtered_ids(**filters)
    cities = _city_counts(db, ids)
    top_city = cities[0]["name"] if cities else None

    top_tech_row = db.execute(
        select(Technology.name)
        .select_from(vacancy_technologies)
        .join(Technology, Technology.id == vacancy_technologies.c.technology_id)
        .where(vacancy_technologies.c.vacancy_id.in_(ids))
        .group_by(Technology.id, Technology.name)
        .order_by(func.count().desc(), Technology.name.asc())
        .limit(1)
    ).first()

    levels = Counter(lvl for *_rest, lvl in rows if lvl is not None)
    common_level = None
    if levels:
        order = {lvl: i for i, lvl in enumerate(constants.EXPERIENCE_LEVELS)}
        common_level = min(levels, key=lambda lvl: (-levels[lvl], order.get(lvl, 99)))

    last_updated = db.scalar(
        select(ParsingRun.finished_at)
        .where(ParsingRun.status.in_(("success", "partial")), ParsingRun.finished_at.is_not(None))
        .order_by(ParsingRun.finished_at.desc())
        .limit(1)
    )

    return {
        "total_vacancies": len(rows),
        "vacancies_with_salary": len(points),
        **_salary_stats(points),
        "currency": currency,
        "top_city": top_city,
        "top_tech": top_tech_row[0] if top_tech_row else None,
        "most_common_experience": common_level,
        "most_common_experience_label": constants.EXPERIENCE_LABELS.get(common_level) if common_level else None,
        "last_updated_at": last_updated,
    }
