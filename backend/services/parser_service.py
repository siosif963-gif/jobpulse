"""Оркестрация парсинга: запуск, upsert, деактивация, отчёт."""
import asyncio
import json
import logging
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

import constants
import database
from config import settings
from database import utcnow
from models import ParsingRun, SearchQuery, Technology, Vacancy, VacancyCity, VacancySalaryHistory
from parsers.base_parser import ParsedVacancy, QueryResult
from parsers.exceptions import SourceBlockedError, StructureChangedError
from parsers.habr_parser import HabrParser
from services.exceptions import ParsingAlreadyRunningError

logger = logging.getLogger("jobpulse.parser_service")

_lock = asyncio.Lock()


@dataclass
class RunReport:
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    queries_total: int = 0
    queries_processed: int = 0
    queries_skipped: int = 0
    pages_attempted: int = 0
    pages_failed: int = 0
    vacancies_seen: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    errors_count: int = 0
    error_messages: list[str] = field(default_factory=list)
    retryable: bool = False

    def summary_line(self) -> str:
        return (
            f"status={self.status} trigger={self.trigger} queries={self.queries_processed}/{self.queries_total} "
            f"(skipped={self.queries_skipped}) pages={self.pages_attempted} (failed={self.pages_failed}) "
            f"seen={self.vacancies_seen} added={self.added} updated={self.updated} unchanged={self.unchanged} "
            f"deactivated={self.deactivated} errors={self.errors_count}"
        )


def is_running() -> bool:
    return _lock.locked()


# --- синхронные операции с БД (вызываются через asyncio.to_thread) ----------
def _normalize(name: str) -> str:
    return " ".join(name.split()).lower()


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _create_run(trigger: str) -> RunReport:
    with database.SessionLocal() as db:
        run = ParsingRun(trigger=trigger, status="running", started_at=utcnow())
        db.add(run)
        db.commit()
        return RunReport(id=run.id, trigger=trigger, status="running", started_at=run.started_at)


def _persist_run(report: RunReport) -> None:
    with database.SessionLocal() as db:
        run = db.get(ParsingRun, report.id)
        data = asdict(report)
        data.pop("id")
        messages = data.pop("error_messages")
        for key, value in data.items():
            setattr(run, key, value)
        run.error_messages = json.dumps(messages[: constants.MAX_ERROR_MESSAGES], ensure_ascii=False) if messages else None
        db.commit()


def _load_active_queries() -> list[tuple[int, str, datetime | None]]:
    with database.SessionLocal() as db:
        rows = db.execute(
            select(SearchQuery.id, SearchQuery.keyword, SearchQuery.last_parsed_at).where(SearchQuery.is_active.is_(True))
        ).all()
    items = [(r.id, r.keyword, r.last_parsed_at) for r in rows]
    items.sort(key=lambda r: (r[1] != constants.ALL_VACANCIES_KEYWORD, r[1]))
    return items


def _touch_query(query_id: int) -> None:
    with database.SessionLocal() as db:
        db.execute(update(SearchQuery).where(SearchQuery.id == query_id).values(last_parsed_at=utcnow()))
        db.commit()


def _save_vacancies(parsed: list[ParsedVacancy]) -> tuple[int, int, int]:
    """Сохраняет пачку вакансий в одной транзакции. Возвращает (added, updated, unchanged)."""
    if not parsed:
        return 0, 0, 0
    now = utcnow()
    added = updated = unchanged = 0
    with database.SessionLocal() as db:
        try:
            tech_cache = _load_technologies(db, parsed)
            existing = _load_existing(db, parsed)
            for item in parsed:
                vacancy = existing.get((item["source"], item["external_id"]))
                if vacancy is None:
                    _create_vacancy(db, item, now, tech_cache)
                    added += 1
                elif _update_vacancy(vacancy, item, now, tech_cache):
                    updated += 1
                else:
                    unchanged += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return added, updated, unchanged


def _load_technologies(db: Session, parsed: list[ParsedVacancy]) -> dict[str, Technology]:
    names: dict[str, str] = {}
    for item in parsed:
        for name in item["tech_stack"]:
            names.setdefault(_normalize(name), name)
    cache: dict[str, Technology] = {}
    keys = list(names)
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        for tech in db.scalars(select(Technology).where(Technology.name_normalized.in_(chunk))):
            cache[tech.name_normalized] = tech
    for key, name in names.items():
        if key not in cache:
            tech = Technology(name=name, name_normalized=key)
            db.add(tech)
            cache[key] = tech
    db.flush()
    return cache


def _load_existing(db: Session, parsed: list[ParsedVacancy]) -> dict[tuple[str, str], Vacancy]:
    result: dict[tuple[str, str], Vacancy] = {}
    by_source: dict[str, list[str]] = {}
    for item in parsed:
        by_source.setdefault(item["source"], []).append(item["external_id"])
    for source, ids in by_source.items():
        for i in range(0, len(ids), 500):
            stmt = (
                select(Vacancy)
                .where(Vacancy.source == source, Vacancy.external_id.in_(ids[i : i + 500]))
                .options(selectinload(Vacancy.technologies), selectinload(Vacancy.cities))
            )
            for vacancy in db.scalars(stmt):
                result[(vacancy.source, vacancy.external_id)] = vacancy
    return result


def _search_text(title: str, company: str | None) -> str:
    return f"{title} {company or ''}".lower()[:1000]


def _city_pairs(cities: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for city in cities:
        pairs.setdefault(_normalize(city), city)
    return pairs


def _create_vacancy(db: Session, item: ParsedVacancy, now: datetime, tech_cache: dict[str, Technology]) -> None:
    vacancy = Vacancy(
        source=item["source"],
        external_id=item["external_id"],
        title=item["title"],
        company=item["company"],
        search_text=_search_text(item["title"], item["company"]),
        salary_min=item["salary_min"],
        salary_max=item["salary_max"],
        currency=item["currency"],
        city=item["cities"][0] if item["cities"] else None,
        is_remote=item["is_remote"],
        experience_level=item["experience_level"],
        employment=item["employment"],
        url=item["url"],
        published_at=_to_naive_utc(item["published_at"]),
        parsed_at=now,
        is_active=not item["archived"],
        created_at=now,
        updated_at=now,
    )
    for norm, city in _city_pairs(item["cities"]).items():
        vacancy.cities.append(VacancyCity(city=city, city_normalized=norm))
    for name in item["tech_stack"]:
        tech = tech_cache[_normalize(name)]
        if tech not in vacancy.technologies:
            vacancy.technologies.append(tech)
    if item["salary_min"] is not None or item["salary_max"] is not None:
        vacancy.salary_history.append(
            VacancySalaryHistory(
                salary_min=item["salary_min"],
                salary_max=item["salary_max"],
                currency=item["currency"],
                recorded_at=now,
            )
        )
    db.add(vacancy)


def _update_vacancy(vacancy: Vacancy, item: ParsedVacancy, now: datetime, tech_cache: dict[str, Technology]) -> bool:
    """Обновляет вакансию; возвращает True, если что-то изменилось."""
    changed = False
    new_city = item["cities"][0] if item["cities"] else None
    new_published = _to_naive_utc(item["published_at"])
    scalar_fields = {
        "title": item["title"],
        "company": item["company"],
        "currency": item["currency"],
        "city": new_city,
        "is_remote": item["is_remote"],
        "experience_level": item["experience_level"],
        "employment": item["employment"],
        "published_at": new_published,
        "url": item["url"],
    }
    salary_changed = (
        vacancy.salary_min != item["salary_min"]
        or vacancy.salary_max != item["salary_max"]
        or vacancy.currency != item["currency"]
    )
    for name, value in scalar_fields.items():
        if getattr(vacancy, name) != value:
            setattr(vacancy, name, value)
            changed = True
    if vacancy.salary_min != item["salary_min"]:
        vacancy.salary_min = item["salary_min"]
    if vacancy.salary_max != item["salary_max"]:
        vacancy.salary_max = item["salary_max"]
    if salary_changed:
        changed = True
        vacancy.salary_history.append(
            VacancySalaryHistory(
                salary_min=item["salary_min"],
                salary_max=item["salary_max"],
                currency=item["currency"],
                recorded_at=now,
            )
        )
    if changed:
        vacancy.search_text = _search_text(item["title"], item["company"])

    new_cities = _city_pairs(item["cities"])
    old_cities = {c.city_normalized for c in vacancy.cities}
    if set(new_cities) != old_cities:
        changed = True
        for city in list(vacancy.cities):
            if city.city_normalized not in new_cities:
                vacancy.cities.remove(city)
        for norm, city in new_cities.items():
            if norm not in old_cities:
                vacancy.cities.append(VacancyCity(city=city, city_normalized=norm))

    new_techs = {_normalize(name) for name in item["tech_stack"]}
    old_techs = {t.name_normalized for t in vacancy.technologies}
    if new_techs != old_techs:
        changed = True
        unique: dict[str, Technology] = {}
        for name in item["tech_stack"]:
            unique.setdefault(_normalize(name), tech_cache[_normalize(name)])
        vacancy.technologies = list(unique.values())

    new_active = not item["archived"]
    if vacancy.is_active != new_active:
        vacancy.is_active = new_active
        changed = True

    vacancy.parsed_at = now
    if changed:
        vacancy.updated_at = now
    return changed


def _deactivate(started_at: datetime, full_crawl_complete: bool) -> int:
    count = 0
    with database.SessionLocal() as db:
        if full_crawl_complete:
            result = db.execute(
                update(Vacancy)
                .where(
                    Vacancy.source == constants.SOURCE_HABR,
                    Vacancy.is_active.is_(True),
                    Vacancy.parsed_at < started_at,
                )
                .values(is_active=False)
            )
            count += result.rowcount or 0
        threshold = utcnow() - timedelta(days=settings.STALE_AFTER_DAYS)
        result = db.execute(
            update(Vacancy)
            .where(
                Vacancy.source == constants.SOURCE_HABR,
                Vacancy.is_active.is_(True),
                Vacancy.parsed_at < threshold,
            )
            .values(is_active=False)
        )
        count += result.rowcount or 0
        db.commit()
    return count


def mark_interrupted_runs(db: Session) -> int:
    runs = list(db.scalars(select(ParsingRun).where(ParsingRun.status == "running")))
    for run in runs:
        run.status = "failed"
        run.finished_at = utcnow()
        run.retryable = False
        run.error_messages = json.dumps(["Прерван перезапуском приложения"], ensure_ascii=False)
    db.commit()
    return len(runs)


# --- публичная точка входа ------------------------------------------------
async def run_parsing(
    trigger: str,
    force: bool = False,
    max_pages: int | None = None,
    parser_factory=HabrParser,
) -> RunReport:
    if _lock.locked():
        raise ParsingAlreadyRunningError("Парсинг уже выполняется")
    async with _lock:
        report = await asyncio.to_thread(_create_run, trigger)
        try:
            await _execute(report, force, max_pages, parser_factory)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Необработанная ошибка парсинга")
            report.status = "failed"
            report.retryable = True
            report.errors_count += 1
            report.error_messages.append(f"Необработанная ошибка: {exc!r}")
        finally:
            report.finished_at = utcnow()
            await asyncio.to_thread(_persist_run, report)
        logger.info("Парсинг завершён: %s", report.summary_line())
        return report


def _add_errors(report: RunReport, result: QueryResult) -> None:
    for error in result.errors:
        if len(report.error_messages) < constants.MAX_ERROR_MESSAGES:
            report.error_messages.append(
                f"query={error.keyword!r} page={error.page} type={error.error_type}: {error.message}"
            )


async def _execute(report: RunReport, force: bool, max_pages: int | None, parser_factory) -> None:
    queries = await asyncio.to_thread(_load_active_queries)
    report.queries_total = len(queries)

    now = utcnow()
    min_age = timedelta(hours=settings.MIN_REPARSE_HOURS)
    to_parse: list[tuple[int, str]] = []
    for query_id, keyword, last_parsed_at in queries:
        if not force and last_parsed_at is not None and now - last_parsed_at < min_age:
            report.queries_skipped += 1
            continue
        to_parse.append((query_id, keyword))

    if not to_parse:
        report.status = "skipped"
        return

    seen_ids: set[str] = set()
    full_crawl_complete = False
    aborted = False
    page_limit = max_pages or settings.MAX_PAGES_PER_QUERY

    async with parser_factory(settings) as parser:
        for query_id, keyword in to_parse:
            try:
                result = await parser.collect(keyword, page_limit)
            except SourceBlockedError as exc:
                report.status, report.retryable, aborted = "blocked", True, True
                report.errors_count += 1
                report.error_messages.append(f"query={keyword!r}: {exc}")
                logger.error("Источник блокирует запросы: %s", exc)
                break
            except StructureChangedError as exc:
                report.status, report.retryable, aborted = "failed", False, True
                report.errors_count += 1
                report.error_messages.append(f"query={keyword!r}: {exc}")
                logger.critical("Структура ответа Habr Career изменилась: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Ошибка обработки запроса %r", keyword)
                report.errors_count += 1
                report.error_messages.append(f"query={keyword!r}: {exc!r}")
                continue

            report.pages_attempted += result.pages_attempted
            report.pages_failed += result.pages_failed
            report.errors_count += result.pages_failed + result.items_failed
            _add_errors(report, result)

            fresh = [v for v in result.vacancies if v["external_id"] not in seen_ids]
            seen_ids.update(v["external_id"] for v in fresh)
            report.vacancies_seen += len(fresh)

            try:
                added, updated, unchanged = await asyncio.to_thread(_save_vacancies, fresh)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Ошибка сохранения запроса %r", keyword)
                report.errors_count += 1
                report.error_messages.append(f"query={keyword!r}: ошибка сохранения {exc!r}")
                continue
            report.added += added
            report.updated += updated
            report.unchanged += unchanged

            if result.pages_attempted > result.pages_failed:
                await asyncio.to_thread(_touch_query, query_id)
                report.queries_processed += 1
            if keyword == constants.ALL_VACANCIES_KEYWORD and result.complete:
                full_crawl_complete = True

    if not aborted:
        report.deactivated = await asyncio.to_thread(_deactivate, report.started_at, full_crawl_complete)

    if report.status == "running":
        if report.errors_count == 0:
            report.status = "success"
        elif report.queries_processed >= 1:
            report.status = "partial"
        else:
            report.status, report.retryable = "failed", True

    if report.errors_count / max(1, report.pages_attempted + report.vacancies_seen) > 0.5:
        logger.warning("Более 50%% ошибок при парсинге")


# --- демо-данные ------------------------------------------------------------
_DEMO_STACKS = [
    ["Python", "Django", "PostgreSQL", "Docker"],
    ["Python", "FastAPI", "PostgreSQL", "Redis"],
    ["JavaScript", "React", "TypeScript", "HTML", "CSS"],
    ["JavaScript", "Vue.js", "TypeScript"],
    ["Java", "Spring", "PostgreSQL", "Kafka"],
    ["Go", "PostgreSQL", "Docker", "Kubernetes"],
    ["DevOps", "Kubernetes", "Docker", "Terraform", "Linux"],
    ["C#", ".NET", "SQL"],
    ["PHP", "Laravel", "MySQL"],
    ["Kotlin", "Android", "Git"],
    ["Python", "Pandas", "SQL", "Airflow"],
]
_DEMO_CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Минск"]
_DEMO_COMPANIES = ["Альфа Софт", "Бета Системс", "Вектор Лаб", "Горизонт IT", "Дельта Тех", "Эко Дата", "Зенит Диджитал"]
_DEMO_TITLES = ["Backend-разработчик", "Frontend-разработчик", "Fullstack-разработчик", "Разработчик", "Инженер ПО"]
_DEMO_LEVELS = [None, "intern", "junior", "junior", "middle", "middle", "middle", "senior", "senior", "lead"]
_DEMO_BASE_SALARY = {None: 150_000, "intern": 50_000, "junior": 90_000, "middle": 180_000, "senior": 280_000, "lead": 380_000}


def generate_demo_vacancies(count: int) -> list[ParsedVacancy]:
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    vacancies: list[ParsedVacancy] = []
    for i in range(1, count + 1):
        stack = rng.choice(_DEMO_STACKS)
        level = rng.choice(_DEMO_LEVELS)
        is_remote = rng.random() < 0.25
        cities = rng.sample(_DEMO_CITIES, rng.choice([0, 1, 1, 1, 2, 3])) if not (is_remote and rng.random() < 0.5) else []
        salary_min = salary_max = currency = None
        if rng.random() < 0.6:
            base = _DEMO_BASE_SALARY[level] * rng.uniform(0.8, 1.25)
            currency = "RUR"
            if rng.random() < 0.08:
                currency, base = "USD", base / 90
            base = int(round(base, -3 if currency == "RUR" else -2))
            kind = rng.choice(["range", "from", "to"])
            if kind == "range":
                salary_min, salary_max = base, int(base * rng.uniform(1.15, 1.5))
            elif kind == "from":
                salary_min = base
            else:
                salary_max = base
        published = now - timedelta(days=rng.uniform(0, 90))
        title = f"{rng.choice(_DEMO_TITLES)} {stack[0]}"
        vacancies.append(
            ParsedVacancy(
                source=constants.SOURCE_DEMO,
                external_id=f"demo-{i}",
                title=title,
                company=rng.choice(_DEMO_COMPANIES),
                salary_min=salary_min,
                salary_max=salary_max,
                currency=currency,
                cities=cities,
                is_remote=is_remote,
                experience_level=level,
                tech_stack=list(stack),
                employment=rng.choice(["full_time", "full_time", "part_time"]),
                url=f"https://example.com/demo/{i}",
                published_at=published,
                archived=False,
            )
        )
    return vacancies


def seed_demo(count: int = 300) -> tuple[int, int, int]:
    return _save_vacancies(generate_demo_vacancies(count))


def clear_demo() -> int:
    with database.SessionLocal() as db:
        ids = list(db.scalars(select(Vacancy).where(Vacancy.source == constants.SOURCE_DEMO)))
        for vacancy in ids:
            db.delete(vacancy)
        db.commit()
        return len(ids)
