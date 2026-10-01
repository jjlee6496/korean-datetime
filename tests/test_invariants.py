"""기준 시각을 바꿔가며 해석 규칙(불변식)을 정량 검증

2026-01-01 ~ 2027-12-31의 모든 날(730일)을 기준일로 삼아 규칙 위반 건수가 0인지 확인합니다.
월말/연말/윤년 경계, 요일별 차이를 한 번에 덮습니다.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, datetime, time, timedelta

import pytest

from korean_datetime import TemporalExpression, TemporalParser
from korean_datetime.temporal.lunar import lunar_to_solar

PARSER = TemporalParser()
REFERENCE_DAYS = [date(2026, 1, 1) + timedelta(days=i) for i in range(730)]


def _first_of_next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _row_friday(ref: date) -> date:
    first = _first_of_next_month(ref)
    friday = first - timedelta(days=first.weekday()) + timedelta(days=4)
    return friday + timedelta(days=7) if friday < first and friday < ref else friday


def _parse(text: str, now: datetime) -> TemporalExpression:
    result = PARSER.parse(text, now=now)
    assert result is not None, f"{text!r} @ {now}"
    return result


Check = Callable[[date, date, TemporalExpression], bool]

DATE_RULES: dict[str, Check] = {
    "오늘": lambda ref, got, r: got == ref,
    "내일": lambda ref, got, r: got == ref + timedelta(days=1),
    "모레": lambda ref, got, r: got == ref + timedelta(days=2),
    "어제": lambda ref, got, r: got == ref - timedelta(days=1),
    "3일 뒤": lambda ref, got, r: got == ref + timedelta(days=3),
    "2주 후": lambda ref, got, r: got == ref + timedelta(days=14),
    "금요일": lambda ref, got, r: got.weekday() == 4 and 0 < (got - ref).days <= 7,
    "이번주 월요일": lambda ref, got, r: got.weekday() == 0 and 0 <= (ref - got).days < 7,
    "다음주 월요일": lambda ref, got, r: got.weekday() == 0 and 1 <= (got - ref).days <= 7,
    "주말": lambda ref, got, r: got.weekday() == 5 and r.end.date() > ref and (r.end.date() - got).days == 2,
    "다음달 1일": lambda ref, got, r: got == _first_of_next_month(ref),
    "이번달 말일": lambda ref, got, r: got == ref.replace(day=calendar.monthrange(ref.year, ref.month)[1]),
    "15일": lambda ref, got, r: got.day == 15 and 0 <= (got - ref).days < 31,
    # 달력 줄 기준: 다음 달 1일이 든 월~일 줄의 금요일. 앞 달 칸이 이미 지났으면 +1주
    "다음달 첫째주 금요일": lambda ref, got, r: got == _row_friday(ref),
    # N번째 요일: 다음 달 안의 첫 금요일
    "다음달 첫째 금요일": lambda ref, got, r: (
        got.weekday() == 4 and got.day <= 7 and got.replace(day=1) == _first_of_next_month(ref)
    ),
    "크리스마스": lambda ref, got, r: (got.month, got.day) == (12, 25) and 0 <= (got - ref).days < 366,
    "추석": lambda ref, got, r: (
        got
        == min(x for x in (lunar_to_solar(ref.year, 8, 15), lunar_to_solar(ref.year + 1, 8, 15)) if x >= ref)
    ),
}


@pytest.mark.parametrize("text", DATE_RULES)
def test_date_rules_hold_for_every_reference_day(text: str) -> None:
    rule = DATE_RULES[text]
    violations = []
    for ref in REFERENCE_DAYS:
        result = _parse(text, datetime.combine(ref, time(14, 30)))
        if not rule(ref, result.start.date(), result):
            violations.append(f"{ref}: {result.start.date()}")
    assert violations == [], f"{text!r} 위반 {len(violations)}/{len(REFERENCE_DAYS)}: {violations[:5]}"


@pytest.mark.parametrize("hour", range(1, 13))
def test_ambiguous_hour_is_nearest_future_for_every_minute_of_day(hour: int) -> None:
    """'N시'는 기준 시각 이후 12시간 안의 N시 또는 N+12시"""
    violations = []
    base = datetime(2026, 9, 28)
    for minute_of_day in range(0, 24 * 60, 10):
        now = base + timedelta(minutes=minute_of_day)
        got = _parse(f"{hour}시", now).start
        if not (now - timedelta(minutes=1) < got <= now + timedelta(hours=12)) or got.hour % 12 != hour % 12:
            violations.append(f"{now:%H:%M} → {got}")
    assert violations == [], violations[:5]


@pytest.mark.parametrize("minutes", [1, 30, 59, 90, 600, 1440])
def test_relative_minutes_are_exact(minutes: int) -> None:
    now = datetime(2026, 9, 28, 23, 50)
    assert _parse(f"{minutes}분 후", now).start == now + timedelta(minutes=minutes)
    assert _parse(f"{minutes}분 전", now).start == now - timedelta(minutes=minutes)


def test_last_weekday_is_in_previous_seven_days() -> None:
    violations = []
    for ref in REFERENCE_DAYS:
        got = _parse("지난 금요일", datetime.combine(ref, time(14, 30))).start.date()
        if got.weekday() != 4 or not 1 <= (ref - got).days <= 7:
            violations.append(f"{ref}: {got}")
    assert violations == [], violations[:5]


def test_long_input_is_linear_time() -> None:
    import time as clock

    started = clock.perf_counter()
    PARSER.parse_all("일" * 20000 + " 내일 3시", now=datetime(2026, 9, 28, 14, 30))
    assert clock.perf_counter() - started < 3.0
