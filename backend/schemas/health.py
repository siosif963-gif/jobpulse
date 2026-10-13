from pydantic import BaseModel

from schemas.common import UtcDatetime


class HealthResponse(BaseModel):
    status: str
    last_parsing_at: UtcDatetime | None
    last_run_status: str | None
    vacancies_added: int | None
    vacancies_updated: int | None
    vacancies_deactivated: int | None
    errors: int | None
    total_vacancies: int
    active_vacancies: int
    is_parsing_now: bool
    scheduler_running: bool
    next_run_at: UtcDatetime | None
