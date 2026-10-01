"""temporal 토큰 규칙 (정규식 → 토큰 값)

규칙 순서는 같은 길이로 매칭될 때의 우선순위입니다. 기본적으로는 가장 긴 매칭이 이깁니다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ..core.numerals import NATIVE, SINO, parse_korean_number, parse_native, parse_sino, syllable_count
from ..core.scanner import Split, Token, TokenRule
from . import lexicon as lx
from . import relative as rel
from .holiday_calendar import HolidayCalendar
from .tokens import TK, Clock, DateTriple, HolidayRef, MonthPart, NumUnit, Offset

Match = re.Match[str]
_RANGE_SEP = r"[~∼〜\-–]"


def words(keys: Iterable[str]) -> str:
    """어휘 목록 → 긴 것 우선 정규식 대안. 공백은 0개 이상의 공백으로."""
    ordered = sorted(set(keys), key=len, reverse=True)
    return "|".join(r"\s*".join(re.escape(part) for part in key.split(" ")) for key in ordered)


def lookup(table: Mapping[str, Any], text: str) -> Any:
    """공백 차이를 무시하고 어휘 표에서 값을 찾습니다."""
    compact = re.sub(r"\s+", "", text)
    for key, value in table.items():
        if key.replace(" ", "") == compact:
            return value
    raise KeyError(text)


def _rule(kind: TK, pattern: str, build: Callable[[Match], Any], *, flags: int = 0, **kw: Any) -> TokenRule:
    return TokenRule(kind.value, re.compile(pattern, flags), build, **kw)


def _tok(kind: TK, value: Any, match: Match, group: int | str = 0, weak: bool = False) -> Token:
    start, end = match.span(group)
    return Token(kind.value, value, start, end, match.group(group), weak)


def _invalid(match: Match) -> Split:
    return Split((_tok(TK.INVALID, None, match),))


def _in_range(value: int, low: int, high: int, match: Match) -> Any:
    return value if low <= value <= high else _invalid(match)


# ---------------------------------------------------------------- 날짜 형식 / 연 / 월 / 일


def _triple(year: int | None, month: int, day: int, match: Match) -> Any:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return _invalid(match)
    return DateTriple(year, month, day)


def short_year(two_digits: str) -> int:
    """두 자리 연도: 50 이상은 19xx, 미만은 20xx"""
    value = int(two_digits)
    return 1900 + value if value >= 50 else 2000 + value


def _formatted_rules(compact: bool) -> list[TokenRule]:
    rules = [
        _rule(
            TK.FORMATTED,
            r"(?<!\d)((?:19|20)\d{2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\.?(?!\d)",
            lambda m: _triple(int(m[1]), int(m[2]), int(m[3]), m),
        ),
        _rule(
            TK.FORMATTED,
            r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)",
            lambda m: _triple(int(m[1]), int(m[2]), int(m[3]), m),
        ),
        _rule(
            TK.FORMATTED,
            r"(?<![\d.])(\d{2})([-./])(\d{1,2})\2(\d{1,2})(?![\d.])",
            lambda m: _triple(short_year(m[1]), int(m[3]), int(m[4]), m),
        ),
        _rule(
            TK.FORMATTED,
            r"(?<![\d/.:\-])(\d{1,2})\s*[/-]\s*(\d{1,2})(?![\d/.:\-])(?!\s*(?:시|일|월|분|주|개|년|상|차|명|번|회|살|세|배|권|잔|병|층|등|위|점|건|곳|인분|%))",
            lambda m: _triple(None, int(m[1]), int(m[2]), m),
        ),
    ]
    if compact:
        rules += [
            _rule(
                TK.FORMATTED,
                r"(?<!\d)(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)",
                lambda m: _triple(short_year(m[1]), int(m[2]), int(m[3]), m),
            ),
            _rule(
                TK.FORMATTED,
                r"(?<!\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)",
                lambda m: _triple(None, int(m[1]), int(m[2]), m),
            ),
        ]
    return rules


_KOREAN_MONTH = words(lx.KOREAN_MONTHS)
_NOT_WEEKDAY = r"(?!\s*(?:요일|욜))"


# '낼'은 내일 말고도 '내다'의 관형형: '시너지를 낼 수', '속도를 낼 계획', '소송을 낼 것'
_NOT_VERB_NAEL = (
    r"(?!(?<=낼)\s*(?:수|것|거|게|건|계획|예정|방침|목표|전망|만큼|때|생각|필요|줄|뿐|정도|듯|만한|리))"
)


def _last_night(match: Match) -> Split:
    """'어젯밤', '간밤', '엊저녁' = 어제 + 밤/저녁"""
    day, part = ("day", "part") if match["day"] else ("day2", "part2")
    return Split((_tok(TK.DAY_REL, -1, match, day), _tok(TK.PERIOD, lx.PERIODS[match[part]], match, part)))


def _calendar_rules() -> list[TokenRule]:
    month_rel = f"({rel.prefix_pattern(lx.MONTH_PREFIX_FIXED)})\\s*달"
    return [
        _rule(TK.YEAR, r"(?<!\d)(\d{4})\s*년(?!\s*(?:간|동안|째))", lambda m: int(m[1])),
        _rule(
            TK.YEAR,
            rf"(?<!\d)((?:19|20)\d{{2}})(?!\d)(?=\s*(?:\d{{1,2}}\s*월|(?:{_KOREAN_MONTH})\s*월))",
            lambda m: int(m[1]),
        ),
        _rule(TK.YEAR_REL, rel.YEAR_PATTERN, lambda m: rel.year_value(m.group()), right_boundary=True),
        _rule(
            TK.MONTH, rf"(\d{{1,2}})\s*월(?:\s*달)?{_NOT_WEEKDAY}", lambda m: _in_range(int(m[1]), 1, 12, m)
        ),
        _rule(TK.MONTH, rf"({_KOREAN_MONTH})\s*월(?:\s*달)?{_NOT_WEEKDAY}", lambda m: lx.KOREAN_MONTHS[m[1]]),
        _rule(
            TK.MONTH_REL,
            month_rel,
            lambda m: rel.prefix_value(lx.MONTH_PREFIX_FIXED, m[1], lx.MONTH_PREFIX_EXCLUDED),
        ),
        _rule(TK.MONTH_REL, words(lx.MONTH_WORDS), lambda m: lookup(lx.MONTH_WORDS, m.group())),
        _rule(
            TK.MONTH_PART,
            words(lx.MONTH_PART_STRONG),
            lambda m: MonthPart(lookup(lx.MONTH_PART_STRONG, m.group()), implicit_month=True),
        ),
        _rule(
            TK.MONTH_PART,
            words(lx.MONTH_PART_WEAK),
            lambda m: MonthPart(lookup(lx.MONTH_PART_WEAK, m.group())),
            right_boundary=True,
            weak=True,
        ),
        _rule(
            TK.DAY_REL,
            r"(?P<day>어젯|엊)(?P<part>밤|저녁)|(?<![가-힣])(?P<day2>간)(?P<part2>밤)",
            _last_night,
        ),
        _rule(TK.YEAR_PART, words(lx.YEAR_PART), lambda m: lookup(lx.YEAR_PART, m.group())),
        _rule(TK.YEAR_PART, r"([1-4])\s*분기", lambda m: f"q{m[1]}"),
        _rule(
            TK.DAY_REL,
            rf"(?:{rel.DAY_PATTERN}){_NOT_VERB_NAEL}",
            lambda m: rel.day_value(m.group()),
            right_boundary=True,
        ),
        # 뉴스 제목과 본문이 붙은 '앞두고오늘(28일)': 괄호 날짜가 뒤따르면 앞말에 붙어 있어도 상대 일
        _rule(
            TK.DAY_REL,
            r"(?:오늘|금일|어제|내일)(?=\(\s*\d{1,2}\s*일\s*\))",
            lambda m: rel.day_value(m.group()),
            attachable=True,
        ),
        _rule(TK.INVALID, words(lx.ANAPHORA), _invalid, right_boundary=True),
        _rule(
            TK.INVALID,
            rf"(?:(?:{words(lx.WEEK_NTH)})\s*)?(?:{words(lx.CALENDAR_DEPENDENT)})",
            _invalid,
            right_boundary=True,
        ),
    ]


# ---------------------------------------------------------------- 주 / 요일


def _week_offset(prefix: str) -> int | None:
    return rel.prefix_value(lx.WEEK_PREFIX_FIXED, prefix, lx.WEEK_PREFIX_EXCLUDED)


def _week_rel_with_part(match: Match) -> Split | None:
    offset = _week_offset(match["rel"])
    if offset is None:
        return None
    return Split(
        (
            _tok(TK.WEEK_REL, offset, match, "head"),
            _tok(TK.WEEK_PART, lx.WEEK_PART_SUFFIX[match["part"]], match, "part"),
        )
    )


def _nth_weekend(match: Match) -> Split:
    return Split(
        (
            _tok(TK.NTH_WEEKDAY, lookup(lx.WEEK_NTH, match["nth"]), match, "nth"),
            _tok(TK.WEEK_PART, "weekend", match, "part"),
        )
    )


# 차주(借主)·금주(禁酒)와 구별: 요일·때 표현이 이어질 때만 ('차주 월요일', '금주 중' / '차주의 채무' 제외)
_WEEK_FOLLOWER = r"[월화수목금토일]\s*(?:요일|욜)|중|초|말|내|안|에|까지|부터|쯤|께|[^가-힣]|$"
_HOMONYM_WEEK = rf"(?!(?:차|금)\s*주(?!\s*(?:{_WEEK_FOLLOWER})))"


def _week_rules() -> list[TokenRule]:
    prefix = rel.prefix_pattern(lx.WEEK_PREFIX_FIXED)
    nth = words(lx.WEEK_NTH)
    return [
        _rule(
            TK.WEEK_REL,
            rf"{_HOMONYM_WEEK}({prefix})\s*주(?!일|간|년|차)",
            lambda m: _week_offset(m[1]),
            right_boundary=True,
        ),
        _rule(TK.WEEK_REL, rf"(?P<head>(?P<rel>{prefix})\s*주)\s*(?P<part>말|중|초)", _week_rel_with_part),
        _rule(TK.WEEK_PART, rf"(?:{words(lx.UPCOMING_PREFIX)})\s*주말", lambda m: "weekend"),
        _rule(TK.WEEK_PART, words(lx.WEEK_PART), lambda m: lx.WEEK_PART[m.group()], right_boundary=True),
        # '셋째 주말' = 셋째 토요일부터 이틀 ('셋째 주 주말'은 달력 셋째 줄의 주말)
        _rule(TK.WEEK_NTH, rf"(?P<nth>{nth})\s*(?P<part>주말)", _nth_weekend, right_boundary=True),
        _rule(
            TK.WEEK_NTH,
            rf"({nth})\s*주(?!일|간|년|말|중|초)",
            lambda m: lookup(lx.WEEK_NTH, m[1]),
            right_boundary=True,
        ),
        _rule(TK.WEEK_NTH, r"([1-5])\s*(?:번)?\s*째\s*주(?!일|간|년|말)", lambda m: int(m[1])),
        _rule(TK.WEEK_NTH, r"([1-5])\s*주\s*차", lambda m: int(m[1])),
        _rule(TK.WEEKDAY, r"([월화수목금토일])\s*(?:요일|욜)", lambda m: lx.WEEKDAYS[m[1]]),
        _rule(
            TK.DAY_SHIFT, words(lx.DAY_SHIFT), lambda m: lookup(lx.DAY_SHIFT, m.group()), right_boundary=True
        ),
        # '셋째 토요일', '마지막 금요일' = 그 달의 N번째 요일 ('셋째 주 토요일'은 달력 줄 기준이라 다름)
        _rule(
            TK.NTH_WEEKDAY,
            rf"({nth})\s*(?=[월화수목금토일]\s*(?:요일|욜))",
            lambda m: lookup(lx.WEEK_NTH, m[1]),
        ),
    ]


# ---------------------------------------------------------------- 시각 / 시간대


def _clock(hour: int, minute: int | None, match: Match, *, literal: bool = False) -> Any:
    if not 0 <= hour <= 24 or (minute is not None and not 0 <= minute <= 59) or (hour == 24 and minute):
        return _invalid(match)
    return Clock(hour, minute, literal=literal or hour == 0 or hour > 12)


def _english_clock(match: Match) -> Any:
    hour, minute = int(match[1]), int(match[2]) if match[2] else None
    if not 1 <= hour <= 12:
        return _invalid(match)
    hour = hour % 12 + (12 if match[3].lower() == "p" else 0)
    return _clock(hour, minute, match, literal=True)


def _native_hour(match: Match) -> Any:
    hour = 0 if match[1] == "영" else parse_native(match[1])
    return None if hour is None else _clock(hour, None, match)


# '시' 뒤에 붙어 다른 낱말이 되는 경우 ('3시간', 'S22 시리즈', '시즌', '시장', '시청', '시민')
_NOT_HOUR = r"(?!간|리즈|즌|장|청|민|내|외|점|설|험|행|력|계|군|의회)"
_TEMPORARY_NOUNS = (
    "적|지원|인하|인상|상향|하향|감면|유예|조치|허용|면제|"
    "운영|중단|도입|시행|연장|적용|특례|완화|확대|폐지|해제"
)
_NOT_TEMPORARY = rf"(?!\s*(?:{_TEMPORARY_NOUNS}))"


def _time_rules() -> list[TokenRule]:
    return [
        _rule(
            TK.CLOCK,
            r"(?<![\d:])(\d{1,2})\s*:\s*([0-5]\d)(?::[0-5]\d)?(?![\d:])",
            lambda m: _clock(int(m[1]), int(m[2]), m, literal=True),
        ),
        _rule(
            TK.CLOCK,
            r"(?<!\d)(\d{1,2})(?::([0-5]\d))?\s*([ap])\.?m\.?(?![a-z])",
            _english_clock,
            flags=re.IGNORECASE,
        ),
        _rule(TK.CLOCK, rf"(?<![\dA-Za-z])(\d{{1,2}})\s*시{_NOT_HOUR}", lambda m: _clock(int(m[1]), None, m)),
        # '공시'(公示)는 0시가 아님, '한시 지원'(限時)은 1시가 아님
        _rule(TK.CLOCK, rf"(영|{NATIVE})\s*시{_NOT_HOUR}{_NOT_TEMPORARY}", _native_hour, right_boundary=True),
        # '3~5시'의 3처럼 범위 앞쪽의 숫자
        _rule(
            TK.CLOCK,
            rf"(?<![\d:])(\d{{1,2}})(?=\s*{_RANGE_SEP}\s*\d{{1,2}}\s*시(?!간))",
            lambda m: _clock(int(m[1]), None, m),
        ),
        _rule(TK.CLOCK, words(lx.FIXED_TIMES), lambda m: Clock(lx.FIXED_TIMES[m.group()], 0, literal=True)),
        _rule(
            TK.PERIOD,
            words(lx.PERIODS),
            lambda m: lookup(lx.PERIODS, m.group().lower()),
            flags=re.IGNORECASE,
            right_boundary=True,
        ),
        _rule(
            TK.PERIOD,
            r"낮(?!은|게|아|추|춰|잡|춘|다|고|지)",
            lambda m: lx.PERIOD_SINGLE_SYLLABLE["낮"],
            right_boundary=True,
        ),
        _rule(TK.HALF, r"반", lambda m: 30, right_boundary=True, weak=True),
        _rule(TK.ON_THE_HOUR, r"정각", lambda m: 0, weak=True),
        _rule(TK.NOW, words(lx.NOW_WORDS), lambda m: "now", right_boundary=True),
        _rule(TK.NOW, words(lx.SOON_WORDS), lambda m: "soon", right_boundary=True),
        _rule(TK.NOW, words(lx.IMMEDIATE_WORDS), lambda m: "modifier", right_boundary=True),
        _rule(TK.SAME_TIME, words(lx.SAME_TIME_WORDS), lambda m: "clock", right_boundary=True),
        _rule(TK.SAME_TIME, words(lx.SAME_DAY_WORDS), lambda m: "day", right_boundary=True),
    ]


# ---------------------------------------------------------------- 기간 (N일, 두 시간, 보름)


_DIGIT_UNITS = "개월|주일|시간|년|달|주|일|분|초"
_SINO_UNITS = "개월|주일|년|주|일|분|초"
_NATIVE_UNITS = "시간|달|주|해"


def _sino_num(match: Match) -> NumUnit | None:
    amount = parse_sino(match[1])
    if amount is None:
        return None
    return NumUnit(amount, match[2])


def _past_span(match: Match) -> Offset | None:
    """'지난 3일간', '지난 한 달 동안' → 되돌아갈 기간"""
    amount = parse_korean_number(match["num"])
    if not amount:
        return None
    months, days, _ = lx.DURATION_UNITS[match["unit"]]
    return Offset(months * amount, days * amount)


def _duration_rules() -> list[TokenRule]:
    past_number = rf"(?P<num>\d{{1,4}}|{SINO}|{NATIVE})"
    return [
        _rule(
            TK.PAST_SPAN,
            rf"지난\s*{past_number}\s*(?P<unit>개월|주일|주|일|달|년|해)\s*(?:간|동안)",
            _past_span,
            right_boundary=True,
        ),
        _rule(
            TK.NUM, rf"(?<!\d)(\d{{1,4}})\s*({_DIGIT_UNITS})", lambda m: NumUnit(int(m[1]), m[2], digits=m[1])
        ),
        _rule(TK.NUM, rf"({SINO})\s*({_SINO_UNITS})", _sino_num, right_boundary=True),
        _rule(TK.NUM, rf"({NATIVE})\s*({_NATIVE_UNITS})", _native_num, right_boundary=True),
        _rule(TK.NUM, words(lx.DAY_TERMS), lambda m: NumUnit(lx.DAY_TERMS[m.group()], "일", term=True)),
        _rule(TK.NUM, r"반\s*년", lambda m: NumUnit(6, "개월")),
        # '3~5일'의 3
        _rule(
            TK.NUM,
            rf"(?<![\d:])(\d{{1,2}})(?=\s*{_RANGE_SEP}\s*\d{{1,2}}\s*일)",
            lambda m: NumUnit(int(m[1]), "일", digits=m[1]),
        ),
        _rule(TK.DIRECTION, words(lx.DIRECTIONS), lambda m: lx.DIRECTIONS[m.group()], right_boundary=True),
    ]


def _native_num(match: Match) -> NumUnit | None:
    amount = parse_native(match[1])
    return None if amount is None else NumUnit(amount, match[2])


def is_single_syllable_sino(token: Token) -> bool:
    """'오일', '삼일'처럼 한 글자 한자어 수사 + 일 → 월 문맥이 있어야 날짜로 봄"""
    value = token.value
    return (
        isinstance(value, NumUnit)
        and not value.digits
        and syllable_count(token.text) <= 2
        and value.unit == "일"
    )


# ---------------------------------------------------------------- 기념일


_MONTH_AHEAD = rf"(?:\d{{1,2}}|{_KOREAN_MONTH})\s*월(?!\s*(?:간|동안|째))"


def _holiday_rules(calendar: HolidayCalendar) -> list[TokenRule]:
    day_names, span_names = dict(calendar.names()), dict(calendar.span_names())
    if not day_names and not span_names:
        return []
    # 요일·기념일·시간대 앞 ('지난 금요일', '지난 추석', '지난 저녁')
    target = rf"(?:[월화수목금토일]\s*(?:요일|욜)|{words([*day_names, *span_names, *lx.PERIODS])})"
    return [
        _rule(
            TK.MODIFIER,
            # '지난 3일' = 오늘 이전 가장 최근의 3일 ('지난 3일간'은 PAST_SPAN)
            rf"(?:{words(lx.MODIFIERS)})\s*(?={target}|\d{{1,2}}\s*일(?!\s*(?:간|동안|째))|{_MONTH_AHEAD})",
            lambda m: lookup(lx.MODIFIERS, m.group()),
        ),
        _rule(TK.MODIFIER, rf"(?:{words(lx.UPCOMING_ANY)})(?=\s)", lambda m: 1),
        _rule(
            TK.YEAR_REL,
            rf"올(?=\s+(?:{_MONTH_AHEAD}|{words([*day_names, *span_names, *lx.YEAR_PART])}))",
            lambda m: 0,
        ),
        _rule(
            TK.HOLIDAY, rf"({words(day_names)})(?:\s*당일)?", lambda m: HolidayRef(lookup(day_names, m[1]))
        ),
        _rule(TK.HOLIDAY, words(span_names), lambda m: HolidayRef(lookup(span_names, m.group()), span=True)),
    ]


def _vague_rules() -> list[TokenRule]:
    return [
        _rule(
            TK.VAGUE, words(lx.VAGUE_WORDS), lambda m: lookup(lx.VAGUE_WORDS, m.group()), right_boundary=True
        )
    ]


def build_rules(compact_dates: bool, calendar: HolidayCalendar, vague: bool = False) -> tuple[TokenRule, ...]:
    return (
        *(_vague_rules() if vague else ()),
        *_formatted_rules(compact_dates),
        *_calendar_rules(),
        *_week_rules(),
        *_holiday_rules(calendar),
        *_time_rules(),
        *_duration_rules(),
    )
