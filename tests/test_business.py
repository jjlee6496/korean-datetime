"""영업일: ParseOptions(business_week=True), business_calendar 주입, 'N거래일 전'·'전 거래일'

달력 데이터는 쓰는 쪽이 넣는 것이라, 여기서는 날짜를 직접 적은 테스트용 달력을 씁니다 (실제 휴장일 아님).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from references import sampled_references

from korean_datetime import ParseOptions, TemporalParser, WeekdayCalendar
from korean_datetime.core.evaluation import GoldCase
from korean_datetime.temporal.evaluation import evaluate_temporal
from korean_datetime.temporal.expectation import evaluate_expectation

# 테스트용 휴일: 2026-10-09(금, 한글날), 2026-10-12(월, 가상), 2026-10-21(수, 가상),
# 2026-11-02 ~ 11-06(월~금 전체, 가상), 2026-12-31(목, 연말 휴장), 2027-01-01(금, 신정)
HOLIDAYS = [
    date(2026, 10, 9),
    date(2026, 10, 12),
    date(2026, 10, 21),
    *(date(2026, 11, d) for d in range(2, 7)),
    date(2026, 12, 31),
    date(2027, 1, 1),
]
CALENDAR = WeekdayCalendar(HOLIDAYS)
WITH_CALENDAR = TemporalParser(ParseOptions(business_week=True, business_calendar=CALENDAR))
NO_CALENDAR = TemporalParser(ParseOptions(business_week=True))


def _span(parser: TemporalParser, text: str, now: datetime) -> tuple[date, date] | None:
    result = parser.parse(text, now=now)
    return None if result is None else (result.start.date(), result.end.date())


def _day(parser: TemporalParser, text: str, now: datetime) -> date | None:
    result = parser.parse(text, now=now)
    return None if result is None else result.start.date()


# ---------------------------------------------------------------- 주 범위


@pytest.mark.parametrize(
    ("now", "text", "start", "end"),
    [
        # 금요일 휴일 → 월~목
        (datetime(2026, 10, 7, 10), "이번 주", date(2026, 10, 5), date(2026, 10, 9)),
        # 월요일 휴일 → 화~금
        (datetime(2026, 10, 7, 10), "다음 주", date(2026, 10, 13), date(2026, 10, 17)),
        # 수요일 휴일 → 월~금 (중간 휴일은 구간 안에 남음)
        (datetime(2026, 10, 19, 10), "이번 주", date(2026, 10, 19), date(2026, 10, 24)),
        # 주 전체가 휴일 → 월~금으로 대체
        (datetime(2026, 10, 28, 10), "다음 주", date(2026, 11, 2), date(2026, 11, 7)),
        # 지난주 (금요일 휴일)
        (datetime(2026, 10, 14, 10), "지난주", date(2026, 10, 5), date(2026, 10, 9)),
    ],
)
def test_business_week_trims_to_first_and_last_business_day(
    now: datetime, text: str, start: date, end: date
) -> None:
    assert _span(WITH_CALENDAR, text, now) == (start, end)


def test_mid_week_holiday_stays_inside_and_is_checkable() -> None:
    start, end = _span(WITH_CALENDAR, "이번 주", datetime(2026, 10, 19, 10)) or (None, None)
    assert (start, end) == (date(2026, 10, 19), date(2026, 10, 24))
    assert not CALENDAR.is_business_day(date(2026, 10, 21))  # 구간 안의 휴일은 달력으로 확인


def test_business_week_without_calendar_is_monday_to_friday() -> None:
    assert _span(NO_CALENDAR, "이번 주", datetime(2026, 10, 7, 10)) == (date(2026, 10, 5), date(2026, 10, 10))


def test_weekday_and_weekend_inside_business_week_are_unchanged() -> None:
    """요일·주말을 짚으면 그 날 그대로 (주 범위만 바뀜)"""
    now = datetime(2026, 10, 7, 10)
    assert _day(WITH_CALENDAR, "다음 주 토요일", now) == date(2026, 10, 17)
    assert _span(WITH_CALENDAR, "이번 주말", now) == (date(2026, 10, 10), date(2026, 10, 12))


@pytest.mark.parametrize(
    ("text", "expression"), [("이번 주", "week(0)"), ("다음주", "week(1)"), ("지난주", "week(-1)")]
)
def test_business_week_matches_weekdays_over_references(text: str, expression: str) -> None:
    """달력 없이 business_week=True면 기준 시각 292개 모두에서 월~금 (식: week(k).weekdays())"""
    cases = []
    for ref in sampled_references():
        want = evaluate_expectation(f"{expression}.weekdays()", ref)
        cases.append(GoldCase(text, want.as_expected() if want else None, "business_week", now=ref))
    report = evaluate_temporal(cases, NO_CALENDAR)
    assert report.overall.accuracy == 1.0, [r.detail for r in report.failures[:3]]


def test_business_week_is_off_by_default() -> None:
    assert _span(TemporalParser(), "이번 주", datetime(2026, 10, 7, 10)) == (
        date(2026, 10, 5),
        date(2026, 10, 12),
    )


# ---------------------------------------------------------------- 영업일 이동


@pytest.mark.parametrize(
    ("now", "text", "expected"),
    [
        # 월요일의 전 거래일 = 금요일
        (datetime(2026, 10, 19, 10), "전 거래일", date(2026, 10, 16)),
        # 금요일이 휴일이면 목요일
        (datetime(2026, 10, 13, 10), "전 거래일", date(2026, 10, 8)),
        # 휴일(토요일) 당일의 전 거래일 = 금요일
        (datetime(2026, 10, 17, 10), "직전 거래일", date(2026, 10, 16)),
        # 주말을 건너뛰어 셈
        (datetime(2026, 10, 20, 10), "3거래일 전", date(2026, 10, 15)),
        # 휴일(수)과 주말을 건너뛰어 셈
        (datetime(2026, 10, 23, 10), "3영업일 전", date(2026, 10, 19)),
        # 연휴(금·월) 뒤 첫 영업일
        (datetime(2026, 10, 8, 10), "다음 거래일", date(2026, 10, 13)),
        (datetime(2026, 10, 8, 10), "2거래일 후", date(2026, 10, 14)),
        # 한 주 전체 휴일을 건너뜀
        (datetime(2026, 10, 30, 10), "다음 영업일", date(2026, 11, 9)),
        # 연말·신정 휴장을 건너 새해로
        (datetime(2026, 12, 30, 10), "다음 거래일", date(2027, 1, 4)),
        (datetime(2027, 1, 4, 10), "전 거래일", date(2026, 12, 30)),
    ],
)
def test_business_day_steps_skip_weekends_and_holidays(now: datetime, text: str, expected: date) -> None:
    assert _day(WITH_CALENDAR, text, now) == expected


@pytest.mark.parametrize("text", ["3거래일 전", "전 거래일", "다음 영업일", "2영업일 후"])
def test_business_day_steps_need_a_calendar(text: str) -> None:
    """달력이 없으면 휴일을 모르므로 인식하지 않음 (주말만 빼고 세면 휴일이 낀 날 틀림)"""
    assert NO_CALENDAR.parse_all(text, now=datetime(2026, 10, 19, 10)) == []


def test_business_day_step_with_time() -> None:
    result = WITH_CALENDAR.parse("전 거래일 오후 3시", now=datetime(2026, 10, 19, 10))
    assert result is not None and result.start == datetime(2026, 10, 16, 15, 0)


def test_weekday_calendar_validates_input() -> None:
    with pytest.raises(TypeError):
        WeekdayCalendar(["2026-10-09"])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        ParseOptions(business_calendar=object())  # type: ignore[arg-type]
