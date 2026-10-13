"""Чистые функции нормализации зарплаты."""
import logging
import re

from constants import CURRENCY_ALIASES, SALARY_BOUNDS

logger = logging.getLogger("jobpulse.parser")

SalaryTriple = tuple[int | None, int | None, str | None]
_EMPTY: SalaryTriple = (None, None, None)


def _to_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def normalize_salary_values(salary_from, salary_to, currency_raw) -> SalaryTriple:
    """Приводит числовые поля зарплаты к (min, max, currency) с проверкой границ."""
    currency: str | None = None
    if currency_raw is not None and str(currency_raw).strip():
        currency = CURRENCY_ALIASES.get(str(currency_raw).strip().lower())
        if currency is None:
            logger.warning("Неизвестная валюта зарплаты: %r", currency_raw)
            return _EMPTY

    low_bound, high_bound = SALARY_BOUNDS[currency or "RUR"]
    values: list[int | None] = []
    for raw in (salary_from, salary_to):
        number = _to_int(raw)
        if number is not None and not (low_bound <= number <= high_bound):
            logger.warning("Зарплата %s вне допустимых границ (%s)", number, currency or "RUR")
            number = None
        values.append(number)

    low, high = values
    if low is None and high is None:
        return _EMPTY
    if low is not None and high is not None and low > high:
        low, high = high, low
    return low, high, currency or "RUR"


_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*(к|k|тыс\.?)(?![а-яёa-z]))?")
_THOUSANDS_GLUE_RE = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")


def parse_salary_text(text: str | None) -> SalaryTriple:
    """Разбор текстовой зарплаты (запасной вариант, если числовые поля пусты)."""
    if not text or not text.strip():
        return _EMPTY
    t = text.lower()
    if "договор" in t:
        return _EMPTY

    if "$" in t or "usd" in t:
        currency = "USD"
    elif "€" in t or "eur" in t:
        currency = "EUR"
    else:
        currency = "RUR"

    for space in (" ", " ", " "):
        t = t.replace(space, " ")
    t = _THOUSANDS_GLUE_RE.sub("", t)

    numbers: list[tuple[float, int]] = []
    for match in _NUMBER_RE.finditer(t):
        value = float(match.group(1).replace(",", "."))
        if match.group(2):
            value *= 1000
        elif currency == "RUR" and value < 1000:
            value *= 1000
        numbers.append((value, match.start()))

    if not numbers:
        return _EMPTY

    low: float | None
    high: float | None
    if len(numbers) == 1:
        value, start = numbers[0]
        if t[:start].rstrip().endswith("до"):
            low, high = None, value
        else:
            low, high = value, None
    else:
        low, high = numbers[0][0], numbers[1][0]
        if low > high:
            low, high = high, low

    return normalize_salary_values(low, high, currency)
