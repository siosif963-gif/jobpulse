"""Парсер внутреннего JSON-эндпоинта Habr Career."""
import asyncio
import logging
import random
from datetime import datetime, timezone

import httpx

import constants
from parsers.base_parser import BaseParser, PageError, ParsedVacancy
from parsers.exceptions import SourceBlockedError, SourceUnavailableError, StructureChangedError

logger = logging.getLogger("jobpulse.parser")

_KNOWN_LEVELS = set(constants.EXPERIENCE_LEVELS)


class HabrParser(BaseParser):
    source_name = constants.SOURCE_HABR

    def __init__(self, settings, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(settings, transport)
        self._warned_levels: set[str] = set()

    # --- сеть -----------------------------------------------------------
    async def fetch_page(self, keyword: str, page: int) -> dict:
        url = self.settings.HABR_CAREER_URL.rstrip("/") + self.settings.HABR_API_PATH
        params: dict = {"page": page}
        if keyword != constants.ALL_VACANCIES_KEYWORD:
            params["q"] = keyword

        assert self._client is not None and self._semaphore is not None, "парсер не открыт через async with"
        async with self._semaphore:
            await asyncio.sleep(
                random.uniform(self.settings.REQUEST_DELAY_MIN_SECONDS, self.settings.REQUEST_DELAY_MAX_SECONDS)
            )
            pauses = constants.RETRY_PAUSES_SECONDS
            last_error: SourceUnavailableError | None = None
            for attempt in range(len(pauses) + 1):
                if attempt > 0:
                    await asyncio.sleep(pauses[attempt - 1])
                try:
                    response = await self._client.get(url, params=params)
                except httpx.TimeoutException as exc:
                    last_error = SourceUnavailableError(f"Таймаут запроса: {exc!r}", "TIMEOUT")
                    continue
                except httpx.TransportError as exc:
                    last_error = SourceUnavailableError(f"Сетевая ошибка: {exc!r}", "NETWORK")
                    continue

                status = response.status_code
                if status in (403, 429):
                    raise SourceBlockedError(f"Источник ответил HTTP {status}", f"HTTP_{status}")
                if status >= 500:
                    last_error = SourceUnavailableError(f"Источник ответил HTTP {status}", f"HTTP_{status}")
                    continue
                if status >= 400:
                    raise SourceUnavailableError(f"Источник ответил HTTP {status}", f"HTTP_{status}")

                try:
                    data = response.json()
                except ValueError:
                    raise SourceBlockedError("Источник вернул не JSON", "NOT_JSON") from None
                self._validate_structure(data)
                return data

            assert last_error is not None
            raise last_error

    @staticmethod
    def _validate_structure(data) -> None:
        ok = (
            isinstance(data, dict)
            and isinstance(data.get("list"), list)
            and isinstance(data.get("meta"), dict)
            and isinstance(data["meta"].get("totalPages"), int)
            and not isinstance(data["meta"].get("totalPages"), bool)
        )
        if not ok:
            logger.critical("Структура ответа Habr Career изменилась")
            raise StructureChangedError("Структура ответа Habr Career изменилась", "STRUCTURE_CHANGED")

    # --- разбор ---------------------------------------------------------
    def get_total_pages(self, raw: dict) -> int:
        return raw["meta"]["totalPages"]

    def parse_vacancies(self, raw: dict) -> tuple[list[ParsedVacancy], list[PageError]]:
        vacancies: list[ParsedVacancy] = []
        errors: list[PageError] = []
        for item in raw.get("list", []):
            try:
                parsed = self._parse_item(item)
            except Exception as exc:  # noqa: BLE001 — битый элемент не должен ронять страницу
                errors.append(PageError("", None, "ITEM_INVALID", f"Не удалось разобрать вакансию: {exc}"))
                continue
            vacancies.append(parsed)
        return vacancies, errors

    def _parse_item(self, item) -> ParsedVacancy:
        if not isinstance(item, dict):
            raise ValueError("элемент не является объектом")
        vacancy_id = item.get("id")
        if not isinstance(vacancy_id, int) or isinstance(vacancy_id, bool):
            raise ValueError("нет числового id")
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"нет title (id={vacancy_id})")
        href = item.get("href")
        if not isinstance(href, str) or not href.startswith("/"):
            raise ValueError(f"некорректный href (id={vacancy_id})")

        company_obj = item.get("company")
        company = None
        if isinstance(company_obj, dict) and isinstance(company_obj.get("title"), str):
            company = company_obj["title"].strip() or None

        salary = item.get("salary") if isinstance(item.get("salary"), dict) else {}
        salary_min, salary_max, currency = self.normalize_salary(
            salary.get("from"), salary.get("to"), salary.get("currency"), salary.get("formatted")
        )

        cities: list[str] = []
        seen_cities: set[str] = set()
        for location in item.get("locations") or []:
            name = location.get("title") if isinstance(location, dict) else None
            if isinstance(name, str) and name.strip() and name.strip().lower() not in seen_cities:
                seen_cities.add(name.strip().lower())
                cities.append(name.strip())

        tech_stack: list[str] = []
        seen_tech: set[str] = set()
        for skill in item.get("skills") or []:
            name = skill.get("title") if isinstance(skill, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = " ".join(name.split()).lower()
            if normalized not in seen_tech:
                seen_tech.add(normalized)
                tech_stack.append(name.strip())

        employment = item.get("employment")
        return ParsedVacancy(
            source=self.source_name,
            external_id=str(vacancy_id),
            title=title.strip(),
            company=company,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            cities=cities,
            is_remote=bool(item.get("remoteWork")),
            experience_level=self._parse_level(item.get("qualification")),
            tech_stack=tech_stack,
            employment=employment if isinstance(employment, str) and employment else None,
            url=self.settings.HABR_CAREER_URL.rstrip("/") + href,
            published_at=self._parse_published(item.get("publishedDate")),
            archived=bool(item.get("archived")),
        )

    def _parse_level(self, qualification) -> str | None:
        if not isinstance(qualification, str) or not qualification.strip():
            return None
        level = qualification.strip().lower()
        if level in _KNOWN_LEVELS:
            return level
        if level not in self._warned_levels:
            self._warned_levels.add(level)
            logger.warning("Неизвестный уровень квалификации: %r", qualification)
        return None

    @staticmethod
    def _parse_published(published) -> datetime:
        try:
            value = datetime.fromisoformat(published["date"])
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return datetime.now(timezone.utc)
