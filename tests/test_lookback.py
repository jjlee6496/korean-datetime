"""기간 값·거슬러 올라가는 기간·분기·연초 이후의 경계 사례 (손으로 계산한 값)

정답셋(temporal_gold.jsonl)이 기준 시각 292개에서 같은 표현을 식으로 검증하고, 여기서는 경계를 명시합니다:
월말, 윤일, 연말·연초, 자정, 분기 경계, 비율·순서 표현.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from korean_datetime import Kind, parse, parse_all


def _range(text: str, now: datetime) -> tuple[object, object]:
    result = parse(text, now=now)
    assert result is not None, text
    assert result.is_range, text
    return result.start, result.end


@pytest.mark.parametrize(
    ("text", "now", "start", "end"),
    [
        # 최근 N = 오늘 포함 N단위: [오늘+1일-N, 내일)
        ("최근 1개월", datetime(2026, 3, 31, 10), date(2026, 3, 1), date(2026, 4, 1)),
        ("최근 1개월", datetime(2026, 3, 1, 10), date(2026, 2, 2), date(2026, 3, 2)),
        ("최근 1년", datetime(2028, 2, 29, 10), date(2027, 3, 1), date(2028, 3, 1)),
        ("최근 2주", datetime(2026, 10, 5, 10), date(2026, 9, 22), date(2026, 10, 6)),
        ("최근 7일", datetime(2027, 1, 3, 10), date(2026, 12, 28), date(2027, 1, 4)),
        # 지난 N = 오늘 전까지 N단위: [오늘-N, 오늘). 월말은 짧은 달에 맞춤
        ("지난 1개월", datetime(2026, 3, 31, 10), date(2026, 2, 28), date(2026, 3, 31)),
        ("지난 3일간", datetime(2026, 1, 2, 10), date(2025, 12, 30), date(2026, 1, 2)),
        # 향후 N = 오늘부터 N단위
        ("향후 1개월", datetime(2026, 1, 31, 10), date(2026, 1, 31), date(2026, 2, 28)),
        # 분기: 연말·연초 경계
        ("최근 4분기", datetime(2026, 1, 1, 0, 5), date(2025, 4, 1), date(2026, 4, 1)),
        ("지난 4분기", datetime(2026, 1, 1, 0, 5), date(2025, 1, 1), date(2026, 1, 1)),
        ("향후 2분기", datetime(2026, 11, 30, 10), date(2026, 10, 1), date(2027, 4, 1)),
        # 연초·월초 당일
        ("연초 이후", datetime(2026, 1, 1, 10), date(2026, 1, 1), date(2026, 1, 2)),
        ("이달 들어", datetime(2026, 10, 1, 10), date(2026, 10, 1), date(2026, 10, 2)),
    ],
)
def test_date_lookbacks(text: str, now: datetime, start: date, end: date) -> None:
    got_start, got_end = _range(text, now)
    assert (got_start, got_end) == (
        datetime.combine(start, datetime.min.time()),
        datetime.combine(end, datetime.min.time()),
    )


def test_time_lookback_crosses_midnight() -> None:
    assert _range("최근 30분", datetime(2026, 10, 1, 0, 10)) == (
        datetime(2026, 9, 30, 23, 40),
        datetime(2026, 10, 1, 0, 10),
    )
    assert _range("향후 2시간", datetime(2026, 12, 31, 23, 0)) == (
        datetime(2026, 12, 31, 23, 0),
        datetime(2027, 1, 1, 1, 0),
    )


def test_quarter_relative_is_a_date_span() -> None:
    last = parse("지난 분기", now=datetime(2026, 1, 15, 10))  # 연초의 지난 분기 = 작년 4분기
    assert last is not None and (last.start, last.end) == (datetime(2025, 10, 1), datetime(2026, 1, 1))
    result = parse("이번 분기 실적", now=datetime(2026, 12, 31, 23, 59))
    assert result is not None
    assert (result.start, result.end, result.kind) == (datetime(2026, 10, 1), datetime(2027, 1, 1), Kind.DATE)
    assert not result.is_range


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("6개월", "P6M"), ("1년간", "P1Y"), ("반년", "P6M"), ("18개월", "P1Y6M"), ("일주일", "P1W"),
        ("열흘간", "P10D"), ("2주 만에", "P2W"), ("90분", "PT1H30M"), ("1시간 30분 동안", "PT1H30M"),
        ("3일간", "P3D"), ("15일 동안", "P15D"), ("5일 수익률", "P5D"), ("120일 이동평균", "P120D"),
    ],
)  # fmt: skip
def test_durations(text: str, iso: str) -> None:
    result = parse(text, now=datetime(2026, 10, 8, 10))
    assert result is not None and result.kind is Kind.DURATION, text
    assert result.duration is not None and result.duration.iso == iso
    assert result.start == result.end == datetime(2026, 10, 8, 10)  # 날짜가 아니라 길이
    assert result.to_dict()["value"] == iso


@pytest.mark.parametrize("text", ["3일마다", "1시간 30분마다", "3일째", "1일 1식", "하루 세 번씩"])
def test_rates_and_ordinals_are_not_durations(text: str) -> None:
    assert all(r.kind is not Kind.DURATION for r in parse_all(text, now=datetime(2026, 10, 8, 10))), text


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("15일에 보자", Kind.DATE),
        ("3시 30분", Kind.TIME),
        ("지난 3일 매출", Kind.DATE),
        ("최근 3일", Kind.DATE),
    ],
)
def test_dates_and_clock_minutes_stay_dates(text: str, kind: Kind) -> None:
    """'15일', '3시 30분'의 30분, '지난 3일'(가장 최근의 3일)은 기간 값이 아님"""
    result = parse(text, now=datetime(2026, 10, 8, 10))
    assert result is not None and result.kind is kind, text
