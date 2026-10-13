import asyncio
import hmac

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

import scheduler
from config import settings
from services import parser_service
from services.exceptions import ParsingAlreadyRunningError

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Ссылки на фоновые задачи, чтобы их не собрал GC
_background_tasks: set[asyncio.Task] = set()


class ForbiddenError(Exception):
    pass


@router.post("/parse", status_code=202)
async def start_parsing(force: bool = Query(False), x_admin_token: str | None = Header(default=None)):
    expected = settings.ADMIN_TOKEN
    if not expected or not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise ForbiddenError()
    if parser_service.is_running():
        raise ParsingAlreadyRunningError("Парсинг уже выполняется")

    task = asyncio.create_task(scheduler.run_parsing_job("manual", force=force))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return JSONResponse(
        status_code=202, content={"message": "Парсинг запущен. Следите за статусом в /api/health"}
    )
