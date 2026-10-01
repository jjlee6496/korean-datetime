"""기념일/공휴일 데이터 외부 주입 (기준: 2026-09-28)"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date

import pytest
from helpers import NOW, d

from ko_normalizer import (
    BuiltinHolidays,
    ChainedHolidays,
    DateTableHolidays,
    HolidayCalendar,
    ParseOptions,
    parse,
)


def _date(text: str, calendar: HolidayCalendar) -> date | None:
    result = parse(text, now=NOW, options=ParseOptions(holidays=calendar))
    return result.start.date() if result else None


class FakeHolidaysPackage(Mapping[date, str]):
    """`holidays.KR()`처럼 날짜 → 이름 매핑을 흉내 낸 외부 데이터"""

    def __init__(self, data: dict[date, str]) -> None:
        self._data = data

    def __getitem__(self, key: date) -> str:
        return self._data[key]

    def __iter__(self) -> Iterator[date]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def test_table_from_external_mapping() -> None:
    external = FakeHolidaysPackage({d(2026, 11, 20): "창립기념일", d(2027, 11, 19): "창립기념일"})
    table = DateTableHolidays(external)
    assert _date("창립기념일", table) == d(2026, 11, 20)
    assert _date("내년 창립기념일", table) == d(2027, 11, 19)
    assert _date("2028년 창립기념일", table) is None  # 데이터에 없는 해


def test_table_accepts_pairs_and_aliases() -> None:
    table = DateTableHolidays([(d(2026, 10, 15), "워크숍")], aliases={"워크숍": ["워크샵", "전사 워크숍"]})
    assert _date("전사 워크숍", table) == d(2026, 10, 15)
    assert _date("워크샵", table) == d(2026, 10, 15)


def test_consecutive_days_become_one_span() -> None:
    table = DateTableHolidays(
        {d(2026, 12, 29): "연말 휴무", d(2026, 12, 30): "연말 휴무", d(2026, 12, 31): "연말 휴무"}
    )
    result = parse("연말 휴무", now=NOW, options=ParseOptions(holidays=table))
    assert result is not None
    assert (result.start.date(), result.end.date()) == (d(2026, 12, 29), d(2027, 1, 1))


def test_chained_prefers_injected_data_then_builtin() -> None:
    override = DateTableHolidays({d(2026, 10, 2): "추석"})  # 가짜 날짜로 덮어쓰기
    calendar = ChainedHolidays(override, BuiltinHolidays())
    assert _date("올해 추석", calendar) == d(2026, 10, 2)
    assert _date("크리스마스", calendar) == d(2026, 12, 25)  # 주입 데이터에 없으면 내장


def test_default_is_builtin() -> None:
    result = parse("크리스마스", now=NOW)
    assert result is not None and result.start.date() == d(2026, 12, 25)
    assert _date("창립기념일", BuiltinHolidays()) is None


def test_protocol_and_validation() -> None:
    assert isinstance(BuiltinHolidays(), HolidayCalendar)
    assert isinstance(DateTableHolidays({}), HolidayCalendar)
    with pytest.raises(TypeError):
        ParseOptions(holidays="KR")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DateTableHolidays({"2026-10-01": "x"})  # type: ignore[dict-item]


def test_semicolon_joined_names_are_split() -> None:
    """python-holidays는 같은 날 기념일을 '개천절; 추석'처럼 이어 붙인다"""
    table = DateTableHolidays({d(2028, 10, 3): "개천절; 추석", d(2028, 10, 4): "추석 다음날"})
    assert _date("2028년 추석", table) == d(2028, 10, 3)
    assert _date("2028년 개천절", table) == d(2028, 10, 3)
