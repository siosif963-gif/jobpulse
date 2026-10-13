from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from database import utcnow
from models import ParsingRun
from services import stats_service
from tests.test_vacancy_service import add_vacancy

MSK = ZoneInfo("Europe/Moscow")


@pytest.mark.parametrize(
    "lo, hi, expected", [(100, 200, 150), (100, None, 100), (None, 200, 200), (None, None, None)]
)
def test_salary_point(lo, hi, expected):
    assert stats_service.salary_point(lo, hi) == expected


def test_bucket_date_periods():
    wednesday = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
    assert stats_service.bucket_date(wednesday, "day", MSK) == date(2026, 10, 14)
    assert stats_service.bucket_date(wednesday, "week", MSK) == date(2026, 10, 12)
    assert stats_service.bucket_date(wednesday, "month", MSK) == date(2026, 10, 1)


def test_bucket_date_moscow_day_boundary():
    # 21:30 UTC = 00:30 следующего дня по Москве (UTC+3)
    late = datetime(2026, 10, 11, 21, 30, tzinfo=timezone.utc)  # воскресенье UTC
    assert stats_service.bucket_date(late, "day", MSK) == date(2026, 10, 12)
    assert stats_service.bucket_date(late, "week", MSK) == date(2026, 10, 12)  # уже понедельник
    naive = datetime(2026, 10, 11, 21, 30)
    assert stats_service.bucket_date(naive, "day", MSK) == date(2026, 10, 12)
    month_edge = datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)
    assert stats_service.bucket_date(month_edge, "month", MSK) == date(2026, 10, 1)


@pytest.fixture
def data(db):
    add_vacancy(db, 1, salary=(100000, 200000), currency="RUR", cities=["Москва"], level="middle",
                techs=["Python", "Django"], days_ago=1)
    add_vacancy(db, 2, salary=(300000, None), currency="RUR", cities=["Москва", "Казань"], level="middle",
                techs=["Python"], days_ago=1)
    add_vacancy(db, 3, remote=True, level="senior", techs=["Java"], days_ago=1)
    add_vacancy(db, 4, salary=(3000, 4000), currency="USD", cities=["казань"], techs=["Python", "Go"], days_ago=1)
    add_vacancy(db, 5, cities=["Москва"], techs=["Go"], days_ago=40)  # вне окна 30 дней
    add_vacancy(db, 6, level="junior", days_ago=1)  # без городов, не удалёнка, без технологий
    return db


def test_salary_trend_one_bucket(data):
    points = stats_service.salary_trend(data, period="month", days=30, currency="RUR")
    assert sum(p["vacancy_count"] for p in points) == 5
    first = next(p for p in points if p["salary_count"] > 0)
    assert first["salary_count"] == 2
    assert first["avg_salary"] == 225000
    assert first["median_salary"] == 225000
    assert first["min_salary"] == 150000 and first["max_salary"] == 300000


def test_trend_currency_filter_and_null_when_no_salaries(data):
    usd = stats_service.salary_trend(data, currency="USD", period="month", days=30)
    assert sum(p["salary_count"] for p in usd) == 1
    assert sum(p["vacancy_count"] for p in usd) == 5
    eur = stats_service.salary_trend(data, currency="EUR", period="month", days=30)
    assert all(p["avg_salary"] is None and p["median_salary"] is None and p["salary_count"] == 0 for p in eur)
    assert all(p["min_salary"] is None and p["max_salary"] is None for p in eur)


def test_trend_filters(data):
    points = stats_service.salary_trend(data, tech="python", period="month", days=30)
    assert sum(p["vacancy_count"] for p in points) == 3
    wide = stats_service.salary_trend(data, period="month", days=365)
    assert sum(p["vacancy_count"] for p in wide) == 6


def test_trend_groups_sorted_by_date(db):
    add_vacancy(db, 1, days_ago=1)
    add_vacancy(db, 2, days_ago=20)
    points = stats_service.salary_trend(db, period="day", days=30)
    assert [p["date"] for p in points] == sorted(p["date"] for p in points)
    assert len(points) == 2


def test_tech_distribution(data):
    items, total = stats_service.tech_distribution(data, days=30, limit=10)
    assert total == 5
    assert items[0] == {"name": "Python", "count": 3, "percentage": 60.0}
    assert [i["name"] for i in items] == ["Python", "Django", "Go", "Java"]  # равные count — по имени
    limited, _ = stats_service.tech_distribution(data, days=30, limit=2)
    assert len(limited) == 2
    by_city, total_city = stats_service.tech_distribution(data, city="__remote__", days=30)
    assert total_city == 1 and by_city[0]["name"] == "Java"


def test_city_distribution(data):
    items, total = stats_service.city_distribution(data, days=30, limit=10)
    assert total == 5
    by_name = {i["name"]: i for i in items}
    assert by_name["Москва"]["count"] == 2 and by_name["Москва"]["value"] == "Москва"
    assert by_name["Казань"]["count"] == 2  # Казань + казань объединены
    assert by_name["Удалёнка"] == {"name": "Удалёнка", "value": "__remote__", "count": 1, "percentage": 20.0}
    assert by_name["Не указан"]["value"] is None and by_name["Не указан"]["count"] == 1
    assert [i["name"] for i in items][:2] == ["Казань", "Москва"]  # равные count — по имени
    top1, _ = stats_service.city_distribution(data, days=30, limit=1)
    assert len(top1) == 1


def test_city_distribution_hides_unspecified_when_zero(db):
    add_vacancy(db, 1, cities=["Москва"])
    items, _ = stats_service.city_distribution(db, days=30)
    assert [i["name"] for i in items] == ["Москва"]


def test_experience_distribution(data):
    items, total = stats_service.experience_distribution(data, days=30)
    assert total == 5
    assert [i["level"] for i in items] == ["intern", "junior", "middle", "senior", "lead", "not_specified"]
    by_level = {i["level"]: i for i in items}
    assert by_level["middle"]["count"] == 2 and by_level["middle"]["percentage"] == 40.0
    assert by_level["intern"]["count"] == 0 and by_level["intern"]["label"] == "Стажёр (Intern)"
    assert by_level["not_specified"]["count"] == 1 and by_level["not_specified"]["label"] == "Не указан"


def test_empty_database(db):
    assert stats_service.salary_trend(db) == []
    assert stats_service.tech_distribution(db) == ([], 0)
    assert stats_service.city_distribution(db) == ([], 0)
    items, total = stats_service.experience_distribution(db)
    assert total == 0 and len(items) == 5 and all(i["count"] == 0 for i in items)
    summary = stats_service.summary(db)
    assert summary["total_vacancies"] == 0 and summary["avg_salary"] is None
    assert summary["top_city"] is None and summary["top_tech"] is None
    assert summary["most_common_experience"] is None and summary["last_updated_at"] is None


def test_summary(data):
    finished = utcnow() - timedelta(hours=1)
    data.add(ParsingRun(trigger="cli", status="success", started_at=finished, finished_at=finished))
    data.add(ParsingRun(trigger="cli", status="failed", started_at=utcnow(), finished_at=utcnow()))
    data.commit()

    s = stats_service.summary(data, days=30, currency="RUR")
    assert s["total_vacancies"] == 5 and s["vacancies_with_salary"] == 2
    assert (s["avg_salary"], s["median_salary"], s["min_salary"], s["max_salary"]) == (225000, 225000, 150000, 300000)
    assert s["top_tech"] == "Python"
    assert s["top_city"] in ("Казань", "Москва")
    assert s["most_common_experience"] == "middle" and s["most_common_experience_label"] == "Middle"
    assert s["last_updated_at"] == finished

    usd = stats_service.summary(data, days=30, currency="USD")
    assert usd["vacancies_with_salary"] == 1 and usd["avg_salary"] == 3500
    only_py = stats_service.summary(data, tech="Python", days=30)
    assert only_py["total_vacancies"] == 3
