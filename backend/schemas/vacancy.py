from typing import Literal

from pydantic import BaseModel, Field, field_validator

import constants
from schemas.common import Pagination, QueryModel, UtcDatetime

ExperienceLevel = Literal["intern", "junior", "middle", "senior", "lead"]
Currency = Literal["RUR", "USD", "EUR"]


class VacancyFilters(QueryModel):
    keyword: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    experience_level: ExperienceLevel | None = None
    tech: str | None = Field(default=None, max_length=100)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: Currency = "RUR"
    only_active: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["published_at", "salary_min", "salary_max"] = "published_at"
    sort_order: Literal["asc", "desc"] = "desc"

    @field_validator("salary_max")
    @classmethod
    def _check_range(cls, value, info):
        low = info.data.get("salary_min")
        if value is not None and low is not None and low > value:
            raise ValueError("salary_min не может быть больше salary_max")
        return value


class VacancyOut(BaseModel):
    id: int
    source: str
    external_id: str
    title: str
    company: str | None
    salary_min: int | None
    salary_max: int | None
    currency: str | None
    city: str | None
    cities: list[str]
    is_remote: bool
    experience_level: str | None
    experience_label: str | None
    tech_stack: list[str]
    employment: str | None
    url: str
    published_at: UtcDatetime
    parsed_at: UtcDatetime
    is_active: bool

    @classmethod
    def from_vacancy(cls, v) -> "VacancyOut":
        return cls(
            id=v.id,
            source=v.source,
            external_id=v.external_id,
            title=v.title,
            company=v.company,
            salary_min=v.salary_min,
            salary_max=v.salary_max,
            currency=v.currency,
            city=v.city,
            cities=[c.city for c in sorted(v.cities, key=lambda c: c.id)],
            is_remote=v.is_remote,
            experience_level=v.experience_level,
            experience_label=constants.EXPERIENCE_LABELS.get(v.experience_level) if v.experience_level else None,
            tech_stack=[t.name for t in sorted(v.technologies, key=lambda t: t.id)],
            employment=v.employment,
            url=v.url,
            published_at=v.published_at,
            parsed_at=v.parsed_at,
            is_active=v.is_active,
        )


class SalaryHistoryOut(BaseModel):
    salary_min: int | None
    salary_max: int | None
    currency: str | None
    recorded_at: UtcDatetime


class VacancyDetailOut(VacancyOut):
    created_at: UtcDatetime
    updated_at: UtcDatetime
    salary_history: list[SalaryHistoryOut]

    @classmethod
    def from_vacancy(cls, v) -> "VacancyDetailOut":
        base = VacancyOut.from_vacancy(v).model_dump()
        return cls(
            **base,
            created_at=v.created_at,
            updated_at=v.updated_at,
            salary_history=[
                SalaryHistoryOut(
                    salary_min=h.salary_min, salary_max=h.salary_max, currency=h.currency, recorded_at=h.recorded_at
                )
                for h in v.salary_history
            ],
        )


class VacancyListResponse(BaseModel):
    vacancies: list[VacancyOut]
    pagination: Pagination
