"""'A부터 B까지', 'A~B' → 하나의 범위 표현

B에 빠진 정보(연/월/날짜)는 A를 기준으로 다시 해석합니다.
- '10월 3일부터 5일까지'의 5일 → 10월 5일
- '작년 12월 30일부터 1월 2일까지'의 1월 2일 → 작년 기준 다음 해 1월 2일
- '내일 3시부터 5시'의 5시 → 내일 17시

B가 A보다 앞서면 A 기준 다음 주기로 넘기되, 넘긴 결과가 그 주기의 절반보다 멀면
뒤집힌 입력('10월 5일부터 10월 3일까지', '5일~3일')으로 보고 합치지 않습니다.
끝 시각은 B가 시각이면 B의 시작, 날짜면 B의 끝(B 포함)이며, 빈 범위는 만들지 않습니다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from .ambiguity import Ambiguity, ordered
from .frame import Frame
from .model import Kind, TemporalExpression
from .options import Cycle

# '부터 그다음 월요일까지'의 '그다음'은 A 뒤에서 찾으라는 뜻이라 B를 A 기준으로 해석하는 것과 같음
_RANGE_GAP = re.compile(r"\s*(?:(?:부터|에서)\s*(?:[~∼〜\-–—]\s*)?|[~∼〜\-–—]\s*)(?:그\s*다음\s*)?")
_UNTIL = re.compile(r"\s*까지")

# (frame, 기준 시각, 주기 선택) → 결과
Resolver = Callable[[Frame, datetime, Cycle], TemporalExpression | None]


def merge_ranges(
    items: Sequence[tuple[Frame, TemporalExpression]], text: str, resolve_from: Resolver
) -> list[TemporalExpression]:
    merged: list[TemporalExpression] = []
    i = 0
    while i < len(items):
        a = items[i][1]
        vague = a.kind is Kind.VAGUE or (i + 1 < len(items) and items[i + 1][1].kind is Kind.VAGUE)
        if (
            not vague
            and i + 1 < len(items)
            and _RANGE_GAP.fullmatch(text, a.span[1], items[i + 1][1].span[0])
        ):
            frame_b, b = items[i + 1]
            end = _range_end(a, _anchor_to(a, frame_b, b, resolve_from))
            if end is not None:
                if _explicit_meridiem(items[i][0]):  # '오후 3시부터 5시까지': 끝의 5시는 앞에서 정해짐
                    end = replace(end, ambiguities=tuple(x for x in end.ambiguities if x not in _HOUR_FLAGS))
                merged.append(_range(a, end, items[i + 1][1], text))
                i += 2
                continue
        merged.append(a)
        i += 1
    return merged


_HOUR_FLAGS = (Ambiguity.MERIDIEM, Ambiguity.NOON_OR_MIDNIGHT)


def _explicit_meridiem(frame: Frame) -> bool:
    """시간대('오후', '저녁')나 24시간제·시각 표기('15시', '15:00')로 오전/오후가 정해졌는지"""
    return frame.period is not None or (frame.clock is not None and frame.clock.literal)


def _has_own_anchor(frame: Frame) -> bool:
    """B가 스스로 기준을 가진 표현이면(모레, 다음주, 2027년 …) A에 맞춰 다시 해석하지 않음"""
    return (
        any(
            value is not None
            for value in (
                frame.year,
                frame.year_rel,
                frame.month_rel,
                frame.day_rel,
                frame.week_rel,
                frame.date_offset,
                frame.time_offset,
            )
        )
        or frame.now
    )


def _max_wrap(frame: Frame) -> timedelta:
    """B를 다음 주기로 넘길 때 허용하는 최대 거리 (생략된 단위 주기의 절반)"""
    if frame.month is not None:
        return timedelta(days=183)
    if frame.day is not None or frame.week_nth is not None:
        return timedelta(days=16)
    if frame.weekday is not None:
        return timedelta(days=7)
    return timedelta(hours=12)


def _is_pure_offset(frame: Frame) -> bool:
    """'30분 뒤', '3일 후'처럼 기준점에서의 거리만 있는 표현"""
    return (frame.date_offset is not None or frame.time_offset is not None) and frame.anchored_offset is None


def _anchor_to(
    a: TemporalExpression, frame_b: Frame, b: TemporalExpression, resolve_from: Resolver
) -> TemporalExpression | None:
    if _is_pure_offset(frame_b):  # 'A부터 30분 뒤까지'의 30분 뒤는 지금이 아니라 A 기준
        return resolve_from(frame_b, a.start, Cycle.CURRENT)
    if _has_own_anchor(frame_b):
        return b
    same_cycle = resolve_from(frame_b, a.start, Cycle.CURRENT)
    if same_cycle is not None and same_cycle.start >= a.start:
        return same_cycle
    next_cycle = resolve_from(frame_b, a.start, Cycle.FUTURE)
    if next_cycle is not None and next_cycle.start - a.start <= _max_wrap(frame_b):
        return next_cycle
    return None


def _range_end(a: TemporalExpression, b: TemporalExpression | None) -> TemporalExpression | None:
    if b is None:
        return None
    end = b.end if b.kind is Kind.DATE else b.start
    return b if end > a.start else None


def _range(
    a: TemporalExpression, b: TemporalExpression, b_original: TemporalExpression, text: str
) -> TemporalExpression:
    end_pos = b_original.span[1]
    until = _UNTIL.match(text, end_pos)
    if until:
        end_pos = until.end()
    end = b.end if b.kind is Kind.DATE else b.start
    kind = a.kind if a.kind is not Kind.DATE or b.kind is Kind.DATE else Kind.DATETIME
    start_pos = a.span[0]
    flags = ordered(frozenset(a.ambiguities) | frozenset(b.ambiguities))
    return TemporalExpression(
        text[start_pos:end_pos],
        (start_pos, end_pos),
        kind,
        a.grain,
        a.start,
        end,
        is_range=True,
        ambiguities=flags,
    )
