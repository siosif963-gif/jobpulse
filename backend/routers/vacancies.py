from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.common import Pagination
from schemas.vacancy import VacancyDetailOut, VacancyFilters, VacancyListResponse, VacancyOut
from services import vacancy_service

router = APIRouter(prefix="/api/vacancies", tags=["vacancies"])


@router.get("", response_model=VacancyListResponse)
def list_vacancies(filters: Annotated[VacancyFilters, Query()], db: Session = Depends(get_db)):
    items, total = vacancy_service.list_vacancies(db, filters)
    total_pages = -(-total // filters.page_size) if total else 0
    return VacancyListResponse(
        vacancies=[VacancyOut.from_vacancy(v) for v in items],
        pagination=Pagination(total=total, page=filters.page, page_size=filters.page_size, total_pages=total_pages),
    )


@router.get("/{vacancy_id}", response_model=VacancyDetailOut)
def get_vacancy(vacancy_id: Annotated[int, Path(ge=1)], db: Session = Depends(get_db)):
    return VacancyDetailOut.from_vacancy(vacancy_service.get_vacancy(db, vacancy_id))
