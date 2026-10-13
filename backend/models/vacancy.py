from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

vacancy_technologies = Table(
    "vacancy_technologies",
    Base.metadata,
    Column("vacancy_id", Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True),
    Column("technology_id", Integer, ForeignKey("technologies.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_vacancy_technologies_technology_id", "technology_id"),
)


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_vacancies_source_external_id"),
        Index("ix_vacancies_published_at", "published_at"),
        Index("ix_vacancies_published_at_experience_level", "published_at", "experience_level"),
        Index("ix_vacancies_is_active", "is_active"),
        Index("ix_vacancies_currency", "currency"),
        Index("ix_vacancies_parsed_at", "parsed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str | None] = mapped_column(String(300), nullable=True)
    search_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    experience_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    employment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    technologies: Mapped[list["Technology"]] = relationship(  # noqa: F821
        "Technology", secondary=vacancy_technologies, lazy="select"
    )
    cities: Mapped[list["VacancyCity"]] = relationship(
        "VacancyCity", back_populates="vacancy", cascade="all, delete-orphan", passive_deletes=True
    )
    salary_history: Mapped[list["VacancySalaryHistory"]] = relationship(
        "VacancySalaryHistory",
        back_populates="vacancy",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VacancySalaryHistory.recorded_at, VacancySalaryHistory.id",
    )


class VacancyCity(Base):
    __tablename__ = "vacancy_cities"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "city_normalized", name="uq_vacancy_cities_vacancy_city"),
        Index("ix_vacancy_cities_city_normalized", "city_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[int] = mapped_column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    city_normalized: Mapped[str] = mapped_column(String(200), nullable=False)

    vacancy: Mapped[Vacancy] = relationship("Vacancy", back_populates="cities")


class VacancySalaryHistory(Base):
    __tablename__ = "vacancy_salary_history"
    __table_args__ = (Index("ix_vacancy_salary_history_vacancy_recorded", "vacancy_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[int] = mapped_column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    vacancy: Mapped[Vacancy] = relationship("Vacancy", back_populates="salary_history")
