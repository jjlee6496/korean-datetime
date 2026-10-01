"""달력 계산 유틸"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from .tokens import Offset


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def clamped_date(year: int, month: int, day: int) -> date:
    """존재하지 않는 날(2월 30일)은 그 달 말일로 보정"""
    return date(year, month, min(day, days_in_month(year, month)))


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return clamped_date(index // 12, index % 12 + 1, day.day)


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month_start(day: date) -> date:
    return add_months(month_start(day), 1)


def week_start(day: date) -> date:
    """그 주의 월요일"""
    return day - timedelta(days=day.weekday())


def nth_weekday(first_of_month: date, weekday: int, nth: int) -> date | None:
    """그 달의 nth번째 weekday (nth=-1은 마지막). 없으면 None (다섯째 주 금요일이 없는 달)."""
    if nth > 0:
        first = first_of_month + timedelta(days=(weekday - first_of_month.weekday()) % 7)
        result = first + timedelta(weeks=nth - 1)
    else:
        last_day = next_month_start(first_of_month) - timedelta(days=1)
        result = last_day - timedelta(days=(last_day.weekday() - weekday) % 7)
    return result if result.month == first_of_month.month else None


def calendar_row(first_of_month: date, n: int) -> date | None:
    """
    달력 n번째 줄(월~일)의 월요일. 1일이 든 줄이 1, 말일이 든 줄이 -1.
    줄이 그 달과 겹치지 않으면 None (2026년 10월은 5줄이라 6째 주는 없음).
    """
    last = next_month_start(first_of_month) - timedelta(days=1)
    first_row, last_row = week_start(first_of_month), week_start(last)
    monday = first_row + timedelta(weeks=n - 1) if n > 0 else last_row + timedelta(weeks=n + 1)
    return monday if first_row <= monday <= last_row else None


def next_weekday_after(day: date, weekday: int) -> date:
    """day 이후(당일 제외) 가장 가까운 weekday"""
    return day + timedelta(days=(weekday - day.weekday() - 1) % 7 + 1)


def apply_offset_to_date(day: date, offset: Offset) -> date:
    return add_months(day, offset.months) + timedelta(days=offset.days)


def apply_offset(moment: datetime, offset: Offset) -> datetime:
    shifted = add_months(moment.date(), offset.months)
    return datetime.combine(shifted, moment.timetz()) + timedelta(days=offset.days, seconds=offset.seconds)
