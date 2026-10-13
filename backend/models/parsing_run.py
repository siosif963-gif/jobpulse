from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ParsingRun(Base):
    __tablename__ = "parsing_runs"
    __table_args__ = (
        Index("ix_parsing_runs_started_at", "started_at"),
        Index("ix_parsing_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    queries_total: Mapped[int] = mapped_column(Integer, default=0)
    queries_processed: Mapped[int] = mapped_column(Integer, default=0)
    queries_skipped: Mapped[int] = mapped_column(Integer, default=0)
    pages_attempted: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    vacancies_seen: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    error_messages: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
