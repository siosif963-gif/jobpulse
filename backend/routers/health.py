from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import scheduler
from database import get_db
from schemas.health import HealthResponse
from services import health_service, parser_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    return health_service.get_health(
        db,
        is_parsing_now=parser_service.is_running(),
        scheduler_running=scheduler.is_scheduler_running(),
        next_run_at=scheduler.get_next_run_time(),
    )
