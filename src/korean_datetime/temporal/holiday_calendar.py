"""기념일/공휴일 달력 — 외부 데이터 주입 지점

공휴일(대체공휴일, 임시공휴일 등)은 정책으로 정해져 계산할 수 없으므로, 필요한 데이터를 밖에서 넣습니다.

    import holidays                                  # 예: python-holidays (이 라이브러리의 의존성 아님)
    from korean_datetime import ParseOptions, DateTableHolidays, ChainedHolidays, BuiltinHolidays, parse

    kr = DateTableHolidays(holidays.KR(years=range(2025, 2031), language="ko"))
    options = ParseOptions(holidays=ChainedHolidays(kr, BuiltinHolidays()))  # 주입 데이터 우선, 없으면 내장
    parse("추석 대체 휴일", options=options)

직접 구현하려면 HolidayCalendar 프로토콜(names, span_names, span)만 만족하면 됩니다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

from .holidays import holiday_names, holiday_span


@runtime_checkable
class HolidayCalendar(Protocol):
    def names(self) -> Mapping[str, str]:
        """텍스트 표현 → key ('추석' → 'chuseok')"""
        ...

    def span_names(self) -> Mapping[str, str]:
        """'연휴' 표현 → key ('추석 연휴' → 'chuseok'). 없으면 빈 매핑."""
        ...

    def span(self, key: str, year: int, *, as_holidays: bool) -> tuple[date, date] | None:
        """year년의 [시작, 끝) 날짜. 모르는 key나 데이터가 없는 해는 None."""
        ...


class BuiltinHolidays:
    """내장 기념일 (data/holidays.json, 음력은 천문 계산)"""

    def names(self) -> Mapping[str, str]:
        return holiday_names()[0]

    def span_names(self) -> Mapping[str, str]:
        return holiday_names()[1]

    def span(self, key: str, year: int, *, as_holidays: bool) -> tuple[date, date] | None:
        try:
            return holiday_span(key, year, as_holidays=as_holidays)
        except (KeyError, ValueError):  # 모르는 key, 음력 지원 범위 밖
            return None


class DateTableHolidays:
    """
    (날짜, 이름) 데이터로 만드는 달력. `{date: name}` 매핑이나 `(date, name)` 쌍 목록을 받습니다.
    같은 이름이 연속된 날짜에 있으면 하나의 기간으로 봅니다 ('연말 휴무' 12/29~12/31).
    한 날짜에 이름이 여럿이면 ';'로 이어 붙여도 됩니다 ('개천절; 추석', python-holidays 형식).
    """

    def __init__(
        self,
        entries: Mapping[date, str] | Iterable[tuple[date, str]],
        aliases: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        pairs = entries.items() if isinstance(entries, Mapping) else entries
        by_name: dict[str, list[date]] = {}
        for day, joined in pairs:
            if not isinstance(day, date) or not isinstance(joined, str) or not joined.strip():
                raise TypeError(f"(date, 이름) 형식이어야 합니다: {(day, joined)!r}")
            for name in joined.split(_NAME_SEPARATOR):  # '개천절; 추석'처럼 이어 붙인 이름
                if name.strip():
                    by_name.setdefault(name.strip(), []).append(day)
        self._dates = {name: tuple(sorted(set(days))) for name, days in by_name.items()}
        self._names = {name: name for name in self._dates}
        for name, extra in (aliases or {}).items():
            self._names.update({alias: name for alias in extra})

    def names(self) -> Mapping[str, str]:
        return self._names

    def span_names(self) -> Mapping[str, str]:
        return {}

    def span(self, key: str, year: int, *, as_holidays: bool) -> tuple[date, date] | None:
        days = [day for day in self._dates.get(key, ()) if day.year == year]
        if not days:
            return None
        end = days[0]
        for day in days[1:]:
            if day != end + timedelta(days=1):
                break
            end = day
        return days[0], end + timedelta(days=1)


class ChainedHolidays:
    """
    여러 달력을 순서대로 조회합니다.
    같은 이름이면 앞 달력의 데이터가 우선이고, 그해 데이터가 없으면 다음 달력을 봅니다.
    """

    def __init__(self, *calendars: HolidayCalendar) -> None:
        if not calendars or not all(isinstance(c, HolidayCalendar) for c in calendars):
            raise TypeError("HolidayCalendar를 하나 이상 넘겨야 합니다")
        self._calendars = calendars
        self._candidates: list[tuple[tuple[int, str], ...]] = []
        self._names = self._index(lambda c: c.names())
        self._span_names = self._index(lambda c: c.span_names())

    def _index(self, pick: Callable[[HolidayCalendar], Mapping[str, str]]) -> dict[str, str]:
        merged: dict[str, list[tuple[int, str]]] = {}
        for i, calendar in enumerate(self._calendars):
            for name, key in pick(calendar).items():
                merged.setdefault(name, []).append((i, key))
        index: dict[str, str] = {}
        for name, candidates in merged.items():
            index[name] = f"chain:{len(self._candidates)}"
            self._candidates.append(tuple(candidates))
        return index

    def names(self) -> Mapping[str, str]:
        return self._names

    def span_names(self) -> Mapping[str, str]:
        return self._span_names

    def span(self, key: str, year: int, *, as_holidays: bool) -> tuple[date, date] | None:
        if not key.startswith("chain:"):
            return None
        for i, inner_key in self._candidates[int(key.removeprefix("chain:"))]:
            found = self._calendars[i].span(inner_key, year, as_holidays=as_holidays)
            if found is not None:
                return found
        return None


_NAME_SEPARATOR = ";"

BUILTIN_HOLIDAYS = BuiltinHolidays()
