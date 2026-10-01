"""모호성 검출 (기준: 2026-09-28 월요일 14:30)

값은 정책대로 하나를 정하고, 추정이 들어간 부분을 `ambiguities`로 알린다.
오전/오후(3시)와 정오/자정(12시)은 문장만 보고 항상 표시한다 (값은 가까운 미래 그대로).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from helpers import NOW, must, p

from ko_normalizer import Ambiguity

A = Ambiguity


def flags(text: str, now: datetime = NOW) -> set[str]:
    return {a.value for a in must(text, now).ambiguities}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 생략된 연/월/일을 실제로 다음 주기로 넘겼을 때만
        ("6월 3일", {A.CYCLE_SHIFTED}),
        ("10월 15일", set()),
        ("15일", {A.CYCLE_SHIFTED}),
        ("30일", set()),
        ("첫째주", {A.CYCLE_SHIFTED}),
        ("신정", {A.CYCLE_SHIFTED}),
        ("크리스마스", set()),
        ("2월 29일", {A.CYCLE_SHIFTED}),
        ("올해 현충일", set()),  # 명시하면 넘기지 않음
        ("오전 10시", {A.CYCLE_SHIFTED}),  # 지나서 내일로
        ("오후 3시", set()),
        ("새벽 2시", {A.CYCLE_SHIFTED}),
        # 오늘과 같은 요일
        ("월요일", {A.SAME_WEEKDAY}),
        ("다음 월요일", {A.SAME_WEEKDAY}),
        ("금요일", set()),
        ("이번주 월요일", set()),
        # 자정을 넘는 시각의 날짜 귀속
        ("밤 1시", {A.DAY_ATTRIBUTION}),
        ("자정", {A.DAY_ATTRIBUTION}),
        ("오늘 자정", {A.DAY_ATTRIBUTION}),
        ("밤 12시", {A.DAY_ATTRIBUTION}),
        ("심야", {A.DAY_ATTRIBUTION}),
        ("밤 11시", set()),
        # 여러 날짜 구간에 시각이 붙음 (첫날로 정함)
        ("이번 주말 오후 3시", {A.MULTI_DAY_TIME}),
        ("다음주 오후 3시", {A.MULTI_DAY_TIME}),
        ("내일 오후 3시", set()),
        # 달력 줄 경계 (앞뒤 달 칸)
        ("다음달 첫번째 주 월요일", {A.CALENDAR_ROW_SPILL}),
        ("저번달 마지막주 일요일", {A.CALENDAR_ROW_SPILL}),
        ("다음달 두번째주 토요일", set()),
        # 정책으로 정한 표현
        ("다음 주말", {A.NEXT_WEEKEND}),
        ("다음주말", {A.NEXT_WEEKEND}),
        ("다음 주 주말", set()),
        # 두 자리 연도
        ("99년 3월 1일", {A.TWO_DIGIT_YEAR}),
        ("25.07.15", {A.TWO_DIGIT_YEAR}),
        ("2025년 4월 14일", set()),
    ],
)
def test_detected_ambiguities(text: str, expected: set[Ambiguity]) -> None:
    assert flags(text) == {a.value for a in expected}


def test_boundary_spill_after_plus_one_week_is_still_flagged() -> None:
    assert flags("다음달 첫번째 주 월요일", datetime(2028, 2, 29, 8, 5)) == {"calendar_row_spill"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3시", {"meridiem"}),
        ("세시 반", {"meridiem"}),
        ("2시", {"meridiem", "cycle_shifted"}),  # 내일 02:00 후보를 고름
        ("12시", {"noon_or_midnight", "cycle_shifted"}),
        ("12시 30분", {"noon_or_midnight", "cycle_shifted"}),
        ("내일 3시", {"meridiem"}),
        ("오늘 2시", {"meridiem"}),
        ("다섯시 십분전", {"meridiem"}),
        ("3~5시", {"meridiem"}),
        # 오전/오후가 정해진 표현은 표시하지 않음
        ("오후 3시", set()),
        ("저녁 7시", set()),
        ("15:30", set()),
        ("3pm", set()),
        ("13시", {"cycle_shifted"}),
        ("정오", {"cycle_shifted"}),
    ],
)
def test_meridiem_is_always_flagged_by_text(text: str, expected: set[str]) -> None:
    assert flags(text) == expected


@pytest.mark.parametrize(
    "now", [datetime(2026, 9, 28, h, m) for h, m in ((0, 10), (8, 5), (14, 30), (23, 50))]
)
def test_meridiem_flag_does_not_depend_on_reference_time(now: datetime) -> None:
    assert "meridiem" in flags("3시", now)
    assert "meridiem" not in flags("오후 3시", now)


def test_ranges_merge_ambiguities() -> None:
    assert flags("6월 3일부터 5일까지") == {"cycle_shifted"}
    assert flags("내일부터 모레까지") == set()


def test_range_end_inherits_explicit_meridiem_from_start() -> None:
    """'오후 3시부터 5시까지'의 5시는 앞의 '오후'가 정해 주므로 모호하지 않다"""
    assert flags("오후 3시부터 5시까지") == set()
    assert flags("내일 오후 3시부터 5시까지") == set()
    assert flags("3시부터 5시까지") == {"meridiem"}


def test_value_is_unchanged_by_detection() -> None:
    assert must("월요일").start.date().isoformat() == "2026-10-05"
    assert must("다음 주말").start.date().isoformat() == "2026-10-10"


def test_to_dict_lists_ambiguities() -> None:
    assert must("다음 주말").to_dict()["ambiguities"] == ["next_weekend"]
    assert must("내일").to_dict()["ambiguities"] == []


def test_non_temporal_is_still_none() -> None:
    assert p("보고 싶어") is None
