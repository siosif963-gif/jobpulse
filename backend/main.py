"""FastAPI-приложение JobPulse."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import database
import scheduler
from config import settings
from logging_config import setup_logging
from routers import admin, health, stats, vacancies
from services import parser_service, query_service
from services.exceptions import NotFoundError, ParsingAlreadyRunningError

logger = logging.getLogger("jobpulse.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    database.init_db()
    with database.SessionLocal() as db:
        interrupted = parser_service.mark_interrupted_runs(db)
        if interrupted:
            logger.warning("Помечено прерванных запусков: %s", interrupted)
        query_service.seed_initial_queries(db)
    if settings.SCHEDULER_ENABLED:
        scheduler.start_scheduler()
    try:
        yield
    finally:
        if settings.SCHEDULER_ENABLED:
            scheduler.shutdown_scheduler()


app = FastAPI(title="JobPulse API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
    allow_credentials=False,
)


@app.middleware("http")
async def slow_request_logger(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > 500:
        logger.warning("slow request %s %s %dms", request.method, request.url.path, elapsed_ms)
    return response


def _error(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


def _validation_text(err: dict) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    if kind == "greater_than_equal":
        return f"должно быть ≥ {ctx.get('ge')}"
    if kind == "less_than_equal":
        return f"должно быть ≤ {ctx.get('le')}"
    if kind == "greater_than":
        return f"должно быть > {ctx.get('gt')}"
    if kind == "less_than":
        return f"должно быть < {ctx.get('lt')}"
    if kind in ("int_parsing", "int_from_float", "int_type"):
        return "должно быть целым числом"
    if kind in ("literal_error", "enum"):
        expected = str(ctx.get("expected", "")).replace("'", "")
        return f"допустимые значения: {expected}"
    if kind == "string_too_long":
        return "слишком длинное значение"
    if kind == "bool_parsing":
        return "должно быть true или false"
    message = str(err.get("msg", "некорректное значение"))
    return message.removeprefix("Value error, ")


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("query", "path", "body")]
        details.append({"field": loc[-1] if loc else None, "message": _validation_text(err)})
    first = details[0] if details else {"field": None, "message": "некорректный запрос"}
    message = f"Неверный параметр {first['field']}: {first['message']}" if first["field"] else first["message"]
    return _error(400, "validation_error", message, details)


@app.exception_handler(NotFoundError)
async def not_found_handler(_request: Request, exc: NotFoundError):
    return _error(404, "not_found", exc.message)


@app.exception_handler(ParsingAlreadyRunningError)
async def conflict_handler(_request: Request, _exc: ParsingAlreadyRunningError):
    return _error(409, "conflict", "Парсинг уже выполняется")


@app.exception_handler(admin.ForbiddenError)
async def forbidden_handler(_request: Request, _exc: admin.ForbiddenError):
    return _error(403, "forbidden", "Доступ запрещён")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    codes = {404: ("not_found", "Ресурс не найден"), 405: ("method_not_allowed", "Метод не поддерживается")}
    code, message = codes.get(exc.status_code, ("http_error", str(exc.detail)))
    return _error(exc.status_code, code, message)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.error("Необработанное исключение %s %s", request.method, request.url.path, exc_info=exc)
    return _error(500, "internal_error", "Внутренняя ошибка сервера")


app.include_router(health.router)
app.include_router(vacancies.router)
app.include_router(stats.router)
app.include_router(admin.router)
