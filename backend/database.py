"""Подключение к БД, сессии, инициализация."""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Текущее время: naive UTC (так хранятся все даты в БД)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if make_url(url).database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


engine = _create_engine()

if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import models  # noqa: F401  (регистрация моделей в метаданных)

    if engine.dialect.name == "sqlite":
        db_path = make_url(settings.DATABASE_URL).database
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
