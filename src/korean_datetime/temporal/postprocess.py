"""스캔된 토큰 후처리

1. 기간 + 방향 병합: [NUM(1,시간) NUM(30,분) DIRECTION(후)] → REL(+1시간 30분)
2. 방향이 붙지 않은 NUM의 역할 결정: '15일' → DAY, '30분' → MINUTE, '25년' → YEAR, 그 외('2주') → BREAK
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..core.scanner import Token
from . import lexicon as lx
from .rules import is_single_syllable_sino, short_year
from .tokens import TK, NumUnit, Offset

_DURATION_GAP = re.compile(r"\s*")
_DURATION_SUFFIX = re.compile(lx.DURATION_SUFFIX)
_DIRECTION_GAP = re.compile(r"\s*(?:정도|쯤|가량|즈음)?\s*")


def postprocess(tokens: Sequence[Token], text: str) -> list[Token]:
    return [_classify_number(token, text) for token in _merge_durations(tokens, text)]


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


def _classify_number(token: Token, text: str) -> Token:
    if token.kind == TK.DIRECTION:
        return _replace(token, TK.BREAK, None)
    if token.kind != TK.NUM:
        return token
    value: NumUnit = token.value
    if value.term or (value.unit in ("일", "분") and _DURATION_SUFFIX.match(text, token.end)):
        return _replace(token, TK.BREAK, None)  # '이틀', '3일간', '30분 동안'은 날짜/시각이 아님
    if value.unit == "일":
        if not 1 <= value.amount <= 31:
            return _replace(token, TK.INVALID, None)
        return _replace(token, TK.DAY, value.amount, weak=is_single_syllable_sino(token))
    if value.unit == "분":
        return (
            _replace(token, TK.MINUTE, value.amount)
            if value.amount <= 59
            else _replace(token, TK.INVALID, None)
        )
    if value.unit == "년" and len(value.digits) == 2:
        return _replace(token, TK.YEAR, short_year(value.digits))
    return _replace(token, TK.BREAK, None)
