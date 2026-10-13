"""Константы проекта: грейды, спец-значения фильтров, границы зарплат."""

ALL_VACANCIES_KEYWORD = "__all__"
REMOTE_CITY_VALUE = "__remote__"

SOURCE_HABR = "habr"
SOURCE_DEMO = "demo"

EXPERIENCE_LEVELS = ("intern", "junior", "middle", "senior", "lead")
NOT_SPECIFIED_LEVEL = "not_specified"
EXPERIENCE_LABELS = {
    "intern": "Стажёр (Intern)",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
    NOT_SPECIFIED_LEVEL: "Не указан",
}

REMOTE_LABEL = "Удалёнка"
CITY_NOT_SPECIFIED_LABEL = "Не указан"

CURRENCIES = ("RUR", "USD", "EUR")
CURRENCY_ALIASES = {"rur": "RUR", "rub": "RUR", "usd": "USD", "eur": "EUR"}

# (минимум, максимум) допустимого значения зарплаты по валюте
SALARY_BOUNDS = {
    "RUR": (10_000, 10_000_000),
    "USD": (100, 100_000),
    "EUR": (100, 100_000),
}

# Паузы между повторами запроса к источнику (секунды); в тестах подменяются на 0
RETRY_PAUSES_SECONDS = (5, 30)

MAX_ERROR_MESSAGES = 50
STARTUP_PARSING_DELAY_SECONDS = 10
HEALTH_STALE_HOURS = 48
