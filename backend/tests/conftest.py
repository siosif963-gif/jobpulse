import json
import os
import tempfile
from pathlib import Path

# Настройки окружения должны быть заданы до импорта приложения
os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "SCHEDULER_ENABLED": "false",
        "APP_ENV": "development",
        "LOG_DIR": tempfile.mkdtemp(prefix="jobpulse-test-logs-"),
        "ADMIN_TOKEN": "test-token",
        "REQUEST_DELAY_MIN_SECONDS": "0",
        "REQUEST_DELAY_MAX_SECONDS": "0",
        "PARSING_RUN_ON_STARTUP_IF_EMPTY": "false",
    }
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import constants  # noqa: E402
import database  # noqa: E402
from config import settings  # noqa: E402
from database import Base  # noqa: E402
from main import app  # noqa: E402
from parsers.habr_parser import HabrParser  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    import models  # noqa: F401

    Base.metadata.drop_all(database.engine)
    Base.metadata.create_all(database.engine)
    monkeypatch.setattr(constants, "RETRY_PAUSES_SECONDS", (0, 0))
    monkeypatch.setattr(settings, "REQUEST_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(settings, "REQUEST_DELAY_MAX_SECONDS", 0)
    yield


@pytest.fixture
def db():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def _override():
        session = database.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[database.get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def pages_handler(pages: dict[int, dict], calls: list | None = None):
    """Обработчик MockTransport: отдаёт JSON по номеру страницы."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        page = int(request.url.params.get("page", "1"))
        if page in pages:
            return httpx.Response(200, json=pages[page])
        return httpx.Response(404)

    return handler


def habr_factory(handler):
    """parser_factory для run_parsing: HabrParser поверх MockTransport."""

    def factory(s):
        return HabrParser(s, transport=httpx.MockTransport(handler))

    return factory
