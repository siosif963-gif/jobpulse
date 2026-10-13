import pytest

from parsers.salary import normalize_salary_values, parse_salary_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("от 100 000 ₽", (100000, None, "RUR")),
        ("100 000 – 150 000 ₽", (100000, 150000, "RUR")),
        ("до 200 000 ₽", (None, 200000, "RUR")),
        ("по договорённости", (None, None, None)),
        ("100к", (100000, None, "RUR")),
        ("150 000 руб.", (150000, None, "RUR")),
        ("от 1 500 до 2 000 $", (1500, 2000, "USD")),
        ("100–150к", (100000, 150000, "RUR")),
        ("от 3 000 €", (3000, None, "EUR")),
        ("", (None, None, None)),
        (None, (None, None, None)),
        ("200 000 – 100 000 ₽", (100000, 200000, "RUR")),
        ("от 5 ₽", (None, None, None)),
        ("от 100 000 ₽", (100000, None, "RUR")),
        ("без цифр ₽", (None, None, None)),
    ],
)
def test_parse_salary_text(text, expected):
    assert parse_salary_text(text) == expected


@pytest.mark.parametrize(
    "args, expected",
    [
        ((230000, None, "rur"), (230000, None, "RUR")),
        ((None, 110000, "rur"), (None, 110000, "RUR")),
        ((None, None, None), (None, None, None)),
        ((300000, 200000, "rur"), (200000, 300000, "RUR")),
        ((500, None, "rur"), (None, None, None)),
        ((3000, 5000, "usd"), (3000, 5000, "USD")),
        ((100000, None, "kzt"), (None, None, None)),
        ((100000, None, None), (100000, None, "RUR")),
        ((-5, 0, "rur"), (None, None, None)),
        (("120000", None, "RUB"), (120000, None, "RUR")),
        ((50_000_000, 100000, "rur"), (None, 100000, "RUR")),
    ],
)
def test_normalize_salary_values(args, expected):
    assert normalize_salary_values(*args) == expected
