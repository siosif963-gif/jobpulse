from datetime import datetime, timezone
from typing import Annotated, Any, get_args

from pydantic import BaseModel, PlainSerializer, field_validator


def _serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")]


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorBody


class Pagination(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class QueryModel(BaseModel):
    """Базовая модель query-параметров: пустая строка в необязательном поле = None."""

    @field_validator("*", mode="before")
    @classmethod
    def _empty_to_none(cls, value: Any, info) -> Any:
        if isinstance(value, str) and value.strip() == "":
            annotation = cls.model_fields[info.field_name].annotation
            if type(None) in get_args(annotation):
                return None
        return value
