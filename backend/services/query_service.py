"""CRUD поисковых запросов и начальный сид."""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import utcnow
from models import SearchQuery
from services.exceptions import NotFoundError

INITIAL_QUERIES_PATH = Path(__file__).resolve().parent.parent / "data" / "initial_queries.json"


def seed_initial_queries(db: Session) -> int:
    """Добавляет отсутствующие запросы из initial_queries.json; существующие не меняет."""
    items = json.loads(INITIAL_QUERIES_PATH.read_text(encoding="utf-8"))
    existing = set(db.scalars(select(SearchQuery.keyword)))
    added = 0
    for item in items:
        keyword = item["keyword"]
        if keyword in existing:
            continue
        db.add(SearchQuery(keyword=keyword, is_active=True, created_at=utcnow()))
        existing.add(keyword)
        added += 1
    db.commit()
    return added


def list_queries(db: Session) -> list[SearchQuery]:
    return list(db.scalars(select(SearchQuery).order_by(SearchQuery.keyword)))


def add_query(db: Session, keyword: str) -> tuple[SearchQuery, bool]:
    """Возвращает (запрос, создан_ли_новый). Существующий запрос включается."""
    keyword = keyword.strip()
    query = db.scalar(select(SearchQuery).where(SearchQuery.keyword == keyword))
    if query is not None:
        if not query.is_active:
            query.is_active = True
            db.commit()
        return query, False
    query = SearchQuery(keyword=keyword, is_active=True, created_at=utcnow())
    db.add(query)
    db.commit()
    return query, True


def set_query_active(db: Session, keyword: str, is_active: bool) -> SearchQuery:
    query = db.scalar(select(SearchQuery).where(SearchQuery.keyword == keyword.strip()))
    if query is None:
        raise NotFoundError(f"Запрос '{keyword}' не найден")
    query.is_active = is_active
    db.commit()
    return query
