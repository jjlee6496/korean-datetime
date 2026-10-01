"""ParseOptions 동작 (기준: 2026-09-28 월요일)"""

from __future__ import annotations

from datetime import datetime

import pytest
from helpers import TODAY, at, d, date_span, days, dt, must, p

from korean_datetime import AmbiguousHour, ParseOptions, parse

MORNING = datetime(2026, 9, 28, 8, 5)


@pytest.mark.parametrize(
    ("policy", "text", "expected"),
    [
        (AmbiguousHour.NEAREST_FUTURE, "9시", at(2026, 9, 28, 9)),
        (AmbiguousHour.NEAREST_FUTURE, "3시", at(2026, 9, 28, 15)),
        (AmbiguousHour.NEAREST_FUTURE, "8시", at(2026, 9, 28, 20)),  # 08:00은 이미 지남
        (AmbiguousHour.PM, "9시", at(2026, 9, 28, 21)),
        (AmbiguousHour.PM, "12시", at(2026, 9, 28, 12)),
        (AmbiguousHour.DAYTIME, "9시", at(2026, 9, 28, 9)),
        (AmbiguousHour.DAYTIME, "6시", at(2026, 9, 28, 18)),
        (AmbiguousHour.AS_IS, "3시", at(2026, 9, 29, 3)),
    ],
)
def test_ambiguous_hour_policy(policy: AmbiguousHour, text: str, expected: datetime) -> None:
    assert dt(text, now=MORNING, ambiguous_hour=policy) == expected


def test_daytime_start_is_configurable() -> None:
    assert dt("내일 9시", daytime_start=10) == at(2026, 9, 29, 21)
    assert dt("내일 9시", daytime_start=9) == at(2026, 9, 29, 9)


def test_current_cycle_keeps_this_cycle() -> None:
    assert must("6월 3일", cycle="current").start.date() == d(2026, 6, 3)
    assert date_span("첫째주", cycle="current") == (d(2026, 8, 31), d(2026, 9, 7))  # 9/1이 든 달력 줄
    assert dt("오전 10시", cycle="current") == at(2026, 9, 28, 10)
    assert must("15일", cycle="current").start.date() == d(2026, 9, 15)
    assert must("금요일", cycle="current").start.date() == days(4)  # 요일은 항상 다가오는 날


def test_compact_dates_are_opt_in() -> None:
    assert p("1015") is None
    assert p("261015") is None
    assert must("1015", compact_dates=True).start.date() == d(2026, 10, 15)
    assert must("261015", compact_dates=True).start.date() == d(2026, 10, 15)
    assert p("1234", compact_dates=True) is None  # 12월 34일은 없음


@pytest.mark.parametrize("bad", [{"daytime_start": 13}, {"daytime_start": -1}])
def test_invalid_options_rejected(bad: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ParseOptions(**bad)  # type: ignore[arg-type]


def test_ambiguous_hour_accepts_string() -> None:
    assert ParseOptions(ambiguous_hour="pm").ambiguous_hour is AmbiguousHour.PM  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ParseOptions(ambiguous_hour="nope")  # type: ignore[arg-type]


def test_now_default_is_current_time() -> None:
    result = parse("지금")
    assert result is not None
    assert abs((result.start - datetime.now()).total_seconds()) < 120
    assert TODAY.year == 2026
