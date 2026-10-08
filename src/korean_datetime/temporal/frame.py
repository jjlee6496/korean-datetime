"""토큰 → Frame(표현 하나의 슬롯 묶음) 조립

인접 토큰(공백이나 '에', '의', '쯤' 같은 조사만 사이에 있는)을 하나의 Frame에 차례로 채웁니다.
각 토큰 종류에는 순위(rank)가 있어 **순위가 커지는 방향으로만** 채울 수 있습니다:

    0 연 → 1 월/주 → 2 일/상대일/기념일 → 3 요일/주말 → 4 시간대 → 5 시 → 6 분 → 7 기준 시각 오프셋

'다음주 월요일 저녁 7시 반'은 1→3→4→5→6으로 한 Frame이 되고,
'내일 3시 모레 5시'는 2→5 다음에 다시 2가 나오므로 Frame이 두 개로 나뉩니다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from ..core.scanner import Token
from .lexicon import Period
from .tokens import TK, Clock, DateTriple, HolidayRef, Lookback, MonthPart, Offset

# 표현 사이에 허용하는 것: 공백, 쉼표, 조사, 괄호 요일 '(월)', ISO 구분자 'T'
_JOIN_GAP = re.compile(r"(?:[\s,]|T|\(\s*[월화수목금토일](?:요일|욜)?\s*\)|에|의|쯤|경|께|즈음|정도)*")


@dataclass(frozen=True, slots=True)
class Frame:
    start: int = -1
    end: int = -1
    rank: int = -1
    invalid: bool = False
    year: int | None = None
    year_rel: int | None = None
    year_part: str | None = None
    month: int | None = None
    month_rel: int | None = None
    month_part: MonthPart | None = None
    day: int | None = None
    day_rel: int | None = None
    week_rel: int | None = None
    week_nth: int | None = None  # 달력 줄 기준 주차
    nth_weekday: int | None = None  # N번째 요일
    weekday: int | None = None
    week_part: str | None = None
    day_shift: int | None = None  # 앞 날짜의 전날(-1)/다음 날(+1)
    holiday: HolidayRef | None = None
    date_offset: Offset | None = None  # 기준일로부터 ('3일 후')
    time_offset: Offset | None = None  # 기준 시각으로부터 ('1시간 후')
    anchored_offset: Offset | None = None  # 앞 표현으로부터 ('17시 5분 전'의 5분 전)
    period: Period | None = None
    clock: Clock | None = None
    minute: int | None = None
    now: bool = False
    soon: bool = False  # '이따', '곧': 뒤에 시각이 오면 그 시각으로 대체
    modifier_only: bool = False  # '곧', '당장': 시각 없이 혼자면 인식하지 않음
    modifier: int | None = None  # '지난 금요일'의 지난(-1)
    same_time: str | None = None  # '내일 이 시각'(clock), '작년 이맘때'(day)
    lookback: Lookback | None = None  # '최근 3개월', '지난 3일간', '최근 4분기'
    quarter_rel: int | None = None  # '이번 분기'(0), '지난 분기'(-1)
    to_date: str | None = None  # '연초 이후'(year), '이달 들어'(month)
    duration: Offset | None = None  # '6개월', '30분 동안': 기간 값 (다른 토큰과 묶지 않음)
    business_days: int | None = None  # '3거래일 전'(-3), '전 거래일'(-1): 영업일 달력으로 이동
    vague: str | None = None  # '최근'(recent), '향후'(future): 다른 토큰과 묶지 않음
    two_digit_year: bool = False  # '99년', '25.07.15'

    @property
    def is_empty(self) -> bool:
        return self.rank < 0

    @property
    def has_month(self) -> bool:
        return self.month is not None or self.month_rel is not None

    @property
    def has_year(self) -> bool:
        return self.year is not None or self.year_rel is not None

    @property
    def has_time(self) -> bool:
        return self.now or self.time_offset is not None or self.clock is not None or self.period is not None

    @property
    def is_meaningful(self) -> bool:
        if self.invalid or self.is_empty or self.modifier_only:
            return False
        return not (self.period is not None and self.period.start is None and self.clock is None)


Adder = Callable[[Frame, Token], Frame | None]


def _requires(frame: Frame, below: int, condition: bool = True) -> bool:
    return frame.rank < below and condition


_TWO_DIGIT_YEAR = re.compile(r"\d{2}(?!\d)")


def _add_formatted(frame: Frame, token: Token) -> Frame | None:
    value: DateTriple = token.value
    if not frame.is_empty:
        return None
    short = value.year is not None and bool(_TWO_DIGIT_YEAR.match(token.text))
    return replace(frame, year=value.year, month=value.month, day=value.day, two_digit_year=short)


def _add_year(frame: Frame, token: Token) -> Frame | None:
    if not frame.is_empty:
        return None
    return replace(frame, year=token.value, two_digit_year=bool(_TWO_DIGIT_YEAR.match(token.text)))


def _add_day(frame: Frame, token: Token) -> Frame | None:
    ok = _requires(frame, 2, frame.week_rel is None and frame.year_part is None)
    if not ok or (token.weak and not frame.has_month) or (frame.has_year and not frame.has_month):
        return None
    return replace(frame, day=token.value)


def _add_month_part(frame: Frame, token: Token) -> Frame | None:
    part: MonthPart = token.value
    if not _requires(frame, 2, frame.week_rel is None and frame.year_part is None):
        return None
    if frame.has_month:
        return replace(frame, month_part=part)
    if frame.has_year and part.name in ("first_day", "last_day"):  # '올해 마지막 날', '내년 첫날'
        return replace(frame, year_part=part.name)
    return (
        replace(frame, month_part=part) if part.implicit_month else None
    )  # '말일': 월 생략 (다음 주기 가능)


# 해의 N번째 요일·주: 1~4번째는 항상 1월, 끝에서 1~4번째는 항상 12월 ('올해 마지막 금요일', '내년 첫째 주')
# 그 밖('올해 다섯째 금요일')은 월을 정할 수 없으므로 표현 전체를 무효로 (이번 달로 잘못 읽지 않도록)
_YEAR_NTH_MONTH = {**dict.fromkeys(range(1, 5), 1), **dict.fromkeys(range(-4, 0), 12)}


def _add_week_nth(frame: Frame, token: Token) -> Frame | None:
    ok = _requires(frame, 2, frame.week_rel is None and frame.year_part is None)
    if not ok:
        return None
    field = "week_nth" if token.kind == TK.WEEK_NTH else "nth_weekday"
    if frame.has_year and not frame.has_month:
        month = _YEAR_NTH_MONTH.get(token.value)
        return (
            replace(frame, invalid=True)
            if month is None
            else replace(frame, month=month, **{field: token.value})
        )
    return replace(frame, **{field: token.value})


def _add_weekday(frame: Frame, token: Token) -> Frame | None:
    ok = _requires(frame, 3, frame.year_part is None and frame.holiday is None and frame.month_part is None)
    return replace(frame, weekday=token.value) if ok else None


def _add_week_part(frame: Frame, token: Token) -> Frame | None:
    context_ok = (
        frame.is_empty
        or (frame.week_rel is not None and frame.rank == 1)
        or ((frame.week_nth is not None or frame.nth_weekday is not None) and frame.day is None)
    )
    return replace(frame, week_part=token.value) if _requires(frame, 3, context_ok) else None


def _add_day_shift(frame: Frame, token: Token) -> Frame | None:
    """'화요일의 전날': 날짜 뒤에 붙음. 앞에 날짜가 없으면 link_day_shifts가 앞 표현의 날짜를 이어줌."""
    ok = frame.day_shift is None and frame.date_offset is None and frame.lookback is None
    return replace(frame, day_shift=token.value) if _requires(frame, 4, ok) else None


def _add_rel(frame: Frame, token: Token) -> Frame | None:
    offset: Offset = token.value
    if frame.is_empty:
        return (
            replace(frame, date_offset=offset) if offset.is_date_grain else replace(frame, time_offset=offset)
        )
    return replace(frame, anchored_offset=offset) if frame.rank < 7 else None


def _add_minute(frame: Frame, token: Token) -> Frame | None:
    ok = frame.clock is not None and frame.clock.minute is None and frame.minute is None
    return replace(frame, minute=token.value) if _requires(frame, 6, ok) else None


def _now(frame: Frame, word_class: str) -> Frame:
    return replace(frame, now=True, soon=word_class != "now", modifier_only=word_class == "modifier")


def _simple(field: str, below: int, condition: Callable[[Frame], bool] = lambda f: True) -> Adder:
    def add(frame: Frame, token: Token) -> Frame | None:
        return replace(frame, **{field: token.value}) if _requires(frame, below, condition(frame)) else None

    return add


_ADDERS: dict[str, tuple[int, Adder]] = {
    TK.YEAR: (0, _add_year),
    TK.YEAR_REL: (0, _simple("year_rel", 0)),
    TK.YEAR_PART: (1, _simple("year_part", 1)),
    TK.MONTH: (1, _simple("month", 1)),
    TK.MONTH_REL: (1, _simple("month_rel", 1)),
    TK.WEEK_REL: (1, _simple("week_rel", 0)),
    TK.MODIFIER: (0, _simple("modifier", 0)),
    TK.FORMATTED: (2, _add_formatted),
    TK.DAY: (2, _add_day),
    TK.DAY_REL: (2, _simple("day_rel", 0)),
    TK.WEEK_NTH: (2, _add_week_nth),
    TK.NTH_WEEKDAY: (2, _add_week_nth),
    TK.HOLIDAY: (2, _simple("holiday", 1)),
    TK.MONTH_PART: (2, _add_month_part),
    TK.WEEKDAY: (3, _add_weekday),
    TK.WEEK_PART: (3, _add_week_part),
    TK.DAY_SHIFT: (3, _add_day_shift),
    TK.PERIOD: (4, _simple("period", 4)),
    TK.CLOCK: (5, _simple("clock", 5)),
    TK.NOW: (5, lambda f, t: _now(f, t.value) if f.is_empty else None),
    TK.LOOKBACK: (9, lambda f, t: replace(f, lookback=t.value) if f.is_empty else None),
    TK.QUARTER_REL: (1, lambda f, t: replace(f, quarter_rel=t.value) if f.is_empty else None),
    TK.TO_DATE: (9, lambda f, t: replace(f, to_date=t.value) if f.is_empty else None),
    TK.DURATION: (9, lambda f, t: replace(f, duration=t.value) if f.is_empty else None),
    TK.BUSINESS_DAY: (2, lambda f, t: replace(f, business_days=t.value) if f.is_empty else None),
    TK.SAME_TIME: (
        5,
        lambda f, t: replace(f, same_time=t.value) if f.rank < 4 and f.time_offset is None else None,
    ),
    TK.VAGUE: (9, lambda f, t: replace(f, vague=t.value) if f.is_empty else None),
    TK.MINUTE: (6, _add_minute),
    TK.HALF: (6, _add_minute),
    TK.ON_THE_HOUR: (6, _add_minute),
}


def _rank_of(frame: Frame, token: Token) -> int:
    if token.kind == TK.REL:
        if not frame.is_empty:
            return 7
        return 2 if token.value.is_date_grain else 5
    return _ADDERS[token.kind][0]


def add_token(frame: Frame, token: Token) -> Frame | None:
    """token을 frame에 넣은 새 Frame. 넣을 수 없으면 None."""
    if token.kind == TK.INVALID:
        return replace(frame, invalid=True, start=_start(frame, token), end=token.end)
    if token.kind == TK.BREAK:
        return None
    if frame.soon and token.kind in (TK.CLOCK, TK.PERIOD):  # '이따 5시': 5시로 해석하고 범위는 '이따'부터
        fresh = add_token(Frame(), token)
        return None if fresh is None else replace(fresh, start=frame.start)
    adder = _add_rel if token.kind == TK.REL else _ADDERS[token.kind][1]
    added = adder(frame, token)
    if added is None:
        return None
    return replace(added, rank=_rank_of(frame, token), start=_start(frame, token), end=token.end)


def _start(frame: Frame, token: Token) -> int:
    return token.start if frame.is_empty else frame.start


# '오늘로부터 한 달 후', '내일부터 3일 뒤': 부터 뒤에 기간이 오면 범위가 아니라 기준점
# 단 '까지'가 붙으면 범위 ('3시부터 30분 뒤까지' = 3시~3시 30분, ranges.py에서 A 기준으로 계산)
_ANCHOR_GAP = re.compile(r"\s*(?:(?:으로|로)?부터|에서)\s*")
_UNTIL = re.compile(r"\s*까지")


def _joinable(text: str, end: int, token: Token) -> bool:
    if _JOIN_GAP.fullmatch(text, end, token.start):
        return True
    if token.kind != TK.REL or _ANCHOR_GAP.fullmatch(text, end, token.start) is None:
        return False
    return not (text[end : token.start].strip().endswith("부터") and _UNTIL.match(text, token.end))


def build_frames(tokens: Sequence[Token], text: str) -> list[Frame]:
    frames: list[Frame] = []
    current = Frame()
    for token in tokens:
        if current.start >= 0 and not _joinable(text, current.end, token):
            frames.append(current)
            current = Frame()
        added = add_token(current, token)
        if added is None:
            frames.append(current)
            added = add_token(Frame(), token)
        current = added if added is not None else Frame()
    frames.append(current)
    return [frame for frame in frames if frame.is_meaningful]


# 슬롯 순위 (build_frames의 순위와 같음). 선택지 'A 아니면 B'에서 B가 A의 문맥을 이어받을 때 사용
_SLOT_RANKS: tuple[tuple[str, ...], ...] = (
    ("year", "year_rel", "modifier"),
    ("month", "month_rel", "week_rel", "year_part"),
    (
        "day",
        "day_rel",
        "week_nth",
        "nth_weekday",
        "holiday",
        "month_part",
        "date_offset",
        "quarter_rel",
        "business_days",
    ),
    ("weekday", "week_part"),
    ("period",),
    ("clock", "now", "time_offset", "same_time"),
)
_ALTERNATIVE_GAP = re.compile(r"\s*(?:아니면|또는|혹은|이나|나|과|와|및|하고|,|/)\s*")


def _top_rank(frame: Frame) -> int | None:
    for rank, fields in enumerate(_SLOT_RANKS):
        if any(getattr(frame, name) not in (None, False) for name in fields):
            return rank
    return None


def inherit_context(frame: Frame, previous: Frame) -> Frame:
    """B의 가장 상위 슬롯보다 위 순위인 A의 슬롯을 B에 채움 ('다음주 월요일 아니면 화요일' → 다음주 화요일)"""
    top = _top_rank(frame)
    if not top:
        return frame
    inherited = {
        name: getattr(previous, name)
        for fields in _SLOT_RANKS[:top]
        for name in fields
        if getattr(previous, name) not in (None, False)
    }
    return replace(frame, **inherited) if inherited else frame


_CONJUNCTION_GAP = re.compile(r"\s*(?:과|와|하고|그리고|및|,)?\s*")
_DATE_FIELDS: tuple[str, ...] = tuple(name for fields in _SLOT_RANKS[:4] for name in fields)


def _has_date_slot(frame: Frame) -> bool:
    return any(getattr(frame, name) not in (None, False) for name in _DATE_FIELDS)


def link_day_shifts(frames: Sequence[Frame], text: str) -> list[Frame]:
    """'다음 주 화요일과 그다음 날 오전 9시': 날짜 없는 '그다음 날'이 바로 앞 표현의 날짜를 이어받음.
    이어받을 앞 표현이 없으면(다른 문장·대화의 날짜를 가리킴) 결과에서 뺌."""
    linked: list[Frame] = []
    for frame in frames:
        if frame.day_shift is not None and not _has_date_slot(frame):
            previous = linked[-1] if linked else None
            if previous is None or not _CONJUNCTION_GAP.fullmatch(text, previous.end, frame.start):
                continue
            frame = replace(frame, **{name: getattr(previous, name) for name in _DATE_FIELDS})
        linked.append(frame)
    return linked


_CORRECTION_GAP = re.compile(r"\s*(?:이|가|은|는)?\s*아니(?:라|고)(?:요)?\s*,?\s*")


def apply_corrections(frames: Sequence[Frame], text: str) -> list[Frame]:
    """'A가 아니라 B': A는 버리고 B만 남김. B에 빠진 정보는 A에서 이어받음 ('3시가 아니라 5시' → 5시)"""
    kept: list[Frame] = []
    for frame in frames:
        previous = kept[-1] if kept else None
        if previous is not None and _CORRECTION_GAP.fullmatch(text, previous.end, frame.start):
            kept[-1] = inherit_context(frame, previous)
            continue
        kept.append(frame)
    return kept


def link_alternatives(frames: Sequence[Frame], text: str) -> list[Frame]:
    """'A 아니면 B', 'A 또는 B', 'A이나 B': B가 A의 문맥을 이어받은 새 Frame 목록 (결과는 각각 유지)"""
    linked: list[Frame] = []
    for frame in frames:
        previous = linked[-1] if linked else None
        if previous is not None and _ALTERNATIVE_GAP.fullmatch(text, previous.end, frame.start):
            frame = inherit_context(frame, previous)
        linked.append(frame)
    return linked
