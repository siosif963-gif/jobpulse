"""Базовый класс парсера и контракты данных."""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TypedDict

import httpx

from parsers.exceptions import SourceBlockedError, StructureChangedError
from parsers.salary import SalaryTriple, normalize_salary_values, parse_salary_text

logger = logging.getLogger("jobpulse.parser")


class ParsedVacancy(TypedDict):
    source: str
    external_id: str
    title: str
    company: str | None
    salary_min: int | None
    salary_max: int | None
    currency: str | None
    cities: list[str]
    is_remote: bool
    experience_level: str | None
    tech_stack: list[str]
    employment: str | None
    url: str
    published_at: datetime
    archived: bool


@dataclass
class PageError:
    keyword: str
    page: int | None
    error_type: str
    message: str


@dataclass
class QueryResult:
    keyword: str
    vacancies: list[ParsedVacancy]
    total_pages: int
    pages_attempted: int
    pages_failed: int
    items_failed: int
    complete: bool
    errors: list[PageError] = field(default_factory=list)


def log_page_error(error: PageError) -> None:
    logger.error("query=%r page=%s type=%s | %s", error.keyword, error.page, error.error_type, error.message)


class BaseParser(ABC):
    source_name: str

    def __init__(self, settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> "BaseParser":
        self._client = httpx.AsyncClient(
            timeout=self.settings.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": self.settings.HTTP_USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
            transport=self._transport,
        )
        self._semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_REQUESTS)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def fetch_page(self, keyword: str, page: int) -> dict:
        """Сырой JSON одной страницы выдачи."""

    @abstractmethod
    def parse_vacancies(self, raw: dict) -> tuple[list[ParsedVacancy], list[PageError]]:
        """Разбор страницы; ошибки отдельных элементов не прерывают разбор."""

    @abstractmethod
    def get_total_pages(self, raw: dict) -> int:
        """Общее число страниц выдачи."""

    def normalize_salary(self, salary_from, salary_to, currency_raw, formatted: str | None = None) -> SalaryTriple:
        result = normalize_salary_values(salary_from, salary_to, currency_raw)
        if result[0] is None and result[1] is None and formatted and formatted.strip():
            if _is_empty(salary_from) and _is_empty(salary_to):
                return parse_salary_text(formatted)
        return result

    async def collect(self, keyword: str, max_pages: int) -> QueryResult:
        from parsers.exceptions import ParserError, SourceUnavailableError

        errors: list[PageError] = []
        vacancies: list[ParsedVacancy] = []
        items_failed = 0

        try:
            first = await self.fetch_page(keyword, 1)
        except SourceUnavailableError as exc:
            error = PageError(keyword, 1, exc.error_type, str(exc))
            log_page_error(error)
            return QueryResult(keyword, [], 0, 1, 1, 0, False, [error])

        total_pages = self.get_total_pages(first)
        parsed, item_errors = self.parse_vacancies(first)
        vacancies.extend(parsed)
        for item_error in item_errors:
            item_error = replace(item_error, keyword=keyword, page=1)
            errors.append(item_error)
            log_page_error(item_error)
        items_failed += len(item_errors)

        last_page = min(total_pages, max_pages)
        pages_attempted = 1
        pages_failed = 0
        if last_page >= 2:
            page_numbers = list(range(2, last_page + 1))
            pages_attempted += len(page_numbers)
            results = await asyncio.gather(
                *(self.fetch_page(keyword, p) for p in page_numbers), return_exceptions=True
            )
            for result in results:
                if isinstance(result, (SourceBlockedError, StructureChangedError)):
                    raise result
            for page, result in zip(page_numbers, results):
                if isinstance(result, BaseException):
                    error_type = result.error_type if isinstance(result, ParserError) else type(result).__name__
                    error = PageError(keyword, page, error_type, str(result) or type(result).__name__)
                    errors.append(error)
                    log_page_error(error)
                    pages_failed += 1
                    continue
                parsed, item_errors = self.parse_vacancies(result)
                vacancies.extend(parsed)
                for item_error in item_errors:
                    item_error = replace(item_error, keyword=keyword, page=page)
                    errors.append(item_error)
                    log_page_error(item_error)
                items_failed += len(item_errors)

        unique: dict[str, ParsedVacancy] = {}
        for vacancy in vacancies:
            unique.setdefault(vacancy["external_id"], vacancy)

        complete = pages_failed == 0 and 1 <= total_pages <= max_pages
        return QueryResult(
            keyword=keyword,
            vacancies=list(unique.values()),
            total_pages=total_pages,
            pages_attempted=pages_attempted,
            pages_failed=pages_failed,
            items_failed=items_failed,
            complete=complete,
            errors=errors,
        )


def _is_empty(value) -> bool:
    return value is None
