from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from config import settings
from schemas.common import QueryModel, UtcDatetime
from schemas.vacancy import Currency, ExperienceLevel


def _default_days() -> int:
    return settings.DEFAULT_STATS_DAYS


class _StatsBase(QueryModel):
    tech: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    experience_level: ExperienceLevel | None = None
    currency: Currency = "RUR"
    days: int = Field(default_factory=_default_days, ge=1, le=365)


class SalaryTrendParams(_StatsBase):
    period: Literal["day", "week", "month"] = "week"


class TechDistributionParams(QueryModel):
    city: str | None = Field(default=None, max_length=100)
    experience_level: ExperienceLevel | None = None
    days: int = Field(default_factory=_default_days, ge=1, le=365)
    limit: int = Field(default=10, ge=1, le=50)


class CityDistributionParams(QueryModel):
    tech: str | None = Field(default=None, max_length=100)
    experience_level: ExperienceLevel | None = None
    days: int = Field(default_factory=_default_days, ge=1, le=365)
    limit: int = Field(default=10, ge=1, le=50)


class ExperienceDistributionParams(QueryModel):
    tech: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    days: int = Field(default_factory=_default_days, ge=1, le=365)


class SummaryParams(_StatsBase):
    pass


# --- ответы ----------------------------------------------------------------
class TrendPoint(BaseModel):
    date: date
    avg_salary: int | None
    median_salary: int | None
    min_salary: int | None
    max_salary: int | None
    vacancy_count: int
    salary_count: int


class TrendFilters(BaseModel):
    tech: str | None
    city: str | None
    experience_level: str | None
    period: str
    days: int


class SalaryTrendResponse(BaseModel):
    data_points: list[TrendPoint]
    currency: str
    filters: TrendFilters


class TechItem(BaseModel):
    name: str
    count: int
    percentage: float


class TechFilters(BaseModel):
    city: str | None
    experience_level: str | None
    days: int
    limit: int


class TechDistributionResponse(BaseModel):
    technologies: list[TechItem]
    total_vacancies: int
    filters: TechFilters


class CityItem(BaseModel):
    name: str
    value: str | None
    count: int
    percentage: float


class CityFilters(BaseModel):
    tech: str | None
    experience_level: str | None
    days: int
    limit: int


class CityDistributionResponse(BaseModel):
    cities: list[CityItem]
    total_vacancies: int
    filters: CityFilters


class ExperienceItem(BaseModel):
    level: str
    label: str
    count: int
    percentage: float


class ExperienceFilters(BaseModel):
    tech: str | None
    city: str | None
    days: int


class ExperienceDistributionResponse(BaseModel):
    experience_levels: list[ExperienceItem]
    total_vacancies: int
    filters: ExperienceFilters


class SummaryData(BaseModel):
    total_vacancies: int
    vacancies_with_salary: int
    avg_salary: int | None
    median_salary: int | None
    min_salary: int | None
    max_salary: int | None
    currency: str
    top_city: str | None
    top_tech: str | None
    most_common_experience: str | None
    most_common_experience_label: str | None
    last_updated_at: UtcDatetime | None


class SummaryFilters(BaseModel):
    tech: str | None
    city: str | None
    experience_level: str | None
    days: int


class SummaryResponse(BaseModel):
    summary: SummaryData
    filters: SummaryFilters
