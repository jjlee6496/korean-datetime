"""기대값 식 — 기준 시각에 무관한 정답 정의

정답셋에 절대 날짜 대신 "기준 시각(ref)에서 계산하는 식"을 적으면,
어떤 기준 시각으로도 같은 정답셋을 돌릴 수 있습니다.

    {"text": "내일",                 "expect": "today + 1d"}
    {"text": "금요일",               "expect": "next(FRI)"}
    {"text": "다음달 첫째주 금요일", "expect": "month(1).nth(1, FRI)"}
    {"text": "6월 3일",              "expect": "future(md(6, 3))"}
    {"text": "3시",                  "expect": "nearest(3:00)"}
    {"text": "인식하면 안 되는 말",   "expect": "none"}

파서의 해석 코드와 독립되도록 표준 라이브러리 calendar만으로 계산합니다 (음력만 lunar_to_solar 사용).

전체 문법·타입·함수 목록과 정답셋 관리 방법: docs/expectation-dsl.md
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

from .lunar import lunar_to_solar

WEEKDAY_NAMES = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
_MAX_SHIFT = 4
_DAYTIME_START = 7


class ExpectationError(ValueError):
    """식 문법이나 사용법 오류"""


@dataclass(frozen=True, slots=True)
class Expect:
    start: datetime
    end: datetime | None  # None이면 시작 시각만 비교 (시각 표현)
    kind: str  # date | time | datetime
    grain: str  # day | week | month | year | instant | period | range
    month_first: date | None = None  # .row()로 만든 주: 그 달의 1일 (앞 달 칸 판정용)
    ambiguities: frozenset[str] = frozenset()  # 기준 시각에 따라 생기는 모호성 (future 넘김, 같은 요일 …)

    def flagged(self, *names: str) -> Expect:
        return replace(self, ambiguities=self.ambiguities | set(names))

    def as_expected(self) -> dict[str, str | bool | list[str]]:
        """평가기(temporal_matches)가 비교할 정답. shape: instant(시각) | span(구간)"""
        expected: dict[str, str | bool | list[str]] = {
            "start": self.start.isoformat(),
            "kind": self.kind,
            "shape": "instant" if self.end is None else "span",
            "is_range": self.grain == "range",
            "ambiguities": sorted(self.ambiguities),
        }
        if self.end is not None:
            expected["end"] = self.end.isoformat()
        return expected


# ---------------------------------------------------------------- 파싱

_TOKEN = re.compile(r"\s*(?:(\d{1,2}:\d{2})|(\d+)(min|mo|d|w|y|h|s)\b|(\d+)|([A-Za-z_]\w*)|(\S))")
Node = tuple[Any, ...]


def _tokenize(text: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None or match.end() == pos:
            break
        clock, amount, unit, number, ident, symbol = match.groups()
        if clock:
            hour, minute = clock.split(":")
            tokens.append(("time", (int(hour), int(minute))))
        elif amount:
            tokens.append(("offset", (int(amount), unit)))
        elif number:
            tokens.append(("int", int(number)))
        elif ident:
            tokens.append(("ident", ident))
        elif symbol:
            tokens.append(("sym", symbol))
        pos = match.end()
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self, offset: int = 0) -> tuple[str, Any]:
        j = self.i + offset
        return self.tokens[j] if j < len(self.tokens) else ("end", None)

    def take(self, kind: str, value: Any = None) -> Any:
        token = self.peek()
        if token[0] != kind or (value is not None and token[1] != value):
            raise ExpectationError(f"{value or kind}이(가) 필요합니다: {token}")
        self.i += 1
        return token[1]

    def parse(self) -> Node:
        node = self.expr()
        if self.peek()[0] != "end":
            raise ExpectationError(f"해석할 수 없는 부분: {self.tokens[self.i :]}")
        return node

    def expr(self) -> Node:
        node = self.chain()
        while self.peek() in (("sym", "+"), ("sym", "-")):
            sign = 1 if self.take("sym") == "+" else -1
            amount, unit = self.take("offset")
            node = ("offset", node, sign * amount, unit)
        return node

    def chain(self) -> Node:
        node = self.atom()
        while self.peek() == ("sym", "."):
            self.take("sym", ".")
            name = self.take("ident")
            node = ("method", node, name, self.args())
        return node

    def atom(self) -> Node:
        if self.peek() == ("sym", "("):
            self.take("sym", "(")
            node = self.expr()
            self.take("sym", ")")
            return node
        name = self.take("ident")
        args = self.args() if self.peek() == ("sym", "(") else []
        return ("atom", name, args)

    def args(self) -> list[Node]:
        self.take("sym", "(")
        args: list[Node] = []
        while self.peek() != ("sym", ")"):
            args.append(self.arg())
            if self.peek() == ("sym", ","):
                self.take("sym", ",")
        self.take("sym", ")")
        return args

    def arg(self) -> Node:
        kind, value = self.peek()
        if kind == "time":
            self.i += 1
            return ("time", value)
        if kind == "sym" and value in "+-" and self.peek(1)[0] == "int":
            self.i += 2
            return ("int", self.tokens[self.i - 1][1] * (1 if value == "+" else -1))
        if kind == "int":
            self.i += 1
            return ("int", value)
        if kind == "ident" and self.peek(1) not in (("sym", "("), ("sym", ".")) and value not in _ATOMS:
            self.i += 1
            return ("word", value)
        return ("expr", self.expr())


# ---------------------------------------------------------------- 달력 계산 (파서와 독립)


def _midnight(day: date, like: datetime) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=like.tzinfo)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _day_span(day: date, ref: datetime) -> Expect:
    return Expect(_midnight(day, ref), _midnight(day + timedelta(days=1), ref), "date", "day")


def _span(start: date, end: date, ref: datetime, grain: str) -> Expect:
    return Expect(_midnight(start, ref), _midnight(end, ref), "date", grain)


def _month_span(first: date, ref: datetime) -> Expect:
    return _span(first, _add_months(first, 1), ref, "month")


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _floor(ref: datetime) -> datetime:
    return ref.replace(second=0, microsecond=0)


# ---------------------------------------------------------------- 평가


def _int(node: Node) -> int:
    if node[0] != "int":
        raise ExpectationError(f"정수가 필요합니다: {node}")
    return int(node[1])


def _word(node: Node) -> str:
    if node[0] != "word":
        raise ExpectationError(f"단어가 필요합니다: {node}")
    return str(node[1])


def _weekday(node: Node) -> int:
    name = _word(node)
    if name not in WEEKDAY_NAMES:
        raise ExpectationError(f"요일은 MON~SUN이어야 합니다: {name}")
    return WEEKDAY_NAMES[name]


_MAX_HOUR = 47  # 24 이상은 다음 날 (25:00 = 다음 날 1시)


def _clock(node: Node, max_hour: int = _MAX_HOUR) -> tuple[int, int]:
    hour, minute = node[1] if node[0] == "time" else (_int(node), 0)
    if not (0 <= hour <= max_hour and 0 <= minute <= 59):
        raise ExpectationError(f"시각 범위를 벗어났습니다 (0~{max_hour}시, 0~59분): {hour}:{minute:02d}")
    return hour, minute


def _arity(args: list[Node], count: int, name: str) -> None:
    if len(args) != count:
        raise ExpectationError(f"{name}은(는) 인자 {count}개가 필요합니다")


def _at(day: date, clock: tuple[int, int], ref: datetime) -> datetime:
    return _midnight(day, ref) + timedelta(hours=clock[0], minutes=clock[1])


def _nearest(ref: datetime, clock: tuple[int, int]) -> tuple[datetime, bool]:
    """(가장 가까운 미래 후보, 내일 후보인지)"""
    base = clock[0] % 12
    for d in (0, 1):
        for add in (0, 12):
            candidate = _at(ref.date() + timedelta(days=d), (base + add, clock[1]), ref)
            if candidate >= _floor(ref):
                return candidate, d == 1
    raise AssertionError("unreachable")


def _day_attribution(result: Expect, hour: int) -> Expect:
    return result.flagged("day_attribution") if hour >= 24 else result


_ATOMS: dict[str, tuple[str | None, Callable[[list[Node], datetime], Expect | None]]] = {}


def _atom(name: str, cycle: str | None) -> Callable[[Callable[[list[Node], datetime], Expect | None]], Any]:
    def register(fn: Callable[[list[Node], datetime], Expect | None]) -> Any:
        _ATOMS[name] = (cycle, fn)
        return fn

    return register


@_atom("today", "day")
def _today(args: list[Node], ref: datetime) -> Expect | None:
    return _day_span(ref.date(), ref)


@_atom("now", None)
def _now(args: list[Node], ref: datetime) -> Expect | None:
    return Expect(_floor(ref), None, "datetime", "instant")


@_atom("none", None)
def _none(args: list[Node], ref: datetime) -> Expect | None:
    return None


@_atom("day", "month")
def _day_atom(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "day")
    found = _safe_date(ref.year, ref.month, _int(args[0]))
    return _day_span(found, ref) if found else None


@_atom("md", "year")
def _md(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 2, "md")
    found = _safe_date(ref.year, _int(args[0]), _int(args[1]))
    return _day_span(found, ref) if found else None


@_atom("ymd", None)
def _ymd(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 3, "ymd")
    found = _safe_date(_int(args[0]), _int(args[1]), _int(args[2]))
    return _day_span(found, ref) if found else None


@_atom("week", "week")
def _week(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "week")
    monday = ref.date() - timedelta(days=ref.weekday()) + timedelta(weeks=_int(args[0]))
    return _span(monday, monday + timedelta(days=7), ref, "week")


@_atom("month", "month")
def _month(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "month")
    return _month_span(_add_months(ref.date().replace(day=1), _int(args[0])), ref)


@_atom("mon", "year")
def _mon(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "mon")
    return _month_span(date(ref.year, _int(args[0]), 1), ref)


@_atom("year", "year")
def _year(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "year")
    year = ref.year + _int(args[0])
    return _span(date(year, 1, 1), date(year + 1, 1, 1), ref, "year")


@_atom("yr", None)
def _yr(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "yr")
    year = _int(args[0])
    return _span(date(year, 1, 1), date(year + 1, 1, 1), ref, "year")


@_atom("next", "week")
def _next(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "next")
    today = ref.date()
    for d in range(1, 8):
        if (today + timedelta(days=d)).weekday() == _weekday(args[0]):
            result = _day_span(today + timedelta(days=d), ref)
            return result.flagged("same_weekday") if d == 7 else result  # 오늘과 같은 요일 → 다음 주
    raise AssertionError("unreachable")


@_atom("prev", "week")
def _prev(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "prev")
    today = ref.date()
    for d in range(1, 8):
        if (today - timedelta(days=d)).weekday() == _weekday(args[0]):
            return _day_span(today - timedelta(days=d), ref)
    raise AssertionError("unreachable")


@_atom("at", "day")
def _at_atom(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "at")
    clock = _clock(args[0])
    return _day_attribution(Expect(_at(ref.date(), clock, ref), None, "time", "instant"), clock[0])


@_atom("nearest", None)
def _nearest_atom(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "nearest")
    clock = _clock(args[0], max_hour=12)
    moment, tomorrow = _nearest(ref, clock)
    result = Expect(moment, None, "time", "instant").flagged(_meridiem_flag(clock[0]))
    return result.flagged("cycle_shifted") if tomorrow else result


def _meridiem_flag(hour: int) -> str:
    """오전/오후가 없는 시각: 12시는 정오/자정, 나머지는 오전/오후"""
    return "noon_or_midnight" if hour % 12 == 0 else "meridiem"


@_atom("period", "day")
def _period(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 2, "period")
    begin, finish = _period_hours(args)
    result = Expect(_at(ref.date(), begin, ref), _at(ref.date(), finish, ref), "time", "period")
    return _day_attribution(result, begin[0])


def _period_hours(args: list[Node]) -> tuple[tuple[int, int], tuple[int, int]]:
    begin, end = _clock(args[0]), _clock(args[1])
    if begin >= end:
        raise ExpectationError(f"시간대는 시작 < 끝이어야 합니다: {begin[0]}~{end[0]}")
    return begin, end


@_atom("lunar", "year")
def _lunar(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 2, "lunar")
    return _day_span(lunar_to_solar(ref.year, _int(args[0]), _int(args[1])), ref)


def _cycle(node: Node) -> str | None:
    if node[0] == "atom":
        if node[1] in _CYCLE_CHOICES:
            raise ExpectationError(f"{node[1]}는 중첩할 수 없습니다")
        return _ATOMS[node[1]][0] if node[1] in _ATOMS else None
    return _cycle(node[1])


def _shift(ref: datetime, cycle: str, k: int) -> datetime:
    if cycle == "year":
        return ref.replace(
            year=ref.year + k, day=min(ref.day, calendar.monthrange(ref.year + k, ref.month)[1])
        )
    if cycle == "month":
        return datetime.combine(_add_months(ref.date(), k), ref.timetz())
    return ref + timedelta(days=k * (7 if cycle == "week" else 1))


def _ended(result: Expect, ref: datetime) -> bool:
    if result.kind == "date" and result.end is not None:
        return result.end <= _midnight(ref.date(), ref)
    if result.end is None:
        return result.start < _floor(ref)
    return result.end <= ref


def _future(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "future")
    inner = args[0][1] if args[0][0] == "expr" else args[0]
    cycle = _cycle(inner)
    if cycle is None:
        raise ExpectationError(f"future에 넣을 수 없는 식입니다 (주기 없음): {inner}")
    for k in range(_MAX_SHIFT + 1):
        result = _eval(inner, _shift(ref, cycle, k))
        if result is not None and not _ended(result, ref):
            return result.flagged("cycle_shifted") if k > 0 else result
    return None


def _past(args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "past")
    inner = args[0][1] if args[0][0] == "expr" else args[0]
    cycle = _cycle(inner)
    if cycle is None:
        raise ExpectationError(f"past에 넣을 수 없는 식입니다 (주기 없음): {inner}")
    result = _eval(inner, ref)
    if result is not None and result.start < _midnight(ref.date(), ref):
        return result
    for k in range(1, _MAX_SHIFT + 1):  # 이전 주기에 없으면('지난 2월 29일') 있는 주기까지
        result = _eval(inner, _shift(ref, cycle, -k))
        if result is not None:
            return result
    return None


def _cycle_arg(args: list[Node], name: str) -> tuple[Node, str]:
    _arity(args, 1, name)
    inner = args[0][1] if args[0][0] == "expr" else args[0]
    cycle = _cycle(inner)
    if cycle is None:
        raise ExpectationError(f"{name}에 넣을 수 없는 식입니다 (주기 없음): {inner}")
    return inner, cycle


def _existing(inner: Node, ref: datetime, cycle: str, ks: range) -> tuple[int, Expect] | None:
    """ks 순서로 주기를 옮겨 가며 X가 있는 첫 주기 (없는 날짜 '2월 29일'은 건너뜀)"""
    for k in ks:
        result = _eval(inner, _shift(ref, cycle, k))
        if result is not None:
            return k, result
    return None


def _latest(args: list[Node], ref: datetime) -> Expect | None:
    """오늘이나 그 전에 시작하는 가장 최근 주기 (Cycle.PAST)"""
    inner, cycle = _cycle_arg(args, "latest")
    tomorrow = _midnight(ref.date() + timedelta(days=1), ref)
    for k in range(0, -_MAX_SHIFT - 1, -1):
        result = _eval(inner, _shift(ref, cycle, k))
        if result is not None and result.start < tomorrow:
            return result.flagged("cycle_shifted") if k else result
    return None


def _day_distance(result: Expect, ref: datetime) -> int:
    """오늘과 X 사이의 날 수 (X가 오늘을 포함하면 0)"""
    today = ref.date()
    first = result.start.date()
    last = (result.end - timedelta(microseconds=1)).date() if result.end is not None else first
    return 0 if first <= today <= last else (first - today).days if first > today else (today - last).days


def _closest(args: list[Node], ref: datetime) -> Expect | None:
    """이번·이전·다음 주기 중 오늘에서 가장 가까운 것, 같으면 미래 쪽 (Cycle.NEAREST)"""
    inner, cycle = _cycle_arg(args, "closest")
    found = [
        hit
        for hit in (
            _existing(inner, ref, cycle, range(0, 1)),
            _existing(inner, ref, cycle, range(-1, -_MAX_SHIFT - 1, -1)),
            _existing(inner, ref, cycle, range(1, _MAX_SHIFT + 1)),
        )
        if hit is not None
    ]
    if not found:
        return None
    k, result = min(found, key=lambda hit: (_day_distance(hit[1], ref), -hit[0]))
    return result.flagged("cycle_shifted") if k else result


_CYCLE_CHOICES = {"future": _future, "past": _past, "latest": _latest, "closest": _closest}


def _eval(node: Node, ref: datetime) -> Expect | None:
    kind = node[0]
    if kind == "atom":
        name, args = node[1], node[2]
        if name in _CYCLE_CHOICES:
            return _CYCLE_CHOICES[name](args, ref)
        if name not in _ATOMS:
            raise ExpectationError(f"알 수 없는 이름: {name}")
        if name in ("today", "now", "none"):
            _arity(args, 0, name)
        return _ATOMS[name][1](args, ref)
    if kind == "offset":
        target = _eval(node[1], ref)
        return None if target is None else _apply_offset(target, node[2], node[3])
    if kind == "method":
        target = _eval(node[1], ref)
        _check_method(target, node[2], node[3])
        if target is None:
            return None
        result = _method(target, node[2], node[3], ref)
        return (
            None if result is None else replace(result, ambiguities=result.ambiguities | target.ambiguities)
        )
    raise ExpectationError(f"식이 아닙니다: {node}")


def _apply_offset(target: Expect, amount: int, unit: str) -> Expect:
    """시작을 옮기고 구간 길이는 유지 (월 단위 이동의 말일 보정이 끝에 따로 적용되지 않도록)"""
    if unit in ("mo", "y"):
        months = amount * (12 if unit == "y" else 1)
        start = datetime.combine(_add_months(target.start.date(), months), target.start.timetz())
    else:
        seconds = {"d": 86400, "w": 604800, "h": 3600, "min": 60, "s": 1}[unit]
        start = target.start + timedelta(seconds=amount * seconds)
    end = start + (target.end - target.start) if target.end is not None else None
    return replace(target, start=start, end=end)


_METHOD_ARITY = {
    "weekday": 1, "weekend": 0, "weekdays": 0, "early": 0,
    "day": 1, "nth": 2, "row": 1, "nthweekend": 1, "first": 0, "last": 0, "part": 1,
    "month": 1, "half": 1, "quarter": 1, "lunar": 2,
    "at": 1, "hour": 1, "period": 2, "around": 2,
    "to": 1, "to_after": 1,
}  # fmt: skip
_PARTS = {"early", "mid", "late"}

_METHOD_GRAIN = {
    **dict.fromkeys(("weekday", "weekend", "weekdays", "early"), "week"),
    **dict.fromkeys(("day", "nth", "row", "nthweekend", "first", "last", "part"), "month"),
    **dict.fromkeys(("month", "half", "quarter", "lunar"), "year"),
    **dict.fromkeys(("at", "hour", "period"), ("day", "week")),
    "around": "day",
    "to": None,
    "to_after": None,
}


def _check_method(target: Expect | None, name: str, args: list[Node]) -> None:
    if name not in _METHOD_GRAIN:
        raise ExpectationError(f"알 수 없는 메서드: .{name}()")
    _arity(args, _METHOD_ARITY[name], f".{name}()")
    needed = _METHOD_GRAIN[name]
    allowed = (needed,) if isinstance(needed, str) else needed
    if target is not None and allowed is not None and target.grain not in allowed:
        raise ExpectationError(f".{name}()은(는) {needed} 구간에만 쓸 수 있습니다 (현재 {target.grain})")


def _method(target: Expect, name: str, args: list[Node], ref: datetime) -> Expect | None:
    if name in ("to", "to_after"):
        return _range(target, args, target.start if name == "to_after" else ref)
    start = target.start.date()
    if target.grain == "week" and name not in ("at", "hour", "period"):
        return _week_method(start, name, args, ref, target.month_first)
    if target.grain == "month":
        return _month_method(start, name, args, ref)
    if target.grain == "year":
        return _year_method(start.year, name, args, ref)
    result = _day_method(target, name, args, ref)
    multi_day = target.end is not None and target.end - target.start > timedelta(days=1)
    if result is not None and multi_day and name in ("at", "hour", "period"):
        return result.flagged("multi_day_time")  # 여러 날 구간에 시각 → 첫날로 정함
    return result


def _week_method(
    monday: date, name: str, args: list[Node], ref: datetime, month_first: date | None
) -> Expect | None:
    if name == "weekday":
        day = monday + timedelta(days=_weekday(args[0]))
        if month_first is None:
            return _day_span(day, ref)
        spill = day.month != month_first.month or day.year != month_first.year
        if day < month_first and day < ref.date():
            day += timedelta(days=7)  # 달력 첫 줄의 앞 달 칸이 이미 지났으면 다음 주
        result = _day_span(day, ref)
        return result.flagged("calendar_row_spill") if spill else result
    begin, length = {"weekend": (5, 2), "weekdays": (0, 5), "early": (0, 2)}[name]
    return _span(monday + timedelta(days=begin), monday + timedelta(days=begin + length), ref, "day")


def _nth_weekday(first: date, weekday: int, nth: int) -> date | None:
    days = [
        date(first.year, first.month, d)
        for d in range(1, calendar.monthrange(first.year, first.month)[1] + 1)
    ]
    matches = [d for d in days if d.weekday() == weekday]
    index = nth - 1 if nth > 0 else nth
    return matches[index] if -len(matches) <= index < len(matches) else None


def _month_method(first: date, name: str, args: list[Node], ref: datetime) -> Expect | None:
    last_day = calendar.monthrange(first.year, first.month)[1]
    if name == "day":
        found = _safe_date(first.year, first.month, _int(args[0]))
        return _day_span(found, ref) if found else None
    if name == "first":
        return _day_span(first, ref)
    if name == "last":
        return _day_span(first.replace(day=last_day), ref)
    if name == "part":
        part = _word(args[0])
        if part not in _PARTS:
            raise ExpectationError(f".part()는 early, mid, late 중 하나여야 합니다: {part}")
        begin, end = {"early": (1, 11), "mid": (11, 21), "late": (21, last_day + 1)}[part]
        return _span(first.replace(day=begin), first + timedelta(days=end - 1), ref, "day")
    if name == "nth":
        found = _nth_weekday(first, _weekday(args[1]), _int(args[0]))
        return _day_span(found, ref) if found else None
    if name == "row":
        monday = _calendar_row(first, _int(args[0]))
        if monday is None:
            return None
        return replace(_span(monday, monday + timedelta(days=7), ref, "week"), month_first=first)
    saturday = _nth_weekday(first, 5, _int(args[0]))
    return _span(saturday, saturday + timedelta(days=2), ref, "day") if saturday else None


def _calendar_row(first: date, n: int) -> date | None:
    """달력의 n번째 줄(월~일)의 월요일. 1일이 든 줄이 1, 말일이 든 줄이 -1. 그 달과 겹치지 않으면 None."""
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    first_row = first - timedelta(days=first.weekday())
    last_row = last - timedelta(days=last.weekday())
    if n == 0:
        raise ExpectationError(".row()의 N은 0일 수 없습니다 (1부터, 마지막은 -1)")
    monday = first_row + timedelta(weeks=n - 1) if n > 0 else last_row + timedelta(weeks=n + 1)
    return monday if first_row <= monday <= last_row else None


def _year_method(year: int, name: str, args: list[Node], ref: datetime) -> Expect | None:
    if name == "lunar":
        return _day_span(lunar_to_solar(year, _int(args[0]), _int(args[1])), ref)
    if name == "month":
        return _month_span(date(year, _int(args[0]), 1), ref)
    size = 6 if name == "half" else 3
    index = _int(args[0])
    if not 1 <= index <= 12 // size:
        raise ExpectationError(f".{name}()의 범위는 1~{12 // size}입니다: {index}")
    first = date(year, (index - 1) * size + 1, 1)
    return _span(first, _add_months(first, size), ref, name)


def _day_method(target: Expect, name: str, args: list[Node], ref: datetime) -> Expect | None:
    day = target.start.date()
    if name == "at":
        clock = _clock(args[0])
        return _day_attribution(Expect(_at(day, clock, ref), None, "datetime", "instant"), clock[0])
    if name == "hour":
        clock = _clock(args[0], max_hour=12)
        return Expect(_hour_on(day, clock, ref), None, "datetime", "instant").flagged(
            _meridiem_flag(clock[0])
        )
    if name == "period":
        begin, finish = _period_hours(args)
        return _day_attribution(
            Expect(_at(day, begin, ref), _at(day, finish, ref), "datetime", "period"), begin[0]
        )
    before, after = _int(args[0]), _int(args[1])
    if before < 0 or after < 0:
        raise ExpectationError(f".around()의 일수는 0 이상이어야 합니다: {before}, {after}")
    return _span(day - timedelta(days=before), day + timedelta(days=after + 1), ref, "day")


def _hour_on(day: date, clock: tuple[int, int], ref: datetime) -> datetime:
    """날짜가 정해진 모호한 시각: 오늘이면 가까운 미래 후보, 아니면 주간(7~18시) 규칙"""
    hour = clock[0]
    if day == ref.date():
        upcoming = [
            c
            for c in (_at(day, (hour % 12, clock[1]), ref), _at(day, (hour % 12 + 12, clock[1]), ref))
            if c >= _floor(ref)
        ]
        if upcoming:
            return upcoming[0]
    daytime = hour if hour >= _DAYTIME_START or hour == 12 else hour + 12
    return _at(day, (daytime, clock[1]), ref)


def _range(target: Expect, args: list[Node], ref: datetime) -> Expect | None:
    _arity(args, 1, "to")
    other_node = args[0][1] if args[0][0] == "expr" else args[0]
    other = _eval(other_node, ref)
    if other is None:
        return None
    end = other.end if other.kind == "date" else other.start
    if end is None or end <= target.start:  # 파서는 뒤집힌·빈 범위를 만들지 않음 → 식이 틀린 것
        raise ExpectationError(f"범위의 끝({end})이 시작({target.start})보다 앞서거나 같습니다 (기준 {ref})")
    kind = target.kind if target.kind != "date" or other.kind == "date" else "datetime"
    return Expect(target.start, end, kind, "range", ambiguities=target.ambiguities | other.ambiguities)


def evaluate_expectation(expression: str, ref: datetime) -> Expect | None:
    """식을 기준 시각 ref에서 계산합니다. 'none'이면 None (인식하지 않아야 함)."""
    return _eval(_Parser(expression).parse(), ref)
