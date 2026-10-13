import asyncio
import copy
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from config import settings
from database import utcnow
from models import ParsingRun, SearchQuery, Technology, Vacancy, VacancyCity, VacancySalaryHistory
from services import parser_service, query_service
from services.exceptions import ParsingAlreadyRunningError
from tests.conftest import habr_factory, load_fixture, pages_handler


@pytest.fixture
def pages():
    return {1: load_fixture("habr_page_1"), 2: load_fixture("habr_page_2")}


@pytest.fixture(autouse=True)
def one_query(db):
    """Только один запрос __all__, чтобы не умножать страницы."""
    db.add(SearchQuery(keyword="__all__", is_active=True, created_at=utcnow()))
    db.commit()


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


async def test_first_run_saves_everything(db, pages):
    report = await parser_service.run_parsing("cli", parser_factory=habr_factory(pages_handler(pages)))
    assert report.status == "partial"  # из-за одного битого элемента (ITEM_INVALID)
    assert (report.added, report.updated, report.unchanged) == (8, 0, 0)
    assert report.vacancies_seen == 8 and report.queries_processed == 1
    assert report.errors_count == 1  # битый элемент
    assert count(db, Vacancy) == 8
    names = {t.name for t in db.scalars(select(Technology))}
    assert {"Python", "PostgreSQL", "Docker", "Kubernetes"} <= names
    assert count(db, Technology) == len(names)
    assert count(db, VacancyCity) == 10  # 2+1+1+1+1+0+3+1
    # история зарплат только у вакансий с зарплатой: 1001, 1003, 1004, 1005, 1007, 1009
    assert count(db, VacancySalaryHistory) == 6
    run = db.scalar(select(ParsingRun))
    assert run.status == "partial" and run.finished_at is not None
    assert len(json.loads(run.error_messages)) == 1
    query = db.scalar(select(SearchQuery))
    assert query.last_parsed_at is not None


async def test_second_run_is_unchanged(db, pages):
    factory = habr_factory(pages_handler(pages))
    await parser_service.run_parsing("cli", parser_factory=factory)
    report = await parser_service.run_parsing("cli", force=True, parser_factory=factory)
    assert (report.added, report.updated, report.unchanged) == (0, 0, 8)
    assert count(db, Vacancy) == 8
    assert count(db, VacancySalaryHistory) == 6


async def test_salary_change_updates_and_records_history(db, pages):
    factory = habr_factory(pages_handler(pages))
    await parser_service.run_parsing("cli", parser_factory=factory)

    changed = copy.deepcopy(pages)
    changed[1]["list"][0]["salary"]["to"] = 350000
    report = await parser_service.run_parsing(
        "cli", force=True, parser_factory=habr_factory(pages_handler(changed))
    )
    assert (report.added, report.updated, report.unchanged) == (0, 1, 7)
    vacancy = db.scalar(select(Vacancy).where(Vacancy.external_id == "1001"))
    assert vacancy.salary_max == 350000
    history = [(h.salary_min, h.salary_max) for h in vacancy.salary_history]
    assert history == [(200000, 300000), (200000, 350000)]


async def test_min_reparse_hours_and_force(db, pages):
    factory = habr_factory(pages_handler(pages))
    await parser_service.run_parsing("cli", parser_factory=factory)

    skipped = await parser_service.run_parsing("scheduler", parser_factory=factory)
    assert skipped.status == "skipped" and skipped.queries_skipped == 1 and skipped.pages_attempted == 0

    forced = await parser_service.run_parsing("manual", force=True, parser_factory=factory)
    assert forced.status == "partial" and forced.queries_skipped == 0

    query = db.scalar(select(SearchQuery))
    query.last_parsed_at = utcnow() - timedelta(hours=settings.MIN_REPARSE_HOURS + 1)
    db.commit()
    again = await parser_service.run_parsing("scheduler", parser_factory=factory)
    assert again.status == "partial" and again.queries_skipped == 0


async def test_full_crawl_deactivates_missing(db, pages):
    await parser_service.run_parsing("cli", parser_factory=habr_factory(pages_handler(pages)))
    shrunk = copy.deepcopy(pages)
    shrunk[2]["list"] = [i for i in shrunk[2]["list"] if i.get("id") not in (1006, 1009)]
    report = await parser_service.run_parsing(
        "cli", force=True, parser_factory=habr_factory(pages_handler(shrunk))
    )
    assert report.deactivated == 2
    inactive = {v.external_id for v in db.scalars(select(Vacancy).where(Vacancy.is_active.is_(False)))}
    assert inactive == {"1006", "1009"}
    assert count(db, Vacancy) == 8  # ничего не удалено


async def test_incomplete_crawl_does_not_deactivate(db, pages):
    await parser_service.run_parsing("cli", parser_factory=habr_factory(pages_handler(pages)))
    report = await parser_service.run_parsing(
        "cli", force=True, max_pages=1, parser_factory=habr_factory(pages_handler(pages))
    )
    assert report.deactivated == 0
    assert db.scalar(select(func.count()).select_from(Vacancy).where(Vacancy.is_active.is_(False))) == 0


async def test_stale_vacancy_deactivated_and_reactivated(db, pages):
    factory = habr_factory(pages_handler(pages))
    await parser_service.run_parsing("cli", parser_factory=factory)

    # вакансия 1003 выпала из выдачи и «устарела»; полный обход неполный (max_pages=1)
    vacancy = db.scalar(select(Vacancy).where(Vacancy.external_id == "1006"))
    vacancy.parsed_at = utcnow() - timedelta(days=settings.STALE_AFTER_DAYS + 1)
    db.commit()
    dropped = copy.deepcopy(pages)
    dropped[2]["list"] = [i for i in dropped[2]["list"] if i.get("id") != 1006]
    report = await parser_service.run_parsing(
        "cli", force=True, max_pages=1, parser_factory=habr_factory(pages_handler(dropped))
    )
    assert report.deactivated == 1
    db.expire_all()
    assert db.scalar(select(Vacancy).where(Vacancy.external_id == "1006")).is_active is False

    # снова появилась в выдаче -> реактивация считается updated
    report = await parser_service.run_parsing("cli", force=True, parser_factory=factory)
    assert report.updated == 1
    db.expire_all()
    assert db.scalar(select(Vacancy).where(Vacancy.external_id == "1006")).is_active is True


async def test_archived_vacancy_is_inactive(db, pages):
    archived = copy.deepcopy(pages)
    archived[1]["list"][1]["archived"] = True
    await parser_service.run_parsing("cli", parser_factory=habr_factory(pages_handler(archived)))
    vacancy = db.scalar(select(Vacancy).where(Vacancy.external_id == "1002"))
    assert vacancy.is_active is False


async def test_blocked_keeps_saved_queries_and_is_retryable(db, pages):
    db.add(SearchQuery(keyword="Python", is_active=True, created_at=utcnow()))
    db.commit()

    def handler(request):
        if request.url.params.get("q") == "Python":
            return httpx.Response(429)
        return pages_handler(pages)(request)

    report = await parser_service.run_parsing("scheduler", parser_factory=habr_factory(handler))
    assert report.status == "blocked" and report.retryable is True
    assert report.queries_processed == 1 and report.deactivated == 0
    assert count(db, Vacancy) == 8  # __all__ (шёл первым) сохранён
    run = db.scalar(select(ParsingRun))
    assert run.status == "blocked" and run.retryable is True


async def test_structure_changed_is_failed_not_retryable(db):
    handler = lambda r: httpx.Response(200, json=load_fixture("habr_broken"))  # noqa: E731
    report = await parser_service.run_parsing("scheduler", parser_factory=habr_factory(handler))
    assert report.status == "failed" and report.retryable is False
    assert report.errors_count >= 1


async def test_all_queries_failing_is_failed_retryable(db):
    report = await parser_service.run_parsing(
        "scheduler", parser_factory=habr_factory(lambda r: httpx.Response(503))
    )
    assert report.status == "failed" and report.retryable is True and report.queries_processed == 0


async def test_partial_when_some_pages_fail(db, pages):
    def handler(request):
        if request.url.params["page"] == "2":
            return httpx.Response(500)
        return httpx.Response(200, json=pages[1])

    report = await parser_service.run_parsing("cli", parser_factory=habr_factory(handler))
    assert report.status == "partial" and report.pages_failed == 1
    assert report.added == 5


async def test_concurrent_run_rejected(db, pages):
    started = asyncio.Event()
    release = asyncio.Event()
    inner = pages_handler(pages)

    class SlowParser:
        def __init__(self, s):
            from parsers.habr_parser import HabrParser

            self.real = HabrParser(s, transport=httpx.MockTransport(inner))

        async def __aenter__(self):
            await self.real.__aenter__()
            return self

        async def __aexit__(self, *a):
            await self.real.__aexit__(*a)

        async def collect(self, keyword, max_pages):
            started.set()
            await release.wait()
            return await self.real.collect(keyword, max_pages)

    task = asyncio.create_task(parser_service.run_parsing("cli", parser_factory=SlowParser))
    await started.wait()
    assert parser_service.is_running() is True
    with pytest.raises(ParsingAlreadyRunningError):
        await parser_service.run_parsing("manual", parser_factory=SlowParser)
    release.set()
    report = await task
    assert report.status == "partial"
    assert parser_service.is_running() is False


async def test_clean_run_is_success(db, pages):
    clean = copy.deepcopy(pages)
    clean[2]["list"] = [i for i in clean[2]["list"] if "title" in i]
    report = await parser_service.run_parsing("cli", parser_factory=habr_factory(pages_handler(clean)))
    assert report.status == "success" and report.errors_count == 0


def test_mark_interrupted_runs(db):
    db.add(ParsingRun(trigger="cli", status="running", started_at=utcnow()))
    db.add(ParsingRun(trigger="cli", status="success", started_at=utcnow()))
    db.commit()
    assert parser_service.mark_interrupted_runs(db) == 1
    statuses = sorted(r.status for r in db.scalars(select(ParsingRun)))
    assert statuses == ["failed", "success"]
    failed = db.scalar(select(ParsingRun).where(ParsingRun.status == "failed"))
    assert "Прерван перезапуском" in failed.error_messages and failed.finished_at is not None


def test_seed_initial_queries_idempotent(db):
    first = query_service.seed_initial_queries(db)
    second = query_service.seed_initial_queries(db)
    assert first == 5 and second == 0  # __all__ уже есть из фикстуры
    query = db.scalar(select(SearchQuery).where(SearchQuery.keyword == "Python"))
    query.is_active = False
    db.commit()
    query_service.seed_initial_queries(db)
    db.refresh(query)
    assert query.is_active is False  # существующие не меняются


def test_query_service_crud(db):
    query, created = query_service.add_query(db, " Rust ")
    assert created and query.keyword == "Rust"
    _q, created = query_service.add_query(db, "Rust")
    assert not created
    query_service.set_query_active(db, "Rust", False)
    assert db.scalar(select(SearchQuery).where(SearchQuery.keyword == "Rust")).is_active is False
    with pytest.raises(Exception):
        query_service.set_query_active(db, "Nope", True)
    assert "Rust" in [q.keyword for q in query_service.list_queries(db)]


def test_demo_seed_and_clear(db):
    added, _u, _n = parser_service.seed_demo(50)
    assert added == 50
    again = parser_service.seed_demo(50)
    assert again[0] == 0
    assert parser_service.clear_demo() == 50
    assert count(db, Vacancy) == 0
