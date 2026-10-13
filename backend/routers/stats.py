from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import stats as s
from services import stats_service

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/salary-trend", response_model=s.SalaryTrendResponse)
def salary_trend(p: Annotated[s.SalaryTrendParams, Query()], db: Session = Depends(get_db)):
    points = stats_service.salary_trend(
        db,
        tech=p.tech,
        city=p.city,
        experience_level=p.experience_level,
        currency=p.currency,
        period=p.period,
        days=p.days,
    )
    return s.SalaryTrendResponse(
        data_points=[s.TrendPoint(**point) for point in points],
        currency=p.currency,
        filters=s.TrendFilters(
            tech=p.tech, city=p.city, experience_level=p.experience_level, period=p.period, days=p.days
        ),
    )


@router.get("/tech-distribution", response_model=s.TechDistributionResponse)
def tech_distribution(p: Annotated[s.TechDistributionParams, Query()], db: Session = Depends(get_db)):
    items, total = stats_service.tech_distribution(
        db, city=p.city, experience_level=p.experience_level, days=p.days, limit=p.limit
    )
    return s.TechDistributionResponse(
        technologies=[s.TechItem(**i) for i in items],
        total_vacancies=total,
        filters=s.TechFilters(city=p.city, experience_level=p.experience_level, days=p.days, limit=p.limit),
    )


@router.get("/city-distribution", response_model=s.CityDistributionResponse)
def city_distribution(p: Annotated[s.CityDistributionParams, Query()], db: Session = Depends(get_db)):
    items, total = stats_service.city_distribution(
        db, tech=p.tech, experience_level=p.experience_level, days=p.days, limit=p.limit
    )
    return s.CityDistributionResponse(
        cities=[s.CityItem(**i) for i in items],
        total_vacancies=total,
        filters=s.CityFilters(tech=p.tech, experience_level=p.experience_level, days=p.days, limit=p.limit),
    )


@router.get("/experience-distribution", response_model=s.ExperienceDistributionResponse)
def experience_distribution(p: Annotated[s.ExperienceDistributionParams, Query()], db: Session = Depends(get_db)):
    items, total = stats_service.experience_distribution(db, tech=p.tech, city=p.city, days=p.days)
    return s.ExperienceDistributionResponse(
        experience_levels=[s.ExperienceItem(**i) for i in items],
        total_vacancies=total,
        filters=s.ExperienceFilters(tech=p.tech, city=p.city, days=p.days),
    )


@router.get("/summary", response_model=s.SummaryResponse)
def summary(p: Annotated[s.SummaryParams, Query()], db: Session = Depends(get_db)):
    data = stats_service.summary(
        db, tech=p.tech, city=p.city, experience_level=p.experience_level, currency=p.currency, days=p.days
    )
    return s.SummaryResponse(
        summary=s.SummaryData(**data),
        filters=s.SummaryFilters(tech=p.tech, city=p.city, experience_level=p.experience_level, days=p.days),
    )
