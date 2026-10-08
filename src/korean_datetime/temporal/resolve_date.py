"""Frame의 날짜 슬롯 → 날짜 구간 [start, end)

연/월이 생략된 표현은 '주기'가 정해지지 않은 것으로 보고 ParseOptions.cycle에 따라 주기를 고릅니다.
기본(FUTURE)은 이미 끝난 구간을 다음 주기로 넘깁니다 ('6월 3일'@9월 → 내년, '15일'@20일 → 다음 달).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .ambiguity import Ambiguity
from .calendar_math import (
    add_months,
    apply_offset_to_date,
    calendar_row,
    days_in_month,
    month_start,
    next_month_start,
    next_weekday_after,
    nth_weekday,
    week_start,
)
from .frame import Frame
from .model import Grain
from .options import Cycle, ParseOptions, holiday_calendar
from .tokens import HolidayRef, MonthPart


@dataclass(frozen=True, slots=True)
class DateSpan:
    start: date
    end: date
    grain: Grain = Grain.DAY
    ambiguities: frozenset[Ambiguity] = frozenset()

    def flagged(self, flag: Ambiguity) -> DateSpan:
        return replace(self, ambiguities=self.ambiguities | {flag})


def _day(day: date) -> DateSpan:
    return DateSpan(day, day + timedelta(days=1))


Compute = Callable[[int], DateSpan | None]
_MAX_CYCLES = 4  # 2월 29일이 다시 오는 최대 주기


def _choose_cycle(
    compute: Compute, explicit: bool, after: date, options: ParseOptions, today: date | None = None
) -> DateSpan | None:
    """after: 이 날짜까지 끝나는 주기는 지난 것 (FUTURE). today: PAST·NEAREST의 기준일 (기본 after)"""
    span = compute(0)
    if explicit or options.cycle is Cycle.CURRENT:
        return span
    if options.cycle is Cycle.PAST:
        return _latest_cycle(compute, today or after)
    if options.cycle is Cycle.NEAREST:
        return _nearest_cycle(compute, today or after)
    if span is not None and span.end > after:
        return span
    # 이미 끝났으면 다음 주기. 이번 주기에 없으면('다섯째주 금요일', '2월 29일') 있는 주기까지
    for k in range(1, _MAX_CYCLES + 1):
        shifted = compute(k)
        if shifted is not None:
            return shifted.flagged(Ambiguity.CYCLE_SHIFTED)
    return None


def _first_existing(compute: Compute, ks: range) -> tuple[int, DateSpan] | None:
    for k in ks:
        span = compute(k)
        if span is not None:
            return k, span
    return None


def _shifted_if(k: int, span: DateSpan) -> DateSpan:
    return span.flagged(Ambiguity.CYCLE_SHIFTED) if k else span


def _latest_cycle(compute: Compute, today: date) -> DateSpan | None:
    """오늘이나 그 전에 시작하는 가장 최근 주기"""
    for k in range(0, -_MAX_CYCLES - 1, -1):
        span = compute(k)
        if span is not None and span.start <= today:
            return _shifted_if(k, span)
    return None


def _distance(span: DateSpan, today: date) -> int:
    if span.start <= today < span.end:
        return 0
    return (span.start - today).days if span.start > today else (today - span.end).days + 1


def _nearest_cycle(compute: Compute, today: date) -> DateSpan | None:
    """이번·이전·다음 주기 중 오늘에서 가장 가까운 것 (같으면 미래 쪽)"""
    candidates = [
        hit
        for ks in (range(0, 1), range(-1, -_MAX_CYCLES - 1, -1), range(1, _MAX_CYCLES + 1))
        if (hit := _first_existing(compute, ks)) is not None
    ]
    if not candidates:
        return None
    k, span = min(candidates, key=lambda hit: (_distance(hit[1], today), -hit[0]))
    return _shifted_if(k, span)


def has_date(frame: Frame) -> bool:
    return any(
        value is not None
        for value in (
            frame.date_offset,
            frame.day_rel,
            frame.week_rel,
            frame.holiday,
            frame.year,
            frame.year_rel,
            frame.year_part,
            frame.month,
            frame.month_rel,
            frame.day,
            frame.week_nth,
            frame.nth_weekday,
            frame.past_span,
            frame.month_part,
            frame.weekday,
            frame.week_part,
        )
    )


def resolve_date(
    frame: Frame, today: date, options: ParseOptions, ended_before: date | None = None
) -> DateSpan | None:
    """ended_before: 이 날짜까지 끝나는 주기는 지난 것으로 봄 (기본은 오늘. 시각이 이미 지났으면 내일)"""
    after = ended_before or today
    if frame.modifier == 1 and options.cycle is not Cycle.FUTURE:  # '오는 15일', '다가오는 추석'
        options = replace(options, cycle=Cycle.FUTURE)
    if frame.past_span is not None:  # '지난 3일간' = [3일 전, 오늘)
        return DateSpan(apply_offset_to_date(today, frame.past_span.scaled(-1)), today)
    if frame.date_offset is not None:
        return _day(apply_offset_to_date(today, frame.date_offset))
    if frame.day_rel is not None:
        return _day(today + timedelta(days=frame.day_rel))
    if frame.week_rel is not None:
        return _within_week(week_start(today) + timedelta(weeks=frame.week_rel), frame)
    if frame.holiday is not None:
        return _holiday(frame, frame.holiday, today, options, after)
    if (
        frame.has_month
        or frame.day is not None
        or frame.week_nth is not None
        or frame.nth_weekday is not None
        or frame.month_part is not None
    ):
        return _month_based(frame, today, options, after)
    if frame.has_year or frame.year_part is not None:
        return _year_based(frame, today, options, after)
    if frame.weekday is not None and frame.modifier is None and options.cycle in (Cycle.PAST, Cycle.NEAREST):
        this_week = lambda k: _day(week_start(today) + timedelta(weeks=k, days=frame.weekday))  # noqa: E731
        return _choose_cycle(this_week, False, today, options, today)
    if frame.weekday is not None:
        span = _day(_weekday_with_modifier(today, frame.weekday, frame.modifier))
        same_weekday = frame.modifier in (None, 1) and today.weekday() == frame.weekday
        return span.flagged(Ambiguity.SAME_WEEKDAY) if same_weekday else span
    if frame.week_part is not None:
        shifted = lambda k: _within_week(week_start(today) + timedelta(weeks=k), frame)  # noqa: E731
        return _choose_cycle(shifted, False, after, options, today)
    return None


def _weekday_with_modifier(today: date, weekday: int, modifier: int | None) -> date:
    """지난 금요일: 오늘 이전 가장 가까운 금요일 / 이번 금요일: 이번 주 금요일 / 그 외: 오늘 이후"""
    if modifier == -1:
        return today - timedelta(days=(today.weekday() - weekday - 1) % 7 + 1)
    if modifier == 0:
        return week_start(today) + timedelta(days=weekday)
    return next_weekday_after(today, weekday)


def _base_year(explicit_year: int | None, today: date) -> int:
    return explicit_year if explicit_year is not None else today.year


def _explicit_year(frame: Frame, today: date) -> int | None:
    if frame.year is not None:
        return frame.year
    return today.year + frame.year_rel if frame.year_rel is not None else None


def _within_week(monday: date, frame: Frame) -> DateSpan:
    if frame.weekday is not None:
        return _day(monday + timedelta(days=frame.weekday))
    if frame.week_part == "weekend":
        return DateSpan(monday + timedelta(days=5), monday + timedelta(days=7))
    if frame.week_part == "weekdays":
        return DateSpan(monday, monday + timedelta(days=5))
    if frame.week_part == "early":
        return DateSpan(monday, monday + timedelta(days=2))
    return DateSpan(monday, monday + timedelta(days=7), Grain.WEEK)


def _holiday(
    frame: Frame, ref: HolidayRef, today: date, options: ParseOptions, after: date
) -> DateSpan | None:
    explicit_year = _explicit_year(frame, today)

    calendar = holiday_calendar(options)

    def compute(k: int) -> DateSpan | None:
        found = calendar.span(ref.key, _base_year(explicit_year, today) + k, as_holidays=ref.span)
        return DateSpan(*found) if found else None

    if frame.modifier == -1 and explicit_year is None:  # '지난 추석': 오늘 이전에 시작한 가장 최근
        this_year = compute(0)
        return this_year if this_year is not None and this_year.start < today else compute(-1)
    return _choose_cycle(compute, explicit_year is not None, after, options, today)


def _month_based(frame: Frame, today: date, options: ParseOptions, after: date) -> DateSpan | None:
    explicit_year = _explicit_year(frame, today)

    def compute(k: int) -> DateSpan | None:
        if frame.month_rel is not None:
            first = add_months(month_start(today), frame.month_rel)
        elif frame.month is not None:
            first = date(_base_year(explicit_year, today) + k, frame.month, 1)
        else:
            first = add_months(month_start(today), k)
        return _within_month(first, frame, today)

    explicit = frame.month_rel is not None or (frame.month is not None and explicit_year is not None)
    if frame.modifier == -1 and not explicit:  # '지난 3일': 오늘 이전 가장 최근
        return _with_past_shift(compute, today)
    return _choose_cycle(compute, explicit, after, options, today)


def _with_past_shift(compute: Compute, today: date) -> DateSpan | None:
    """오늘 이전에 시작하는 가장 최근 주기 (없는 날짜면 더 이전 주기까지)"""
    for k in range(0, -_MAX_CYCLES - 1, -1):
        span = compute(k)
        if span is not None and span.start < today:
            return span
    return None


def _within_month(first: date, frame: Frame, today: date) -> DateSpan | None:
    if frame.day is not None:
        if frame.day > days_in_month(first.year, first.month):
            return None  # 없는 날짜('2월 30일', '9월 31일')는 인식하지 않음
        return _day(first.replace(day=frame.day))
    if frame.week_nth is not None:
        return _calendar_week(first, frame.week_nth, frame, today)
    if frame.nth_weekday is not None:
        return _nth_weekday(first, frame.nth_weekday, frame)
    if frame.month_part is not None:
        return _month_part(first, frame.month_part)
    if frame.weekday is not None:
        return _day(first + timedelta(days=(frame.weekday - first.weekday()) % 7))
    return DateSpan(first, next_month_start(first), Grain.MONTH)


def _calendar_week(first: date, week_nth: int, frame: Frame, today: date) -> DateSpan | None:
    """'셋째 주 토요일', '마지막 주': 달력 줄(1일이 든 월~일 줄이 1주) 기준. 앞뒤 달 날짜일 수 있음."""
    monday = calendar_row(first, week_nth)
    if monday is None:
        return None
    if frame.weekday is not None:
        day = monday + timedelta(days=frame.weekday)
        spill = (day.year, day.month) != (first.year, first.month)
        if day < first and day < today:  # 첫 줄의 앞 달 칸이 이미 지났으면 다음 주 ('다음달 첫째 주 월요일')
            day += timedelta(days=7)
        return _day(day).flagged(Ambiguity.CALENDAR_ROW_SPILL) if spill else _day(day)
    if frame.week_part == "weekend":
        return DateSpan(monday + timedelta(days=5), monday + timedelta(days=7))
    if frame.week_part == "weekdays":
        return DateSpan(monday, monday + timedelta(days=5))
    return DateSpan(monday, monday + timedelta(days=7), Grain.WEEK)


def _nth_weekday(first: date, nth: int, frame: Frame) -> DateSpan | None:
    """'셋째 토요일', '마지막 금요일', '셋째 주말': 그 달 안의 N번째 요일 (주말은 N번째 토요일부터 이틀)"""
    if frame.week_part == "weekend":
        saturday = nth_weekday(first, 5, nth)
        return None if saturday is None else DateSpan(saturday, saturday + timedelta(days=2))
    if frame.weekday is None:
        return None
    day = nth_weekday(first, frame.weekday, nth)
    return None if day is None else _day(day)


def _month_part(first: date, part: MonthPart) -> DateSpan:
    last = days_in_month(first.year, first.month)
    ranges = {
        "early": (1, 11),
        "mid": (11, 21),
        "late": (21, last + 1),
        "first_day": (1, 2),
        "last_day": (last, last + 1),
    }
    begin, end = ranges[part.name]
    return DateSpan(first.replace(day=begin), first + timedelta(days=end - 1))


def _year_based(frame: Frame, today: date, options: ParseOptions, after: date) -> DateSpan | None:
    explicit_year = _explicit_year(frame, today)

    def compute(k: int) -> DateSpan:
        return _year_part(date(_base_year(explicit_year, today) + k, 1, 1), frame.year_part)

    return _choose_cycle(compute, explicit_year is not None, after, options, today)


def _year_part(jan1: date, part: str | None) -> DateSpan:
    if part is None:
        return DateSpan(jan1, jan1.replace(year=jan1.year + 1), Grain.YEAR)
    if part in ("h1", "h2"):
        start = jan1 if part == "h1" else jan1.replace(month=7)
        return DateSpan(start, add_months(start, 6), Grain.HALF_YEAR)
    if part.startswith("q"):
        start = add_months(jan1, (int(part[1]) - 1) * 3)
        return DateSpan(start, add_months(start, 3), Grain.QUARTER)
    if part in ("first_day", "last_day"):
        day = jan1 if part == "first_day" else jan1.replace(month=12, day=31)
        return _day(day)
    start = jan1 if part == "early" else jan1.replace(month=12)
    return DateSpan(start, add_months(start, 1), Grain.MONTH)
