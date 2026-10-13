"""Список вакансий с фильтрами и пагинацией, деталь; общие фильтры для статистики."""
from datetime import timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

import constants
from database import utcnow
from models import Technology, Vacancy, VacancyCity
from schemas.vacancy import VacancyFilters
from services.exceptions import NotFoundError


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def apply_common_filters(
    stmt: Select,
    *,
    tech: str | None = None,
    city: str | None = None,
    experience_level: str | None = None,
    days: int | None = None,
) -> Select:
    """Фильтры, общие для списка вакансий и статистики (раздел 11.1 ТЗ)."""
    tech = _clean(tech)
    if tech:
        stmt = stmt.where(Vacancy.technologies.any(Technology.name_normalized == " ".join(tech.split()).lower()))
    city = _clean(city)
    if city:
        if city == constants.REMOTE_CITY_VALUE:
            stmt = stmt.where(Vacancy.is_remote.is_(True))
        else:
            stmt = stmt.where(Vacancy.cities.any(VacancyCity.city_normalized == city.lower()))
    if experience_level:
        stmt = stmt.where(Vacancy.experience_level == experience_level)
    if days is not None:
        stmt = stmt.where(Vacancy.published_at >= utcnow() - timedelta(days=days))
    return stmt


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_vacancies(db: Session, filters: VacancyFilters) -> tuple[list[Vacancy], int]:
    stmt = apply_common_filters(
        select(Vacancy), tech=filters.tech, city=filters.city, experience_level=filters.experience_level
    )
    if filters.only_active:
        stmt = stmt.where(Vacancy.is_active.is_(True))
    keyword = _clean(filters.keyword)
    if keyword:
        pattern = f"%{_escape_like(keyword.lower())}%"
        stmt = stmt.where(Vacancy.search_text.like(pattern, escape="\\"))
    if filters.salary_min is not None or filters.salary_max is not None:
        stmt = stmt.where(Vacancy.currency == filters.currency)
        if filters.salary_min is not None:
            stmt = stmt.where(func.coalesce(Vacancy.salary_max, Vacancy.salary_min) >= filters.salary_min)
        if filters.salary_max is not None:
            stmt = stmt.where(func.coalesce(Vacancy.salary_min, Vacancy.salary_max) <= filters.salary_max)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = getattr(Vacancy, filters.sort_by)
    ordered = column.desc() if filters.sort_order == "desc" else column.asc()
    stmt = (
        stmt.order_by(ordered.nulls_last(), Vacancy.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
        .options(selectinload(Vacancy.technologies), selectinload(Vacancy.cities))
    )
    return list(db.scalars(stmt)), total


def get_vacancy(db: Session, vacancy_id: int) -> Vacancy:
    stmt = (
        select(Vacancy)
        .where(Vacancy.id == vacancy_id)
        .options(
            selectinload(Vacancy.technologies),
            selectinload(Vacancy.cities),
            selectinload(Vacancy.salary_history),
        )
    )
    vacancy = db.scalar(stmt)
    if vacancy is None:
        raise NotFoundError(f"Вакансия с id={vacancy_id} не найдена")
    return vacancy
