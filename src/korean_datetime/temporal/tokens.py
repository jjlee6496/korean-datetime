"""temporal 토큰 종류와 토큰 값 타입"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TK(str, Enum):
    """토큰 종류"""

    FORMATTED = "formatted"  # DateTriple: 2026-10-01, 10/15
    YEAR = "year"  # int: 2026년
    YEAR_REL = "year_rel"  # int: 올해(0), 내년(1)
    YEAR_PART = "year_part"  # str: h1, h2, q1..q4, early, late
    MONTH = "month"  # int: 10월, 시월
    MONTH_REL = "month_rel"  # int: 이번달(0), 다음달(1)
    MONTH_PART = "month_part"  # MonthPart: 초, 중순, 말일
    DAY = "day"  # int: 15일, 십오일
    DAY_REL = "day_rel"  # int: 오늘(0), 내일(1)
    WEEK_REL = "week_rel"  # int: 이번주(0), 다음주(1)
    WEEK_NTH = "week_nth"  # int: 첫째주(1), 마지막주(-1) — 달력 줄 기준 주차
    NTH_WEEKDAY = "nth_weekday"  # int: 셋째 토요일, 셋째 주말의 셋째 — N번째 요일
    WEEKDAY = "weekday"  # int: 월요일(0)~일요일(6)
    DAY_SHIFT = "day_shift"  # int: 앞 날짜의 전날(-1), 다음 날(+1)
    MODIFIER = "modifier"  # int: 요일/기념일 앞의 지난(-1), 이번(0), 다음(1)
    WEEK_PART = "week_part"  # str: weekend, weekdays, early
    HOLIDAY = "holiday"  # HolidayRef
    PERIOD = "period"  # lexicon.Period: 저녁, 오후, 밤
    CLOCK = "clock"  # Clock: 3시, 15:30, 자정
    MINUTE = "minute"  # int: 30분
    HALF = "half"  # 반
    ON_THE_HOUR = "on_the_hour"  # 정각
    NOW = "now"  # 지금
    SAME_TIME = "same_time"  # 이 시각 (날짜와 함께: 그날 지금 시각)
    LOOKBACK = "lookback"  # Lookback: 최근 3개월, 지난 3일간, 향후 2주, 최근 4분기
    QUARTER_REL = "quarter_rel"  # int: 이번 분기(0), 지난 분기(-1), 다음 분기(1)
    TO_DATE = "to_date"  # str: 연초 이후·올해 들어(year), 이달 들어(month) = 그 시작부터 오늘까지
    DURATION = "duration"  # Offset: 6개월, 3일간, 30분 동안 (날짜가 아닌 길이)
    BUSINESS_DAY = (
        "business_day"  # int: 3거래일 전(-3), 전 거래일(-1), 다음 영업일(1) — 영업일 달력이 있어야 계산
    )
    NUM = "num"  # NumUnit: 3일, 두 시간 (기간 후보)
    DIRECTION = "direction"  # int: 후(+1), 전(-1)
    REL = "rel"  # Offset: 3일 후, 30분 전
    INVALID = "invalid"  # 형식은 맞지만 값이 틀림 (13월, 25시) → 해당 표현 전체 무효
    BREAK = "break"  # 표현을 끊는 토큰 (단독 기간 '2주' 등)
    VAGUE = "vague"  # str: 최근(recent), 향후(future) — ParseOptions(vague=True)일 때만


@dataclass(frozen=True, slots=True)
class DateTriple:
    year: int | None
    month: int
    day: int


@dataclass(frozen=True, slots=True)
class Clock:
    """hour는 0~24. literal이면 오전/오후 모호성 해석을 하지 않음 (15:30, 13시, 3pm)."""

    hour: int
    minute: int | None = None
    literal: bool = False


@dataclass(frozen=True, slots=True)
class NumUnit:
    amount: int
    unit: str
    digits: str = ""  # 아라비아 숫자로 쓰였으면 원문 숫자
    term: bool = False  # 이틀·보름 같은 기간 전용 단어 (날짜로 쓰이지 않음)


@dataclass(frozen=True, slots=True)
class MonthPart:
    name: str  # early, mid, late, first_day, last_day
    implicit_month: bool = False  # '월말', '말일'처럼 월이 없어도 이번 달을 뜻함


@dataclass(frozen=True, slots=True)
class HolidayRef:
    key: str
    span: bool = False  # '연휴'면 앞뒤 포함 기간


@dataclass(frozen=True, slots=True)
class Lookback:
    """'최근 3개월'(recent: 오늘 포함), '지난 3개월'(past: 오늘 전까지), '향후 3개월'(future: 오늘부터).
    분기면 quarters, 그 밖은 offset"""

    direction: str
    offset: Offset | None = None
    quarters: int | None = None


@dataclass(frozen=True, slots=True)
class Offset:
    months: int = 0
    days: int = 0
    seconds: int = 0

    @property
    def is_date_grain(self) -> bool:
        return self.seconds == 0

    def __add__(self, other: Offset) -> Offset:
        return Offset(self.months + other.months, self.days + other.days, self.seconds + other.seconds)

    def scaled(self, sign: int) -> Offset:
        return Offset(self.months * sign, self.days * sign, self.seconds * sign)
