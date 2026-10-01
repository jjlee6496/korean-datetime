"""음력 변환과 명절 (기준: 2026-09-28)"""

from __future__ import annotations

from datetime import timedelta

import pytest
from helpers import TODAY, d, date_span, must

from ko_normalizer.temporal.lunar import lunar_to_solar

# 한국천문연구원 역서 기준으로 알려진 날짜
SEOLLAL = {
    2019: d(2019, 2, 5),
    2020: d(2020, 1, 25),
    2021: d(2021, 2, 12),
    2022: d(2022, 2, 1),
    2023: d(2023, 1, 22),
    2024: d(2024, 2, 10),
    2025: d(2025, 1, 29),
    2026: d(2026, 2, 17),
}
CHUSEOK = {
    2019: d(2019, 9, 13),
    2020: d(2020, 10, 1),
    2021: d(2021, 9, 21),
    2022: d(2022, 9, 10),
    2023: d(2023, 9, 29),
    2024: d(2024, 9, 17),
    2025: d(2025, 10, 6),
    2026: d(2026, 9, 25),
}
BUDDHA = {2023: d(2023, 5, 27), 2024: d(2024, 5, 15), 2025: d(2025, 5, 5), 2026: d(2026, 5, 24)}


@pytest.mark.parametrize(("year", "expected"), SEOLLAL.items())
def test_seollal(year: int, expected: object) -> None:
    assert lunar_to_solar(year, 1, 1) == expected


@pytest.mark.parametrize(("year", "expected"), CHUSEOK.items())
def test_chuseok(year: int, expected: object) -> None:
    assert lunar_to_solar(year, 8, 15) == expected


@pytest.mark.parametrize(("year", "expected"), BUDDHA.items())
def test_buddha_birthday(year: int, expected: object) -> None:
    assert lunar_to_solar(year, 4, 8) == expected


@pytest.mark.parametrize("year", range(1990, 2051))
def test_lunar_new_year_is_in_seollal_window(year: int) -> None:
    """설날은 항상 양력 1/21 ~ 2/20 사이"""
    assert d(year, 1, 21) <= lunar_to_solar(year, 1, 1) <= d(year, 2, 20)


def test_lunar_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        lunar_to_solar(2026, 13, 1)
    with pytest.raises(ValueError):
        lunar_to_solar(2026, 1, 31)


@pytest.mark.parametrize(
    ("text", "month", "day"),
    [("설날", 1, 1), ("구정", 1, 1), ("추석", 8, 15), ("부처님 오신 날", 4, 8), ("정월 대보름", 1, 15)],
)
def test_lunar_holiday_phrase_picks_next_occurrence(text: str, month: int, day: int) -> None:
    this_year = lunar_to_solar(TODAY.year, month, day)
    expected = this_year if this_year >= TODAY else lunar_to_solar(TODAY.year + 1, month, day)
    assert must(text).start.date() == expected


def test_holiday_span_is_three_days_around_the_day() -> None:
    chuseok = lunar_to_solar(2027, 8, 15)  # 올해 추석(9/25)은 지났으므로 내년
    assert date_span("추석 연휴") == (chuseok - timedelta(days=1), chuseok + timedelta(days=2))
