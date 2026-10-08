"""영업일 달력 — 외부 데이터 주입 지점

거래일·영업일은 기관마다 다르고(거래소 휴장일, 회사 휴무일) 정책으로 정해져 라이브러리가 알 수 없습니다.
쓰는 쪽이 달력을 넣으면 다음이 계산됩니다:
- "3거래일 전", "2영업일 후", "전 거래일", "다음 영업일": 영업일만 세어 이동
- ParseOptions(business_week=True)의 "이번 주": 그 주의 첫 영업일 ~ 마지막 영업일

    from korean_datetime import ParseOptions, WeekdayCalendar, parse

    krx = WeekdayCalendar(holidays=[date(2026, 10, 9), ...])   # 월~금 중 휴장일 제외
    parse("3거래일 전 종가", options=ParseOptions(business_calendar=krx))

달력을 넣지 않으면 영업일 표현은 인식하지 않습니다(주말만 빼고 세면 휴일이 낀 날 틀린 값이 되므로).
직접 구현하려면 BusinessCalendar 프로토콜(is_business_day)만 만족하면 됩니다. ParseOptions에 넣으므로
해시 가능해야 합니다(frozen dataclass 권장).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

_MAX_SCAN_DAYS = 366  # 영업일을 찾을 때 최대로 넘겨 볼 날 수 (달력이 전부 휴일이어도 멈추도록)


@runtime_checkable
class BusinessCalendar(Protocol):
    def is_business_day(self, day: date) -> bool:
        """그 날이 영업일(거래일)인지"""
        ...


@dataclass(frozen=True)
class WeekdayCalendar:
    """월~금 중 holidays를 뺀 날이 영업일. 휴장일·공휴일 목록은 쓰는 쪽이 넣음"""

    holidays: frozenset[date] = field(default_factory=frozenset)

    def __init__(self, holidays: Iterable[date] = ()) -> None:
        days = frozenset(holidays)
        if not all(isinstance(day, date) for day in days):
            raise TypeError("holidays에는 date만 넣을 수 있습니다")
        object.__setattr__(self, "holidays", days)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays


def step_business_days(calendar: BusinessCalendar, start: date, steps: int) -> date | None:
    """start에서 영업일만 세어 steps번 이동 (start 자신은 세지 않음, 음수면 과거). 찾지 못하면 None"""
    day, remaining, direction = start, abs(steps), 1 if steps > 0 else -1
    for _ in range(_MAX_SCAN_DAYS * max(1, remaining)):
        if remaining == 0:
            return day
        day += timedelta(days=direction)
        if calendar.is_business_day(day):
            remaining -= 1
    return day if remaining == 0 else None


def business_days_between(calendar: BusinessCalendar, start: date, end: date) -> list[date]:
    """[start, end) 안의 영업일"""
    return [
        start + timedelta(days=i)
        for i in range((end - start).days)
        if calendar.is_business_day(start + timedelta(days=i))
    ]
