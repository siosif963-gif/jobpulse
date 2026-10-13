"""Настройки приложения. Единственный источник конфигурации."""
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: Literal["development", "production"] = "development"
    DATABASE_URL: str = "sqlite:///./database.db"
    LOG_DIR: str = "./logs"
    LOG_LEVEL: str = "INFO"
    APP_TIMEZONE: str = "Europe/Moscow"
    ALLOWED_ORIGINS: str = (
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500,http://127.0.0.1:5500"
    )
    ADMIN_TOKEN: str = ""

    HABR_CAREER_URL: str = "https://career.habr.com"
    HABR_API_PATH: str = "/api/frontend/vacancies"
    HTTP_USER_AGENT: str = "JobPulse/1.0 (+https://github.com/your-name/jobpulse)"
    REQUEST_TIMEOUT_SECONDS: float = Field(10, gt=0)
    REQUEST_DELAY_MIN_SECONDS: float = Field(1.0, ge=0)
    REQUEST_DELAY_MAX_SECONDS: float = Field(3.0, ge=0)
    MAX_CONCURRENT_REQUESTS: int = Field(2, gt=0)
    MAX_PAGES_PER_QUERY: int = Field(60, gt=0)
    MIN_REPARSE_HOURS: float = Field(20, gt=0)
    STALE_AFTER_DAYS: int = Field(7, gt=0)

    SCHEDULER_ENABLED: bool = True
    PARSING_SCHEDULE: Literal["daily", "interval"] = "daily"
    PARSING_DAILY_HOUR: int = Field(3, ge=0, le=23)
    PARSING_INTERVAL_HOURS: float = Field(24, gt=0)
    PARSING_RUN_ON_STARTUP_IF_EMPTY: bool = True
    RETRY_DELAY_MINUTES: float = Field(60, gt=0)
    MAX_JOB_RETRIES: int = Field(3, gt=0)

    DEFAULT_STATS_DAYS: int = Field(30, gt=0)

    @model_validator(mode="after")
    def _check_delays(self) -> "Settings":
        if self.REQUEST_DELAY_MIN_SECONDS > self.REQUEST_DELAY_MAX_SECONDS:
            raise ValueError("REQUEST_DELAY_MIN_SECONDS не может быть больше REQUEST_DELAY_MAX_SECONDS")
        return self

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
