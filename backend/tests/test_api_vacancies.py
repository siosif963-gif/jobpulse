import re

from tests.test_vacancy_service import add_vacancy

Z_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def seed(db):
    add_vacancy(db, 1, title="Python разработчик", salary=(100000, 150000), currency="RUR",
                cities=["Москва", "Казань"], level="middle", techs=["Python", "Django"])
    add_vacancy(db, 2, title="Go разработчик", cities=["Москва"], level="senior", techs=["Go"], days_ago=2)


def test_list_shape_and_dates(client, db):
    seed(db)
    r = client.get("/api/vacancies")
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"] == {"total": 2, "page": 1, "page_size": 20, "total_pages": 1}
    first = body["vacancies"][0]
    assert first["title"] == "Python разработчик"
    assert first["cities"] == ["Москва", "Казань"] and first["city"] == "Москва"
    assert first["tech_stack"] == ["Python", "Django"]
    assert first["experience_label"] == "Middle"
    assert Z_DATE.match(first["published_at"]) and Z_DATE.match(first["parsed_at"])
    assert set(first) == {
        "id", "source", "external_id", "title", "company", "salary_min", "salary_max", "currency", "city",
        "cities", "is_remote", "experience_level", "experience_label", "tech_stack", "employment", "url",
        "published_at", "parsed_at", "is_active",
    }


def test_empty_db_and_out_of_range_page(client, db):
    r = client.get("/api/vacancies")
    assert r.json()["pagination"]["total_pages"] == 0 and r.json()["vacancies"] == []
    seed(db)
    r = client.get("/api/vacancies?page=5")
    assert r.status_code == 200 and r.json()["vacancies"] == []


def test_filters_via_api_and_empty_strings(client, db):
    seed(db)
    assert client.get("/api/vacancies?tech=Go").json()["pagination"]["total"] == 1
    assert client.get("/api/vacancies?tech=&city=&experience_level=&keyword=").json()["pagination"]["total"] == 2
    assert client.get("/api/vacancies?keyword=PYTHON").json()["pagination"]["total"] == 1
    assert client.get("/api/vacancies?salary_min=120000").json()["pagination"]["total"] == 1


def test_validation_errors_are_400_russian(client):
    r = client.get("/api/vacancies?page=0")
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["message"] == "Неверный параметр page: должно быть ≥ 1"
    assert err["details"] == [{"field": "page", "message": "должно быть ≥ 1"}]

    r = client.get("/api/vacancies?page_size=101")
    assert r.status_code == 400 and "≤ 100" in r.json()["error"]["message"]

    r = client.get("/api/vacancies?salary_min=200&salary_max=100")
    assert r.status_code == 400
    assert r.json()["error"]["details"][0]["field"] == "salary_max"

    r = client.get("/api/vacancies?experience_level=boss")
    assert r.status_code == 400 and "допустимые значения" in r.json()["error"]["message"]

    r = client.get("/api/vacancies?page=abc")
    assert r.status_code == 400 and "целым числом" in r.json()["error"]["message"]

    r = client.get("/api/vacancies?keyword=" + "a" * 101)
    assert r.status_code == 400 and "слишком длинное" in r.json()["error"]["message"]


def test_detail(client, db):
    seed(db)
    r = client.get("/api/vacancies/1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1 and "salary_history" in body
    assert Z_DATE.match(body["created_at"]) and Z_DATE.match(body["updated_at"])


def test_detail_not_found_and_bad_id(client):
    r = client.get("/api/vacancies/999")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found", "message": "Вакансия с id=999 не найдена", "details": [],
    }
    assert client.get("/api/vacancies/0").status_code == 400
