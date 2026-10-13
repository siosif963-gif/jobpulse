import httpx
import pytest

import constants
from config import settings
from parsers.exceptions import SourceBlockedError, SourceUnavailableError, StructureChangedError
from parsers.habr_parser import HabrParser
from tests.conftest import load_fixture, pages_handler


def parser_with(handler) -> HabrParser:
    return HabrParser(settings, transport=httpx.MockTransport(handler))


def two_pages() -> dict:
    return {1: load_fixture("habr_page_1"), 2: load_fixture("habr_page_2")}


async def test_collect_parses_all_fields():
    async with parser_with(pages_handler(two_pages())) as parser:
        result = await parser.collect("Python", 10)

    by_id = {v["external_id"]: v for v in result.vacancies}
    assert set(by_id) == {"1001", "1002", "1003", "1004", "1005", "1006", "1007", "1009"}
    assert result.total_pages == 2 and result.pages_failed == 0 and result.complete is True

    full = by_id["1001"]
    assert full["title"] == "Python backend"
    assert full["company"] == "Альфа Софт"
    assert (full["salary_min"], full["salary_max"], full["currency"]) == (200000, 300000, "RUR")
    assert full["cities"] == ["Москва", "Санкт-Петербург"]
    assert full["experience_level"] == "middle"
    assert full["tech_stack"] == ["Python", "PostgreSQL"]  # дубль "python" отброшен
    assert full["url"] == "https://career.habr.com/vacancies/1001"
    assert full["published_at"].utcoffset().total_seconds() == 0
    assert full["published_at"].hour == 15  # 18:57 MSK -> 15:57 UTC

    assert by_id["1002"]["salary_min"] is None and by_id["1002"]["currency"] is None
    assert (by_id["1003"]["salary_min"], by_id["1003"]["salary_max"]) == (250000, None)
    assert (by_id["1004"]["salary_min"], by_id["1004"]["salary_max"]) == (None, 110000)
    assert by_id["1005"]["currency"] == "USD" and by_id["1005"]["is_remote"] is True
    assert by_id["1006"]["cities"] == [] and by_id["1006"]["is_remote"] is True
    assert by_id["1006"]["experience_level"] is None
    assert by_id["1007"]["salary_min"] == 150000  # из salary.formatted
    assert by_id["1007"]["cities"] == ["Москва", "Казань", "Минск"]
    assert by_id["1009"]["experience_level"] == "intern"


async def test_broken_item_skipped_with_item_invalid():
    async with parser_with(pages_handler(two_pages())) as parser:
        result = await parser.collect("Python", 10)
    invalid = [e for e in result.errors if e.error_type == "ITEM_INVALID"]
    assert len(invalid) == 1 and invalid[0].page == 2 and invalid[0].keyword == "Python"
    assert result.items_failed == 1
    assert all(v["external_id"] != "1008" for v in result.vacancies)


async def test_duplicates_removed():
    async with parser_with(pages_handler(two_pages())) as parser:
        result = await parser.collect("Python", 10)
    ids = [v["external_id"] for v in result.vacancies]
    assert len(ids) == len(set(ids))
    assert ids.count("1001") == 1


async def test_predicted_salary_ignored():
    async with parser_with(pages_handler(two_pages())) as parser:
        result = await parser.collect("Python", 10)
    assert all((v["salary_max"] or 0) < 999000 and (v["salary_min"] or 0) < 999000 for v in result.vacancies)
    no_salary = next(v for v in result.vacancies if v["external_id"] == "1002")
    assert no_salary["salary_min"] is None and no_salary["salary_max"] is None


async def test_all_keyword_does_not_send_q():
    calls: list[httpx.Request] = []
    async with parser_with(pages_handler(two_pages(), calls)) as parser:
        await parser.collect(constants.ALL_VACANCIES_KEYWORD, 10)
        assert all("q" not in c.url.params for c in calls)
        calls.clear()
        await parser.collect("Python", 10)
        assert all(c.url.params["q"] == "Python" for c in calls)


@pytest.mark.parametrize("status", [403, 429])
async def test_blocked_statuses(status):
    async with parser_with(lambda r: httpx.Response(status)) as parser:
        with pytest.raises(SourceBlockedError):
            await parser.collect("Python", 5)


async def test_non_json_is_blocked():
    async with parser_with(lambda r: httpx.Response(200, text="<html>captcha</html>")) as parser:
        with pytest.raises(SourceBlockedError):
            await parser.collect("Python", 5)


async def test_retry_on_500_then_success():
    state = {"n": 0}
    page = load_fixture("habr_page_1")
    page["meta"]["totalPages"] = 1

    def handler(request):
        state["n"] += 1
        return httpx.Response(500) if state["n"] <= 2 else httpx.Response(200, json=page)

    async with parser_with(handler) as parser:
        result = await parser.collect("Python", 5)
    assert state["n"] == 3
    assert result.pages_failed == 0 and len(result.vacancies) == 5


async def test_page_failure_after_retries_marks_incomplete():
    pages = two_pages()

    def handler(request):
        if request.url.params["page"] == "2":
            return httpx.Response(500)
        return httpx.Response(200, json=pages[1])

    async with parser_with(handler) as parser:
        result = await parser.collect("Python", 5)
    assert result.pages_failed == 1 and result.complete is False
    assert len(result.vacancies) == 5
    assert any(e.error_type == "HTTP_500" and e.page == 2 for e in result.errors)


async def test_first_page_unavailable_returns_empty_result():
    async with parser_with(lambda r: httpx.Response(503)) as parser:
        result = await parser.collect("Python", 5)
    assert result.vacancies == [] and result.pages_failed == 1 and result.complete is False
    assert result.total_pages == 0


async def test_timeout_is_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async with parser_with(handler) as parser:
        with pytest.raises(SourceUnavailableError) as info:
            await parser.fetch_page("Python", 1)
    assert info.value.error_type == "TIMEOUT"


async def test_client_4xx_is_unavailable():
    async with parser_with(lambda r: httpx.Response(404)) as parser:
        with pytest.raises(SourceUnavailableError):
            await parser.fetch_page("Python", 1)


async def test_broken_structure():
    async with parser_with(lambda r: httpx.Response(200, json=load_fixture("habr_broken"))) as parser:
        with pytest.raises(StructureChangedError):
            await parser.collect("Python", 5)


async def test_max_pages_limits_and_marks_incomplete():
    calls: list[httpx.Request] = []
    async with parser_with(pages_handler(two_pages(), calls)) as parser:
        result = await parser.collect("Python", 1)
    assert len(calls) == 1 and result.complete is False and result.pages_attempted == 1


async def test_unknown_qualification_and_bad_published_date():
    page = {
        "list": [
            {
                "id": 1, "href": "/vacancies/1", "title": "X", "qualification": "Architect",
                "publishedDate": {"date": "не дата"}, "salary": None, "company": None,
            }
        ],
        "meta": {"totalPages": 1},
    }
    async with parser_with(lambda r: httpx.Response(200, json=page)) as parser:
        result = await parser.collect("X", 5)
    vacancy = result.vacancies[0]
    assert vacancy["experience_level"] is None and vacancy["company"] is None
    assert vacancy["published_at"].tzinfo is not None
