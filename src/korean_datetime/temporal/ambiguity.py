"""모호성 종류 — 값은 정책대로 하나로 정하고, 추정이 들어간 부분을 알린다

값은 바뀌지 않습니다. 호출하는 쪽이 종류를 보고 되물을지, 그대로 쓸지 정합니다.
"""

from __future__ import annotations

from enum import Enum


class Ambiguity(str, Enum):
    MERIDIEM = "meridiem"
    """오전/오후가 없는 1~11시 → 가까운 미래로 정함 ('3시'). 기준 시각과 상관없이 문장만 보고 항상 표시"""
    NOON_OR_MIDNIGHT = "noon_or_midnight"
    """오전/오후가 없는 12시 → 정오/자정 중 가까운 미래로 정함 ('12시'). 문장만 보고 항상 표시"""
    CYCLE_SHIFTED = "cycle_shifted"
    """생략된 연/월/일이 이미 지나 다음 주기로 넘김 ('6월 3일'@9월 → 내년, '오전 10시'@14시 → 내일)"""
    SAME_WEEKDAY = "same_weekday"
    """오늘과 같은 요일을 말함 → 다음 주로 정함 ('월요일'@월요일)"""
    DAY_ATTRIBUTION = "day_attribution"
    """자정을 넘는 시각이라 어느 날에 속하는지 모호 ('밤 1시', '자정', '심야')"""
    MULTI_DAY_TIME = "multi_day_time"
    """여러 날짜 구간에 시각이 붙어 첫날로 정함 ('이번 주말 오후 3시', '다음주 오후 3시')"""
    CALENDAR_ROW_SPILL = "calendar_row_spill"
    """달력 줄 주차의 요일이 앞뒤 달 칸 ('다음달 첫째 주 월요일'이 이번 달 날짜이거나 +1주로 옮김)"""
    NEXT_WEEKEND = "next_weekend"
    """'다음 주말'을 '다음 주의 주말'로 정함 (문맥에 따라 이번 주말일 수 있음)"""
    TWO_DIGIT_YEAR = "two_digit_year"
    """두 자리 연도를 50 이상 19xx, 미만 20xx로 정함 ('99년')"""


def ordered(flags: frozenset[Ambiguity]) -> tuple[Ambiguity, ...]:
    """정의 순서대로 정렬 (결과 비교·출력이 항상 같도록)"""
    return tuple(a for a in Ambiguity if a in flags)
