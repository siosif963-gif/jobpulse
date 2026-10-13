from datetime import timedelta

import pytest

from database import utcnow
from models import Technology, Vacancy, VacancyCity
from schemas.vacancy import VacancyFilters
from services import vacancy_service
from services.exceptions import NotFoundError


def add_vacancy(db, n, *, title=None, company="ООО Ромашка", salary=(None, None), currency=None, cities=(),
                remote=False, level=None, techs=(), active=True, days_ago=1):
    now = utcnow()
    title = title or f"Вакансия {n}"
    v = Vacancy(
        source="habr", external_id=str(n), title=title, company=company,
        search_text=f"{title} {company or ''}".lower(),
        salary_min=salary[0], salary_max=salary[1], currency=currency,
        city=cities[0] if cities else None, is_remote=remote, experience_level=level,
        url=f"https://example.com/{n}", published_at=now - timedelta(days=days_ago),
        parsed_at=now, is_active=active, created_at=now, updated_at=now,
    )
    for c in cities:
        v.cities.append(VacancyCity(city=c, city_normalized=c.lower()))
    for t in techs:
        norm = t.lower()
        tech = db.query(Technology).filter_by(name_normalized=norm).first() or Technology(name=t, name_normalized=norm)
        v.technologies.append(tech)
    db.add(v)
    db.commit()
    return v


def ids(db, **kwargs):
    items, total = vacancy_service.list_vacancies(db, VacancyFilters(**kwargs))
    return [v.external_id for v in items], total


@pytest.fixture
def data(db):
    add_vacancy(db, 1, title="Разработчик Python", salary=(100000, 150000), currency="RUR",
                cities=["Москва"], level="middle", techs=["Python", "Django"], days_ago=1)
    add_vacancy(db, 2, title="Java разработчик", salary=(200000, None), currency="RUR",
                cities=["Санкт-Петербург", "Москва"], level="senior", techs=["Java"], days_ago=2)
    add_vacancy(db, 3, title="DevOps 100%_надёжность", company=None, remote=True, level="junior",
                techs=["Docker"], days_ago=3)
    add_vacancy(db, 4, title="Go dev", salary=(None, 3000), currency="USD", cities=["Казань"],
                techs=["Go"], active=False, days_ago=4)
    return db


def test_default_only_active_sorted_by_date(data):
    found, total = ids(data)
    assert found == ["1", "2", "3"] and total == 3


def test_only_active_false(data):
    found, total = ids(data, only_active="false")
    assert total == 4 and "4" in found


def test_filter_tech_city_level(data):
    assert ids(data, tech=" python ")[0] == ["1"]
    assert sorted(ids(data, city="москва")[0]) == ["1", "2"]
    assert ids(data, city="__remote__")[0] == ["3"]
    assert ids(data, experience_level="senior")[0] == ["2"]


def test_keyword_cyrillic_case_insensitive(data):
    assert sorted(ids(data, keyword="РАЗРАБОТЧИК")[0]) == ["1", "2"]
    assert ids(data, keyword="ромашка")[0] == ["1", "2"]


def test_keyword_escapes_like_wildcards(data):
    assert ids(data, keyword="100%")[0] == ["3"]
    assert ids(data, keyword="%")[0] == ["3"]
    assert ids(data, keyword="_")[0] == ["3"]
    assert ids(data, keyword="1_0")[0] == []


def test_salary_filters(data):
    assert sorted(ids(data, salary_min=180000)[0]) == ["2"]
    assert sorted(ids(data, salary_min=120000)[0]) == ["1", "2"]
    assert ids(data, salary_max=120000)[0] == ["1"]
    assert ids(data, salary_min=1000, currency="USD", only_active="false")[0] == ["4"]
    # без salary_min/max валюта игнорируется
    assert ids(data, currency="USD")[1] == 3


def test_sorting_nulls_last(data):
    asc, _ = ids(data, sort_by="salary_min", sort_order="asc")
    assert asc == ["1", "2", "3"]
    desc, _ = ids(data, sort_by="salary_min", sort_order="desc")
    assert desc == ["2", "1", "3"]
    by_max, _ = ids(data, sort_by="salary_max", sort_order="desc")
    assert by_max == ["1", "3", "2"] or by_max[0] == "1"
    assert by_max[0] == "1"


def test_pagination(db):
    for n in range(1, 8):
        add_vacancy(db, n, days_ago=n)
    page1, total = ids(db, page_size=3, page=1)
    page3, _ = ids(db, page_size=3, page=3)
    beyond, total2 = ids(db, page_size=3, page=10)
    assert total == 7 and page1 == ["1", "2", "3"] and page3 == ["7"]
    assert beyond == [] and total2 == 7


def test_get_vacancy(data):
    vacancy = vacancy_service.get_vacancy(data, 1)
    assert vacancy.title == "Разработчик Python"
    with pytest.raises(NotFoundError):
        vacancy_service.get_vacancy(data, 999)
