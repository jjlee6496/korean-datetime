"""Frame의 시각 슬롯 → datetime

오전/오후 해석:
- 시간대가 있으면 시간대 규칙 ('저녁 7시' → 19시, '밤 1시' → 다음 날 1시)
- 24시간제/시각 표기면 그대로 ('13시', '05:00', '3pm')
- 그 외 1~12시는 AmbiguousHour 정책
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, tzinfo

from .ambiguity import Ambiguity
from .frame import Frame
from .lexicon import HourMode
from .options import AmbiguousHour, Cycle, ParseOptions
from .tokens import Clock


def to_24h(mode: HourMode, hour: int) -> int:
    """시간대 규칙으로 24시간제 변환. 24 이상은 다음 날."""
    if mode is HourMode.AM:
        return 0 if hour == 12 else hour
    if mode is HourMode.PM:
        return hour + 12 if hour < 12 else hour
    if mode is HourMode.NOON:
        return hour + 12 if 1 <= hour <= 6 else hour
    if mode is HourMode.EVENING:
        return 24 if hour == 12 else (hour + 12 if hour < 12 else hour)
    if hour in (0, 12):
        return 24 if mode is HourMode.LATE_NIGHT or hour == 12 else hour
    if 1 <= hour <= 5:
        return 24 + hour
    return hour + 12 if hour < 12 else hour


def at_hours(day: date, hours: float, tz: tzinfo | None) -> datetime:
    return datetime.combine(day, time(tzinfo=tz)) + timedelta(hours=hours)


def floor_minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def _is_ambiguous(clock: Clock, frame: Frame) -> bool:
    return frame.period is None and not clock.literal and 1 <= clock.hour <= 12


def _policy_hour(hour: int, options: ParseOptions) -> int:
    policy = options.ambiguous_hour
    if policy is AmbiguousHour.AS_IS:
        return hour
    if policy is AmbiguousHour.PM:
        return hour + 12 if hour < 12 else hour
    return hour if hour >= options.daytime_start or hour == 12 else hour + 12


def _candidates(day: date, hour: int, minute: int, tz: tzinfo | None, days: int) -> Iterator[datetime]:
    base = hour % 12
    for offset_day in range(days):
        for add in (0, 12):
            yield at_hours(day + timedelta(days=offset_day), base + add + minute / 60, tz)


Flags = frozenset[Ambiguity]


def resolve_clock(
    frame: Frame,
    clock: Clock,
    day: date | None,
    now: datetime,
    options: ParseOptions,
    shift: timedelta = timedelta(0),
) -> tuple[datetime, Flags]:
    """
    (기준이 되는 시각, 모호성). day가 None이면 날짜 미지정 (기준일에서 추론, 필요하면 다음 날).
    shift는 뒤에 붙은 오프셋('17시 5분 전'의 -5분): 미래 여부는 오프셋을 적용한 시각으로 판단합니다.
    """
    moment, flags = _resolve_clock(frame, clock, day, now, options, shift)
    return moment, flags | _meridiem(clock, frame)


def _meridiem(clock: Clock, frame: Frame) -> Flags:
    """오전/오후가 없는 1~12시: 정책(값)과 상관없이 문장만 보고 표시"""
    if not _is_ambiguous(clock, frame):
        return frozenset()
    return frozenset({Ambiguity.NOON_OR_MIDNIGHT if clock.hour == 12 else Ambiguity.MERIDIEM})


def _resolve_clock(
    frame: Frame, clock: Clock, day: date | None, now: datetime, options: ParseOptions, shift: timedelta
) -> tuple[datetime, Flags]:
    tz = now.tzinfo
    minute = frame.minute if frame.minute is not None else (clock.minute or 0)
    reference = floor_minute(now)
    target_day = day or now.date()

    if _is_ambiguous(clock, frame) and options.ambiguous_hour is AmbiguousHour.NEAREST_FUTURE:
        if day is None:
            moment = next(
                c for c in _candidates(target_day, clock.hour, minute, tz, 2) if c + shift >= reference
            )
            return moment, _shifted(moment.date() > target_day)
        if day == now.date():
            upcoming = [c for c in _candidates(day, clock.hour, minute, tz, 1) if c + shift >= reference]
            if upcoming:
                return upcoming[0], frozenset()
        return at_hours(target_day, _policy_hour(clock.hour, options) + minute / 60, tz), frozenset()

    if frame.period is not None:
        hour = to_24h(frame.period.mode, clock.hour)
    elif _is_ambiguous(clock, frame):
        hour = _policy_hour(clock.hour, options)
    else:
        hour = clock.hour
    moment = at_hours(target_day, hour + minute / 60, tz)
    rolled = day is None and options.cycle is Cycle.FUTURE and moment + shift < reference
    flags = _shifted(rolled) | _attribution(hour)
    return (moment + timedelta(days=1) if rolled else moment), flags


def resolve_period(
    start_hour: float, end_hour: float, day: date | None, now: datetime, options: ParseOptions
) -> tuple[datetime, datetime, Flags]:
    """시간대('저녁' = 18~21시)의 구간. day가 None이면 기준일, 이미 끝났으면(cycle=FUTURE) 다음 날"""
    target_day = day or now.date()
    start = at_hours(target_day, start_hour, now.tzinfo)
    end = at_hours(target_day, end_hour, now.tzinfo)
    flags = _attribution(start_hour)
    if day is None and options.cycle is Cycle.FUTURE and end <= now:
        return start + timedelta(days=1), end + timedelta(days=1), flags | _shifted(True)
    return start, end, flags


def _shifted(condition: bool) -> Flags:
    return frozenset({Ambiguity.CYCLE_SHIFTED}) if condition else frozenset()


def _attribution(hour: float) -> Flags:
    """24시 이상(자정, 밤 1시, 심야)은 어느 날에 속하는지 모호"""
    return frozenset({Ambiguity.DAY_ATTRIBUTION}) if hour >= 24 else frozenset()
