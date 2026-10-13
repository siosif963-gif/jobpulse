import re

from database import utcnow
from models import ParsingRun
from tests.test_vacancy_service import add_vacancy


def seed(db):
    add_vacancy(db, 1, salary=(100000, 200000), currency="RUR", cities=["Москва"], level="middle",
                techs=["Python"], days_ago=1)
    add_vacancy(db, 2, remote=True, level="senior", techs=["Python", "Go"], days_ago=2)
    db.add(ParsingRun(trigger="cli", status="success", started_at=utcnow(), finished_at=utcnow()))
    db.commit()


def test_salary_trend(client, db):
    seed(db)
    body = client.get("/api/stats/salary-trend?tech=Python&period=day&days=30").json()
    assert body["currency"] == "RUR"
    assert body["filters"] == {"tech": "Python", "city": None, "experience_level": None, "period": "day", "days": 30}
    assert len(body["data_points"]) == 2
    point = next(p for p in body["data_points"] if p["salary_count"])
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", point["date"])
    assert point["avg_salary"] == 150000 and point["vacancy_count"] == 1


def test_defaults_and_empty(client):
    body = client.get("/api/stats/salary-trend").json()
    assert body["data_points"] == [] and body["filters"]["period"] == "week" and body["filters"]["days"] == 30
    assert client.get("/api/stats/tech-distribution").json()["technologies"] == []
    assert client.get("/api/stats/city-distribution").json()["cities"] == []
    exp = client.get("/api/stats/experience-distribution").json()
    assert len(exp["experience_levels"]) == 5 and exp["total_vacancies"] == 0
    assert client.get("/api/stats/summary").json()["summary"]["total_vacancies"] == 0


def test_distributions(client, db):
    seed(db)
    tech = client.get("/api/stats/tech-distribution?limit=1").json()
    assert tech["technologies"] == [{"name": "Python", "count": 2, "percentage": 100.0}]
    assert tech["total_vacancies"] == 2 and tech["filters"]["limit"] == 1

    city = client.get("/api/stats/city-distribution").json()
    assert {c["value"] for c in city["cities"]} == {"Москва", "__remote__"}

    exp = client.get("/api/stats/experience-distribution?tech=Go").json()
    assert exp["total_vacancies"] == 1
    assert [e["count"] for e in exp["experience_levels"]] == [0, 0, 0, 1, 0]


def test_summary_dates_end_with_z(client, db):
    seed(db)
    body = client.get("/api/stats/summary?currency=RUR").json()
    summary = body["summary"]
    assert summary["total_vacancies"] == 2 and summary["vacancies_with_salary"] == 1
    assert summary["last_updated_at"].endswith("Z")
    assert summary["top_tech"] == "Python" and summary["most_common_experience"] in ("middle", "senior")
    assert body["filters"] == {"tech": None, "city": None, "experience_level": None, "days": 30}


def test_validation(client):
    r = client.get("/api/stats/summary?days=366")
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "Неверный параметр days: должно быть ≤ 365"
    assert client.get("/api/stats/summary?days=0").status_code == 400
    assert client.get("/api/stats/tech-distribution?limit=51").status_code == 400
    assert client.get("/api/stats/salary-trend?period=year").status_code == 400
    r = client.get("/api/stats/summary?experience_level=boss")
    assert r.status_code == 400 and "допустимые значения" in r.json()["error"]["message"]
    assert client.get("/api/stats/summary?currency=KZT").status_code == 400
