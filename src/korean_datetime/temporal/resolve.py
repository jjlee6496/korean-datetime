"""Frame → TemporalExpression"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta

from .ambiguity import Ambiguity, ordered
from .calendar_math import add_months, apply_offset, week_start
from .frame import Frame
from .model import Direction, Grain, Kind, TemporalExpression
from .options import ParseOptions
from .resolve_date import DateSpan, has_date, resolve_date
from .resolve_time import floor_minute, resolve_clock, resolve_period
from .tokens import Offset

_GRAIN_STEP = {
    Grain.SECOND: timedelta(seconds=1),
    Grain.MINUTE: timedelta(minutes=1),
    Grain.HOUR: timedelta(hours=1),
}


def _offset_grain(offset: Offset) -> Grain:
    if offset.seconds % 60:
        return Grain.SECOND
    return Grain.MINUTE if offset.seconds else Grain.DAY


def _instant(text: str, frame: Frame, start: datetime, grain: Grain, kind: Kind) -> TemporalExpression:
    return TemporalExpression(text, (frame.start, frame.end), kind, grain, start, start + _GRAIN_STEP[grain])


def resolve(frame: Frame, text: str, now: datetime, options: ParseOptions) -> TemporalExpression | None:
    """해석할 수 없으면 None (존재하지 않는 '다섯째 주 금요일' 등)

    '다가오는', '매월'처럼 다음에 올 때를 가리키면('다가오는 31일 오전 9시', '매달 말일 자정 10분 전')
    오늘 날짜라도 시각이 이미 지났으면 다음 주기로 넘깁니다. 수식어가 없으면 날짜 단위로만 판단
    ('10월 15일 저녁 7시'@10월 15일 밤 → 오늘 저녁 7시, 내년으로 넘기지 않음).
    """
    result = _resolve(frame, text, now, options, None)
    if result is None or not _time_passed(frame, result, now, options):
        return result
    retried = _resolve(frame, text, now, options, now.date() + timedelta(days=1))
    return retried if retried is not None and retried.start > result.start else result


def _same_position(span: DateSpan, today: date) -> date:
    """해·달·주 구간에서 오늘과 같은 위치의 날 ('작년' → 1년 전 오늘, '다음 주' → 7일 뒤). 하루면 그날."""
    if span.grain is Grain.YEAR:
        return add_months(today, (span.start.year - today.year) * 12)
    if span.grain is Grain.MONTH:
        return add_months(today, (span.start.year - today.year) * 12 + span.start.month - today.month)
    if span.grain is Grain.WEEK:
        return today + (span.start - week_start(today))
    return span.start


def _vague(frame: Frame, direction: str, text: str, now: datetime) -> TemporalExpression:
    """막연한 때: 값은 기준일 하루, 뜻은 direction (호출하는 쪽이 kind=VAGUE를 보고 정확한 날짜와 구별)"""
    start = datetime.combine(now.date(), time(tzinfo=now.tzinfo))
    end = start + timedelta(days=1)
    span = (frame.start, frame.end)
    return TemporalExpression(text, span, Kind.VAGUE, Grain.DAY, start, end, direction=Direction(direction))


def _shift_day(span: DateSpan, shift: int) -> DateSpan:
    """구간의 전날(첫날 하루 전) / 다음 날(끝난 다음 날): '주말 전날' = 금요일"""
    day = span.start - timedelta(days=1) if shift < 0 else span.end
    return DateSpan(day, day + timedelta(days=1), ambiguities=span.ambiguities)


def _time_passed(frame: Frame, result: TemporalExpression, now: datetime, options: ParseOptions) -> bool:
    upcoming = frame.modifier == 1
    if not upcoming or not has_date(frame) or result.kind is Kind.DATE:
        return False
    if frame.clock is not None:
        return result.start < floor_minute(now)
    return frame.period is not None and result.end <= now


def _resolve(
    frame: Frame, text: str, now: datetime, options: ParseOptions, ended_before: date | None
) -> TemporalExpression | None:
    span_text = text[frame.start : frame.end]
    if frame.vague is not None:
        return _vague(frame, frame.vague, span_text, now)
    if frame.now:
        return _instant(span_text, frame, floor_minute(now), Grain.MINUTE, Kind.DATETIME)
    if frame.time_offset is not None:
        grain = _offset_grain(frame.time_offset)
        moment = apply_offset(now, frame.time_offset).replace(microsecond=0)
        start = moment if grain is Grain.SECOND else floor_minute(moment)
        return _instant(span_text, frame, start, grain, Kind.DATETIME)

    date_span = resolve_date(frame, now.date(), options, ended_before) if has_date(frame) else None
    if has_date(frame) and date_span is None:
        return None
    if frame.day_shift is not None:
        if date_span is None:
            return None
        date_span = _shift_day(date_span, frame.day_shift)
    if frame.same_time:  # '내일 이 시각': 그날의 지금 시각 / '작년 이맘때': 1년 전 오늘
        day = _same_position(date_span, now.date()) if date_span else now.date()
        if frame.same_time == "day":
            start = datetime.combine(day, time(tzinfo=now.tzinfo))
            return TemporalExpression(
                span_text, (frame.start, frame.end), Kind.DATE, Grain.DAY, start, start + timedelta(days=1)
            )
        moment = datetime.combine(day, floor_minute(now).timetz())
        return _instant(span_text, frame, moment, Grain.MINUTE, Kind.DATETIME)
    combined = _combine(frame, span_text, date_span, now, options)
    if combined is None:
        return None
    result, time_flags = combined
    flags = time_flags | _date_flags(frame, span_text, date_span)
    result = replace(
        result, ambiguities=ordered(flags), is_range=result.is_range or frame.past_span is not None
    )
    return _apply_anchor(result, frame.anchored_offset) if frame.anchored_offset else result


_NEXT_WEEKEND = re.compile(r"(?:다음|담)\s*주말")


def _date_flags(frame: Frame, text: str, date_span: DateSpan | None) -> frozenset[Ambiguity]:
    flags = set(date_span.ambiguities) if date_span else set()
    if date_span and frame.has_time and (date_span.end - date_span.start).days > 1:
        flags.add(Ambiguity.MULTI_DAY_TIME)  # '이번 주말 오후 3시' → 첫날로 정함
    if frame.week_rel == 1 and frame.week_part == "weekend" and _NEXT_WEEKEND.search(text):
        flags.add(Ambiguity.NEXT_WEEKEND)  # '다음 주 주말'이 아닌 '다음 주말'
    if frame.two_digit_year:
        flags.add(Ambiguity.TWO_DIGIT_YEAR)
    return frozenset(flags)


def _time_shift(frame: Frame) -> timedelta:
    """'17시 5분 전'처럼 시각 뒤에 붙은 시·분 단위 오프셋"""
    offset = frame.anchored_offset
    if offset is None or offset.months or offset.days:
        return timedelta(0)
    return timedelta(seconds=offset.seconds)


def _modifier_day(frame: Frame, now: datetime) -> date | None:
    """'지난 저녁' → 어제, '이번 저녁' → 오늘. 수식어가 없으면 None(날짜 미지정)."""
    if frame.modifier == -1:
        return now.date() - timedelta(days=1)
    return now.date() if frame.modifier == 0 else None


def _combine(
    frame: Frame, text: str, date_span: DateSpan | None, now: datetime, options: ParseOptions
) -> tuple[TemporalExpression, frozenset[Ambiguity]] | None:
    day = date_span.start if date_span else _modifier_day(frame, now)
    kind = Kind.DATETIME if date_span else Kind.TIME
    if frame.clock is not None:
        start, flags = resolve_clock(frame, frame.clock, day, now, options, _time_shift(frame))
        precise = frame.minute is not None or frame.clock.minute is not None
        return _instant(text, frame, start, Grain.MINUTE if precise else Grain.HOUR, kind), flags
    period = frame.period
    if period is not None and period.start is not None and period.end is not None:
        start, end, flags = resolve_period(period.start, period.end, day, now, options)
        return TemporalExpression(text, (frame.start, frame.end), kind, Grain.HOUR, start, end), flags
    if date_span is None:
        return None
    tz = now.tzinfo
    start = datetime(date_span.start.year, date_span.start.month, date_span.start.day, tzinfo=tz)
    end = datetime(date_span.end.year, date_span.end.month, date_span.end.day, tzinfo=tz)
    expression = TemporalExpression(text, (frame.start, frame.end), Kind.DATE, date_span.grain, start, end)
    return expression, frozenset()


def _apply_anchor(result: TemporalExpression, offset: Offset) -> TemporalExpression:
    """'17시 5분 전', '크리스마스 3일 전'처럼 앞 표현 기준 오프셋"""
    start = apply_offset(result.start, offset)
    if result.kind is Kind.DATE and offset.is_date_grain:
        # 시작만 옮기고 길이는 유지 (끝에 따로 말일 보정이 적용되면 1/30+1개월이 빈 구간이 됨)
        return replace(result, start=start, end=start + (result.end - result.start))
    grain = _offset_grain(offset) if not offset.is_date_grain else result.grain
    grain = grain if grain in _GRAIN_STEP else Grain.MINUTE
    kind = Kind.DATETIME if result.kind is Kind.DATE else result.kind
    return replace(result, kind=kind, grain=grain, start=start, end=start + _GRAIN_STEP[grain])
