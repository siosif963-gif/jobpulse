from datetime import timedelta

import httpx
import pytest

import scheduler
from config import settings
from database import utcnow
from models import ParsingRun
from services import parser_service
from services.parser_service import RunReport
from tests.conftest import habr_factory
from tests.test_vacancy_service import add_vacancy


def add_run(db, status, hours_ago=1, **kwargs):
    when = utcnow() - timedelta(hours=hours_ago)
    db.add(ParsingRun(trigger="cli", status=status, started_at=when, finished_at=when, **kwargs))
    db.commit()


def test_health_no_data(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_data" and body["last_parsing_at"] is None
    assert body["total_vacancies"] == 0 and body["is_parsing_now"] is False
    assert body["scheduler_running"] is False and body["next_run_at"] is None


def test_health_ok(client, db):
    add_vacancy(db, 1)
    add_vacancy(db, 2, active=False)
    add_run(db, "success", added=5, updated=2, deactivated=1, errors_count=3)
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["last_run_status"] == "success"
    assert body["vacancies_added"] == 5 and body["vacancies_updated"] == 2
    assert body["vacancies_deactivated"] == 1 and body["errors"] == 3
    assert body["total_vacancies"] == 2 and body["active_vacancies"] == 1
    assert body["last_parsing_at"].endswith("Z")


def test_health_degraded_on_failed_run(client, db):
    add_vacancy(db, 1)
    add_run(db, "success", hours_ago=5)
    add_run(db, "blocked", hours_ago=1)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["last_run_status"] == "blocked"
    assert body["vacancies_added"] is not None  # из последнего успешного


def test_health_degraded_when_success_is_old(client, db):
    add_vacancy(db, 1)
    add_run(db, "success", hours_ago=49)
    assert client.get("/api/health").json()["status"] == "degraded"


def test_health_ignores_skipped_runs(client, db):
    add_vacancy(db, 1)
    add_run(db, "success", hours_ago=3)
    add_run(db, "skipped", hours_ago=1)
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["last_run_status"] == "success"


# --- admin ------------------------------------------------------------------
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Token": "wrong"}])
def test_admin_forbidden(client, headers):
    r = client.post("/api/admin/parse", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"] == {"code": "forbidden", "message": "Доступ запрещён", "details": []}


def test_admin_disabled_when_token_empty(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    assert client.post("/api/admin/parse", headers={"X-Admin-Token": ""}).status_code == 403
    assert client.post("/api/admin/parse", headers={"X-Admin-Token": "anything"}).status_code == 403


def test_admin_starts_parsing(client, monkeypatch):
    calls = []

    async def fake_job(trigger, force=False):
        calls.append((trigger, force))

    monkeypatch.setattr(scheduler, "run_parsing_job", fake_job)
    r = client.post("/api/admin/parse?force=true", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 202
    assert r.json()["message"].startswith("Парсинг запущен")
    assert calls == [("manual", True)]


def test_admin_conflict_when_running(client, monkeypatch):
    monkeypatch.setattr(parser_service, "is_running", lambda: True)
    r = client.post("/api/admin/parse", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


# --- планировщик: повторы -----------------------------------------------------
class FakeScheduler:
    running = True

    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append(kwargs)


def make_report(status, retryable):
    return RunReport(id=1, trigger="scheduler", status=status, started_at=utcnow(), retryable=retryable)


@pytest.fixture
def fake_scheduler(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", fake)
    scheduler.reset_retry_counter()
    yield fake
    scheduler.reset_retry_counter()


async def test_blocked_schedules_retry_until_limit(fake_scheduler, monkeypatch):
    async def blocked(trigger, force=False, **kw):
        return make_report("blocked", True)

    monkeypatch.setattr(parser_service, "run_parsing", blocked)
    for _ in range(settings.MAX_JOB_RETRIES):
        await scheduler.run_parsing_job("scheduler")
    assert len(fake_scheduler.jobs) == settings.MAX_JOB_RETRIES
    assert all(j["id"] == "parsing_retry" and j["replace_existing"] for j in fake_scheduler.jobs)
    assert fake_scheduler.jobs[0]["args"] == ["retry"]

    await scheduler.run_parsing_job("retry")  # лимит исчерпан
    assert len(fake_scheduler.jobs) == settings.MAX_JOB_RETRIES
    assert scheduler.get_retry_count() == 0  # счётчик сброшен


async def test_success_resets_counter_and_no_retry(fake_scheduler, monkeypatch):
    statuses = iter([("blocked", True), ("success", False)])

    async def run(trigger, force=False, **kw):
        return make_report(*next(statuses))

    monkeypatch.setattr(parser_service, "run_parsing", run)
    await scheduler.run_parsing_job("scheduler")
    assert scheduler.get_retry_count() == 1 and len(fake_scheduler.jobs) == 1
    await scheduler.run_parsing_job("retry")
    assert scheduler.get_retry_count() == 0 and len(fake_scheduler.jobs) == 1


async def test_non_retryable_failure_does_not_retry(fake_scheduler, monkeypatch):
    async def run(trigger, force=False, **kw):
        return make_report("failed", False)

    monkeypatch.setattr(parser_service, "run_parsing", run)
    await scheduler.run_parsing_job("scheduler")
    assert fake_scheduler.jobs == []


async def test_unhandled_exception_is_retried(fake_scheduler, monkeypatch):
    async def boom(trigger, force=False, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(parser_service, "run_parsing", boom)
    await scheduler.run_parsing_job("scheduler")
    assert len(fake_scheduler.jobs) == 1


async def test_job_with_real_blocked_parser(fake_scheduler, db, monkeypatch):
    """Сквозной: реальный run_parsing с подменённым транспортом (403) -> задача повтора."""
    from models import SearchQuery

    db.add(SearchQuery(keyword="__all__", is_active=True, created_at=utcnow()))
    db.commit()
    real = parser_service.run_parsing
    factory = habr_factory(lambda r: httpx.Response(403))

    async def patched(trigger, force=False, **kw):
        return await real(trigger, force=force, parser_factory=factory)

    monkeypatch.setattr(parser_service, "run_parsing", patched)
    await scheduler.run_parsing_job("scheduler")
    assert len(fake_scheduler.jobs) == 1 and fake_scheduler.jobs[0]["id"] == "parsing_retry"


async def test_already_running_is_swallowed(fake_scheduler, monkeypatch):
    from services.exceptions import ParsingAlreadyRunningError

    async def run(trigger, force=False, **kw):
        raise ParsingAlreadyRunningError()

    monkeypatch.setattr(parser_service, "run_parsing", run)
    await scheduler.run_parsing_job("scheduler")
    assert fake_scheduler.jobs == []


def test_scheduler_start_registers_jobs(monkeypatch):
    """Реальный AsyncIOScheduler: основная задача и startup-задача при пустой БД."""
    import asyncio

    monkeypatch.setattr(settings, "PARSING_RUN_ON_STARTUP_IF_EMPTY", True)

    async def go():
        scheduler.start_scheduler()
        try:
            assert scheduler.is_scheduler_running()
            assert scheduler.get_next_run_time() is not None
            raw = scheduler._scheduler
            assert raw.get_job("parsing_main") is not None
            assert raw.get_job("parsing_startup") is not None
        finally:
            scheduler.shutdown_scheduler()

    asyncio.run(go())
    assert not scheduler.is_scheduler_running()
