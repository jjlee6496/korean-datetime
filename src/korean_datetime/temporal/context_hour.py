"""AmbiguousHour.CONTEXT: 오전/오후 없는 1~11시를 같은 텍스트 안의 단서로 정함

단어 목록을 새로 만들지 않고 구조와 기존 어휘만 씁니다:
1. 순서: 앞에 오전/오후가 정해진 시각이 있으면 그 뒤로 이어지는 후보 중 가장 이른 것
   ('오후 6시에 끝나고 8시 영화' → 20시). 대화의 시각은 대개 앞으로 진행함
2. 시간대 말: 가장 가까운 lexicon.PERIODS 어휘의 시간대 ('저녁 먹으러 8시쯤' → 20시)
3. 둘 다 없으면 DAYTIME 규칙의 값 그대로 (해석 단계에서 이미 계산됨)

AI허브 대화 데이터(Training 677건) 분석: DAYTIME 0.70, 순서(같은 텍스트) 0.76, 시간대 말 0.76.
값을 바꿔도 meridiem 표시는 남깁니다 (문장에 오전/오후가 없었다는 사실은 그대로).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from . import lexicon as lx
from .ambiguity import Ambiguity, ordered
from .frame import Frame
from .model import Kind, TemporalExpression

_PERIOD_WORDS = re.compile(
    "|".join(
        re.escape(word)
        for word in sorted(lx.PERIODS, key=len, reverse=True)
        if lx.PERIODS[word].start is not None
    )
)


def _open_hour(frame: Frame, result: TemporalExpression) -> int | None:
    """오전/오후를 문맥으로 정할 수 있는 시각이면 그 시(1~11), 아니면 None (12시는 정오/자정 문제라 제외)"""
    clock = frame.clock
    if clock is None or clock.hour % 12 == 0:
        return None
    is_open = (
        Ambiguity.MERIDIEM in result.ambiguities
        and not result.is_range
        and frame.anchored_offset is None  # '7시 5분 전'은 오프셋 적용 뒤라 시만 바꿀 수 없음
    )
    return clock.hour % 12 if is_open else None


def _from_reference(frame: Frame) -> bool:
    return any(value is not None for value in (frame.duration, frame.lookback, frame.to_date, frame.vague))


def _settled_hour(result: TemporalExpression) -> int | None:
    """오전/오후가 정해진 시각의 24시간제 시 (날짜만 있거나 아직 모호하면 None)"""
    if result.kind is Kind.DATE or Ambiguity.MERIDIEM in result.ambiguities:
        return None
    return result.start.hour


def _after(hour: int, previous: int) -> int | None:
    later = [candidate for candidate in (hour, hour + 12) if candidate >= previous]
    return min(later) if later else None


def _nearest_period(text: str, span: tuple[int, int]) -> int | None:
    """span 밖에서 가장 가까운 시간대 말의 시작 시각"""
    best: tuple[int, float] | None = None
    for match in _PERIOD_WORDS.finditer(text):
        if span[0] <= match.start() and match.end() <= span[1]:
            continue
        distance = min(abs(match.start() - span[1]), abs(span[0] - match.end()))
        start = lx.PERIODS[match.group()].start
        if start is not None and (best is None or distance < best[0]):
            best = (distance, start)
    return None if best is None else int(best[1])


def _choose(hour: int, previous: int | None, text: str, span: tuple[int, int]) -> int | None:
    if previous is not None and (chosen := _after(hour, previous)) is not None:
        return chosen
    period_start = _nearest_period(text, span)
    if period_start is None:
        return None
    return hour if period_start < 12 else hour + 12


def _with_hour(result: TemporalExpression, hour: int, now: datetime, roll: bool) -> TemporalExpression:
    """시만 바꿈. 날짜 없는 시각(kind=TIME)은 다음 날로 넘길지 다시 판단
    ('7시'@9시: 07시면 지났으니 내일, 19시면 오늘)"""
    flags: set[Ambiguity] = {flag for flag in result.ambiguities if flag is not Ambiguity.CYCLE_SHIFTED}
    if result.kind is not Kind.TIME:
        start = result.start.replace(hour=hour)
        return replace(result, start=start, end=start + (result.end - result.start))
    start = result.start.replace(year=now.year, month=now.month, day=now.day, hour=hour)
    passed = roll and start < now.replace(second=0, microsecond=0)
    if passed:
        start += timedelta(days=1)
        flags.add(Ambiguity.CYCLE_SHIFTED)
    length = result.end - result.start
    return replace(result, start=start, end=start + length, ambiguities=ordered(frozenset(flags)))


def apply_context_hours(
    items: Sequence[tuple[Frame, TemporalExpression]], text: str, now: datetime, roll: bool
) -> list[tuple[Frame, TemporalExpression]]:
    """위치 순 (frame, 결과) 목록에서 모호한 시각의 오전/오후를 문맥으로 다시 정한 새 목록.
    roll: 날짜 없는 시각이 이미 지났으면 다음 날로 넘김 (cycle=FUTURE)"""
    adjusted: list[tuple[Frame, TemporalExpression]] = []
    previous: int | None = None
    for frame, result in items:
        if _from_reference(frame):  # '2시간', '최근 30분': 말한 시각이 아니라 지금 시각에서 나온 값
            adjusted.append((frame, result))
            continue
        if (hour := _open_hour(frame, result)) is not None:
            chosen = _choose(hour, previous, text, result.span)
            if chosen is not None and chosen != result.start.hour:
                result = _with_hour(result, chosen, now, roll)
        elif (settled := _settled_hour(result)) is not None:
            previous = settled
        adjusted.append((frame, result))
    return adjusted
