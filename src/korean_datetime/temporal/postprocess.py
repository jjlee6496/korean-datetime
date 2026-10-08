"""스캔된 토큰 후처리

1. 기간 + 방향 병합: [NUM(1,시간) NUM(30,분) DIRECTION(후)] → REL(+1시간 30분)
2. 방향이 붙지 않은 NUM의 역할 결정: '15일' → DAY, '30분' → MINUTE, '25년' → YEAR, 그 외('2주') → BREAK
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

from ..core.scanner import Token, ends_word
from . import lexicon as lx
from .rules import is_single_syllable_sino, short_year
from .tokens import TK, NumUnit, Offset

_DURATION_GAP = re.compile(r"\s*")
_DURATION_SUFFIX = re.compile(lx.DURATION_SUFFIX)
_DIRECTION_GAP = re.compile(r"\s*(?:정도|쯤|가량|즈음)?\s*")
_RATE_OR_ORDINAL = re.compile(lx.RATE_OR_ORDINAL_SUFFIX)
_DURATION_CUE = re.compile(
    rf"\s*(?:{'|'.join(lx.DURATION_CUES)})|(?:{'|'.join(lx.GLUED_DURATION_CUES)})(?![가-힣])"
)
_CLOCK_GAP = re.compile(r"\s*")
_FRACTION = re.compile(r"의\s*(?:\d|[일이삼사오육칠팔구십한두세네])")  # '10분의 1'
_DURATION_SUFFIX_RE = re.compile(lx.DURATION_SUFFIX)


def _word_ends(text: str, end: int) -> bool:
    """기간 값 뒤에 올 수 있는 것: 조사·공백·문장 부호, 기간 단서('간', '동안', '수익률')"""
    return ends_word(text, end) or bool(
        _DURATION_SUFFIX_RE.match(text, end) or _DURATION_CUE.match(text, end)
    )


_SINO_DIGITS = frozenset("일이삼사오육칠팔구십백천")
_AMBIGUOUS_UNITS = frozenset({"일", "주", "분", "초"})  # 한 글자 단위만 ('일주일', '삼개월'은 그대로 기간)


def _glued_one_syllable_sino(token: Token) -> bool:
    """'구분', '사주', '오일': 한자 수사 한 글자 + 단위가 띄어쓰기 없이 붙음 (다른 낱말일 가능성이 큼)"""
    value: NumUnit = token.value
    if (
        value.digits
        or value.term
        or value.unit not in _AMBIGUOUS_UNITS
        or any(ch.isspace() for ch in token.text)
    ):
        return False
    number = token.text[: -len(value.unit)] if token.text.endswith(value.unit) else token.text
    return len(number) == 1 and number in _SINO_DIGITS


def _can_be_duration(token: Token, text: str) -> bool:
    """길이 값으로 볼 수 있는지. 걸러내는 것:
    - '85만6767주', '100주 매수': 혼자 쓴 'N주'는 주식 수와 겹쳐 기간 단서가 있을 때만 ('2주 동안', '2주간')
    - '100달러', '2022 분야별': 낱말이 끝나지 않음
    - '10분의 1': 분수
    - '구분', '사주', '십분': 한 글자 한자 수사가 단위에 붙은 낱말"""
    value: NumUnit = token.value
    if _glued_one_syllable_sino(token) or not _word_ends(text, token.end):
        return False
    if value.unit == "주" and not _DURATION_SUFFIX_RE.match(text, token.end):
        return False
    return not (value.unit == "분" and _FRACTION.match(text, token.end))


def postprocess(tokens: Sequence[Token], text: str) -> list[Token]:
    merged = _merge_durations(tokens, text)
    return [_classify_number(token, text, merged[i - 1] if i else None) for i, token in enumerate(merged)]


def _merge_durations(tokens: Sequence[Token], text: str) -> list[Token]:
    merged: list[Token] = []
    i = 0
    while i < len(tokens):
        run_end = _duration_run_end(tokens, i, text)
        direction = tokens[run_end] if run_end < len(tokens) else None
        if (
            run_end > i
            and not _is_date_after_month(tokens, i, run_end, text)
            and direction is not None
            and direction.kind == TK.DIRECTION
            and _DIRECTION_GAP.fullmatch(text, tokens[run_end - 1].end, direction.start)
        ):
            offset = _sum_offsets(tokens[i:run_end]).scaled(direction.value)
            start = tokens[i].start
            merged.append(Token(TK.REL.value, offset, start, direction.end, text[start : direction.end]))
            i = run_end + 1
            continue
        if run_end > i and _RATE_OR_ORDINAL.match(text, tokens[run_end - 1].end):
            # '1시간 30분마다': 비율 표현이 묶음 전체에 걸림 (길이 값이 아님)
            merged.extend(_replace(token, TK.BREAK, None) for token in tokens[i:run_end])
            i = run_end
            continue
        if run_end - i >= 2 and _mergeable_run(tokens, i, run_end, text):
            # '1시간 30분 동안': 방향 없는 기간 묶음은 하나의 기간 값
            start, end = tokens[i].start, tokens[run_end - 1].end
            offset = _sum_offsets(tokens[i:run_end])
            merged.append(Token(TK.DURATION.value, offset, start, end, text[start:end]))
            i = run_end
            continue
        # 방향이 없는 기간 묶음은 통째로 넘긴다 (긴 입력에서 선형 시간 유지)
        stop = max(run_end, i + 1)
        merged.extend(tokens[i:stop])
        i = stop
    return merged


_MONTH_KINDS = (TK.MONTH, TK.MONTH_REL)


def _is_date_after_month(tokens: Sequence[Token], i: int, run_end: int, text: str) -> bool:
    """'11월 9일 이후', '지난달 22일 전': 월 바로 뒤의 'N일'은 기간이 아니라 날짜"""
    if i == 0 or run_end - i != 1 or tokens[i].kind != TK.NUM or tokens[i].value.unit != "일":
        return False
    previous = tokens[i - 1]
    return (
        previous.kind in _MONTH_KINDS
        and _DURATION_GAP.fullmatch(text, previous.end, tokens[i].start) is not None
    )


def _unit_size(token: Token) -> int:
    months, days, seconds = lx.DURATION_UNITS[token.value.unit]
    return months * 2_592_000 + days * 86_400 + seconds


def _mergeable_run(tokens: Sequence[Token], i: int, run_end: int, text: str) -> bool:
    """방향 없는 'N단위' 여러 개를 하나의 기간으로 볼지: '1년 6개월'처럼 큰 단위에서 작은 단위로 가고,
    월 바로 뒤가 아니어야 함 ('12월 20일 5년 임기'는 날짜 20일 + 기간 5년)"""
    numbers = [token for token in tokens[i:run_end] if token.kind == TK.NUM]
    sizes = [_unit_size(token) for token in numbers]
    decreasing = all(a > b for a, b in pairwise(sizes))
    after_month = i > 0 and tokens[i - 1].kind in _MONTH_KINDS
    return decreasing and not after_month and _word_ends(text, tokens[run_end - 1].end)


def _duration_run_end(tokens: Sequence[Token], i: int, text: str) -> int:
    """tokens[i]부터 이어지는 기간 토큰(NUM, 단위 뒤의 '반')의 끝 인덱스(미포함)"""
    j = i
    while j < len(tokens):
        token = tokens[j]
        is_num = token.kind == TK.NUM
        is_half = token.kind == TK.HALF and j > i and tokens[j - 1].value.unit in lx.HALF_OF_UNIT
        if not (is_num or is_half):
            break
        if j > i and not _DURATION_GAP.fullmatch(text, tokens[j - 1].end, token.start):
            break
        j += 1
    return j


def _sum_offsets(tokens: Sequence[Token]) -> Offset:
    total = Offset()
    previous_unit = ""
    for token in tokens:
        if token.kind == TK.HALF:
            months, days, seconds = lx.HALF_OF_UNIT[previous_unit]
            total = total + Offset(months, days, seconds)
            continue
        value: NumUnit = token.value
        months, days, seconds = lx.DURATION_UNITS[value.unit]
        total = total + Offset(months * value.amount, days * value.amount, seconds * value.amount)
        previous_unit = value.unit
    return total


def _replace(token: Token, kind: TK, value: object, weak: bool = False) -> Token:
    return Token(kind.value, value, token.start, token.end, token.text, weak)


def _duration(token: Token, text: str) -> Token:
    if not _can_be_duration(token, text):
        return _replace(token, TK.BREAK, None)
    return _replace(token, TK.DURATION, _sum_offsets([token]))


def _right_after_clock(previous: Token | None, token: Token, text: str) -> bool:
    """'3시 30분'의 30분: 바로 앞이 시각이면 분, 아니면 기간 값('30분 걸려')"""
    return (
        previous is not None
        and previous.kind == TK.CLOCK
        and _CLOCK_GAP.fullmatch(text, previous.end, token.start) is not None
    )


def _classify_number(token: Token, text: str, previous: Token | None = None) -> Token:
    """방향 없는 'N단위'의 역할: 날짜(15일), 분(3시 30분), 연도(25년), 기간 값(6개월, 3일간)"""
    if token.kind == TK.DIRECTION:
        return _replace(token, TK.BREAK, None)
    if token.kind != TK.NUM:
        return token
    value: NumUnit = token.value
    if _RATE_OR_ORDINAL.match(text, token.end):
        return _replace(token, TK.BREAK, None)  # '3일마다', '3일째', '1일 1식': 길이가 아님
    if value.term or (value.unit in ("일", "분") and _DURATION_SUFFIX.match(text, token.end)):
        return _duration(token, text)  # '이틀', '3일간', '30분 동안'
    if value.unit == "일":
        if _DURATION_CUE.match(text, token.end):
            return _duration(token, text)  # '5일 수익률', '20일 이평선'
        if not 1 <= value.amount <= 31:
            return _replace(token, TK.INVALID, None)
        return _replace(token, TK.DAY, value.amount, weak=is_single_syllable_sino(token))
    if value.unit == "분":
        if not _right_after_clock(previous, token, text):
            return _duration(token, text)  # '30분 걸려'
        return (
            _replace(token, TK.MINUTE, value.amount)
            if value.amount <= 59
            else _replace(token, TK.INVALID, None)
        )
    if value.unit == "년" and len(value.digits) == 2:
        return _replace(token, TK.YEAR, short_year(value.digits))
    return _duration(token, text)  # '6개월', '2주', '1년', '두 시간'
