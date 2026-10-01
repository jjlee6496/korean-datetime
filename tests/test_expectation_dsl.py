"""기대값 식(expectation DSL) 자체의 동작"""

from __future__ import annotations

from datetime import datetime

import pytest

from ko_normalizer.temporal.expectation import Expect, ExpectationError, evaluate_expectation

REF = datetime(2026, 9, 28, 14, 30)  # 월요일


def ev(expr: str, ref: datetime = REF) -> Expect | None:
    return evaluate_expectation(expr, ref)


def span(expr: str, ref: datetime = REF) -> tuple[str, str | None, str]:
    result = ev(expr, ref)
    assert result is not None
    return result.start.isoformat(), result.end.isoformat() if result.end else None, result.kind


def test_day_arithmetic() -> None:
    assert span("today") == ("2026-09-28T00:00:00", "2026-09-29T00:00:00", "date")
    assert span("today + 3d") == ("2026-10-01T00:00:00", "2026-10-02T00:00:00", "date")
    assert span("today - 1w")[0] == "2026-09-21T00:00:00"
    assert span("today + 1mo")[0] == "2026-10-28T00:00:00"
    assert span("md(1, 31) + 1mo", datetime(2026, 1, 5))[0] == "2026-02-28T00:00:00"  # 말일 보정
    assert span("today + 1y")[0] == "2027-09-28T00:00:00"


def test_weeks_and_weekdays() -> None:
    assert span("next(MON)")[0] == "2026-10-05T00:00:00"  # 오늘 제외
    assert span("prev(FRI)")[0] == "2026-09-25T00:00:00"
    assert span("week(0)")[:2] == ("2026-09-28T00:00:00", "2026-10-05T00:00:00")
    assert span("week(1).weekday(WED)")[0] == "2026-10-07T00:00:00"
    assert span("week(0).weekend()")[:2] == ("2026-10-03T00:00:00", "2026-10-05T00:00:00")
    assert span("week(0).weekdays()")[:2] == ("2026-09-28T00:00:00", "2026-10-03T00:00:00")
    assert span("week(1).early()")[:2] == ("2026-10-05T00:00:00", "2026-10-07T00:00:00")


def test_months_and_years() -> None:
    assert span("month(1)")[:2] == ("2026-10-01T00:00:00", "2026-11-01T00:00:00")
    assert span("month(1).nth(1, FRI)")[0] == "2026-10-02T00:00:00"
    assert span("month(1).nth(-1, SUN)")[0] == "2026-10-25T00:00:00"
    assert ev("month(0).nth(5, FRI)") is None  # 9월에는 다섯째 금요일이 없음
    assert span("month(0).row(1)")[:2] == ("2026-08-31T00:00:00", "2026-09-07T00:00:00")  # 9/1이 든 줄
    assert span("month(1).row(-1)")[:2] == ("2026-10-26T00:00:00", "2026-11-02T00:00:00")  # 10/31이 든 줄
    assert span("month(1).row(3).weekday(SAT)")[0] == "2026-10-17T00:00:00"
    assert ev("month(1).row(6)") is None  # 2026년 10월은 5줄
    assert span("month(1).nthweekend(3)")[:2] == ("2026-10-17T00:00:00", "2026-10-19T00:00:00")
    assert span("month(-1).last()")[0] == "2026-08-31T00:00:00"
    assert span("month(0).part(mid)")[:2] == ("2026-09-11T00:00:00", "2026-09-21T00:00:00")
    assert span("year(1).quarter(1)")[:2] == ("2027-01-01T00:00:00", "2027-04-01T00:00:00")
    assert span("year(0).half(2)")[:2] == ("2026-07-01T00:00:00", "2027-01-01T00:00:00")
    assert span("year(0).month(12)")[:2] == ("2026-12-01T00:00:00", "2027-01-01T00:00:00")
    assert ev("md(2, 30)") is None
    assert span("ymd(2025, 4, 14)")[0] == "2025-04-14T00:00:00"


def test_future_moves_to_next_cycle() -> None:
    assert span("future(md(6, 3))")[0] == "2027-06-03T00:00:00"
    assert span("future(md(10, 3))")[0] == "2026-10-03T00:00:00"
    assert span("future(day(15))")[0] == "2026-10-15T00:00:00"
    assert span("future(day(31))")[0] == "2026-10-31T00:00:00"  # 9월엔 31일이 없음
    assert span("future(md(2, 29))")[0] == "2028-02-29T00:00:00"
    assert span("future(month(0).row(1))")[0] == "2026-09-28T00:00:00"  # 9월 1주는 끝남 → 10월 1주(9/28~)
    assert span("future(at(10:00))")[0] == "2026-09-29T10:00:00"
    assert span("future(period(18, 21))")[:2] == ("2026-09-28T18:00:00", "2026-09-28T21:00:00")


def test_times() -> None:
    assert span("now + 90min") == ("2026-09-28T16:00:00", None, "datetime")
    assert span("at(15:30)") == ("2026-09-28T15:30:00", None, "time")
    assert span("at(25:00)")[0] == "2026-09-29T01:00:00"
    assert span("nearest(3:00)")[0] == "2026-09-28T15:00:00"
    assert span("nearest(2:00)")[0] == "2026-09-29T02:00:00"
    assert span("nearest(12:00)")[0] == "2026-09-29T00:00:00"
    assert span("(today + 1d).hour(3)")[0] == "2026-09-29T15:00:00"  # 다른 날: 주간 규칙
    assert span("(today + 1d).hour(9)")[0] == "2026-09-29T09:00:00"
    assert span("today.hour(2)")[0] == "2026-09-28T14:00:00"  # 오늘 후보가 모두 지남 → 주간 규칙
    assert span("(today + 1d).at(19:30)") == ("2026-09-29T19:30:00", None, "datetime")
    assert span("(today + 7d).period(12, 13)")[:2] == ("2026-10-05T12:00:00", "2026-10-05T13:00:00")


def test_ranges_and_spans() -> None:
    assert span("at(15:00).to(at(17:00))")[:2] == ("2026-09-28T15:00:00", "2026-09-28T17:00:00")
    assert span("(today + 1d).to(today + 2d)")[:2] == ("2026-09-29T00:00:00", "2026-10-01T00:00:00")
    assert span("md(10, 3).around(1, 1)")[:2] == ("2026-10-02T00:00:00", "2026-10-05T00:00:00")


def test_lunar() -> None:
    assert span("year(0).lunar(8, 15)")[0] == "2026-09-25T00:00:00"
    assert span("future(lunar(8, 15))")[0] == "2027-09-15T00:00:00"


def test_none_and_errors() -> None:
    assert ev("none") is None
    for bad in ["today +", "unknown()", "next(XYZ)", "today.weekday(MON)", "md(1)", "(today"]:
        with pytest.raises(ExpectationError):
            ev(bad)


def test_past_moves_to_previous_cycle() -> None:
    assert span("past(md(12, 25))")[0] == "2025-12-25T00:00:00"
    assert span("past(lunar(8, 15))")[0] == "2026-09-25T00:00:00"
    assert span("past(md(9, 1))")[0] == "2026-09-01T00:00:00"


def test_to_after_evaluates_end_from_start() -> None:
    assert span("nearest(3:00).to_after(nearest(5:00))", datetime(2026, 9, 28, 16))[:2] == (
        "2026-09-29T03:00:00",
        "2026-09-29T05:00:00",
    )
    assert span("year(-1).month(12).day(30).to_after(future(md(1, 2)))")[:2] == (
        "2025-12-30T00:00:00",
        "2026-01-03T00:00:00",
    )


def test_past_searches_until_the_date_exists() -> None:
    assert span("past(md(2, 29))")[0] == "2024-02-29T00:00:00"


@pytest.mark.parametrize(
    "bad",
    [
        "at(23:99)",
        "at(48:00)",
        "nearest(13:00)",
        "week(0).weekend(1)",
        "month(0).first(3)",
        "today.at(15:00, 1)",
        "month(0).part(soon)",
        "period(21, 18)",
        "today.around(-1, 1)",
    ],
)
def test_invalid_arguments_are_rejected(bad: str) -> None:
    with pytest.raises(ExpectationError):
        ev(bad)


def test_expected_shape_is_recorded() -> None:
    assert ev("at(15:00)").as_expected()["shape"] == "instant"  # type: ignore[union-attr]
    assert ev("today").as_expected()["shape"] == "span"  # type: ignore[union-attr]
    assert ev("at(15:00).to_after(nearest(5:00))").as_expected()["is_range"] is True  # type: ignore[union-attr]


def test_row_weekday_before_the_first_moves_one_week_only_when_past() -> None:
    """달력 첫 줄의 앞 달 칸이 이미 지난 날이면 +1주, 오늘 이후면 그대로. 뒤 달 칸은 대상 아님."""
    assert span("month(1).row(1).weekday(MON)", datetime(2028, 2, 29, 8, 5))[0] == "2028-03-06T00:00:00"
    assert span("month(1).row(1).weekday(MON)")[0] == "2026-09-28T00:00:00"  # 오늘은 지난 날 아님
    assert span("month(-1).row(-1).weekday(SUN)")[0] == "2026-09-06T00:00:00"  # 뒤 달 칸은 그대로


def flags_of(expr: str, ref: datetime = REF) -> set[str]:
    result = ev(expr, ref)
    assert result is not None
    return set(result.ambiguities)


def test_dynamic_ambiguities_are_computed_by_expressions() -> None:
    assert flags_of("future(md(6, 3))") == {"cycle_shifted"}
    assert flags_of("future(md(10, 15))") == set()
    assert flags_of("future(at(10:00))") == {"cycle_shifted"}
    assert flags_of("nearest(2:00)") == {"meridiem", "cycle_shifted"}  # 내일 후보를 고름
    assert flags_of("nearest(3:00)") == {"meridiem"}
    assert flags_of("nearest(12:00)") == {"noon_or_midnight", "cycle_shifted"}
    assert flags_of("(today + 1d).hour(3)") == {"meridiem"}
    assert flags_of("next(MON)") == {"same_weekday"}  # 기준일이 월요일
    assert flags_of("next(FRI)") == set()
    assert flags_of("future(at(25:00))") == {"day_attribution"}
    assert flags_of("future(period(24, 27))") == {"day_attribution"}
    assert flags_of("week(0).weekend().at(15:00)") == {"multi_day_time"}
    assert flags_of("week(1).at(15:00)") == {"multi_day_time"}
    assert flags_of("month(1).row(1).weekday(MON)") == {"calendar_row_spill"}
    assert flags_of("month(1).row(2).weekday(SAT)") == set()
    assert flags_of("future(md(6, 3)).to_after(future(day(5)))") == {"cycle_shifted"}
    assert set(ev("today").as_expected()["ambiguities"]) == set()  # type: ignore[union-attr, arg-type]


@pytest.mark.parametrize(
    "inverted", ["md(10, 5).to(md(10, 3))", "at(17:00).to(at(15:00))", "today.at(9:00).to(now)"]
)
def test_inverted_or_empty_range_is_an_expression_error(inverted: str) -> None:
    """파서는 뒤집힌·빈 범위를 만들지 않으므로, 그런 값을 내는 식은 정답셋 오류"""
    with pytest.raises(ExpectationError, match="범위의 끝"):
        ev(inverted, datetime(2026, 9, 28, 9, 0))
