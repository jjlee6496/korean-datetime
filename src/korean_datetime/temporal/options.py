"""해석 옵션"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo
from enum import Enum

from .holiday_calendar import BUILTIN_HOLIDAYS, HolidayCalendar


class AmbiguousHour(str, Enum):
    """오전/오후가 없는 1~12시('3시')를 해석하는 방법"""

    NEAREST_FUTURE = "nearest_future"
    """기준일(또는 날짜 미지정)이면 기준 시각 이후 가장 가까운 시각. 다른 날짜면 DAYTIME 규칙."""
    DAYTIME = "daytime"
    """daytime_start 이상이면 오전, 미만이면 오후 (기본 7: 7~11시 오전, 1~6시 오후)"""
    PM = "pm"
    """1~11시는 항상 오후"""
    AS_IS = "as_is"
    """숫자 그대로 (3시 → 03:00)"""
    CONTEXT = "context"
    """같은 텍스트 안의 단서로 정함: 앞에 오전/오후가 정해진 시각이 있으면 그 뒤로 이어지는 쪽,
    없으면 가장 가까운 시간대 말('저녁 먹으러 8시' → 20시), 둘 다 없으면 DAYTIME (context_hour 모듈)"""


class Cycle(str, Enum):
    """연/월/날짜가 생략된 표현('15일', '6월 3일', '금요일', '추석')을 어느 주기로 볼지"""

    FUTURE = "future"
    """이미 지났으면 다음 주기 (채팅·예약: '15일에 보자'@20일 → 다음 달 15일)"""
    PAST = "past"
    """오늘이나 그 전의 가장 최근 주기 (기록·일지: '15일에 다녀왔다'@10일 → 지난달 15일)"""
    NEAREST = "nearest"
    """이번·이전·다음 주기 중 오늘에서 가장 가까운 것, 같으면 미래 (뉴스: '29일'@1일 → 지난달 29일)"""
    CURRENT = "current"
    """넘기지 않고 이번 주기 그대로 ('15일'@20일 → 이번 달 15일)"""


@dataclass(frozen=True, slots=True)
class ParseOptions:
    """
    Attributes:
        cycle: 연/월/날짜가 생략된 표현의 주기 (Cycle 참고).
            '지난', '다가오는'처럼 문장에 방향이 있으면 그쪽을 따름
        ambiguous_hour: 오전/오후가 없는 시각의 해석 규칙
        daytime_start: DAYTIME 규칙에서 오전으로 볼 최소 시각 (0~12)
        compact_dates: 구분자 없는 4·6자리 숫자(1015, 261015)를 날짜로 인식 (오탐이 많아 기본 꺼짐)
        vague: '최근', '요즘', '향후' 같은 막연한 때를 Kind.VAGUE로 인식 (값은 기준일, 방향은 direction)
        holidays: 기념일/공휴일 달력. None이면 내장 달력. 외부 데이터 주입은 holiday_calendar 모듈 참고
        timezone: now도 reference_time()도 없을 때 서버 시각을 읽을 시간대 (예: KST). None이면 서버 로컬 시각
    """

    cycle: Cycle = Cycle.FUTURE
    ambiguous_hour: AmbiguousHour = AmbiguousHour.NEAREST_FUTURE
    daytime_start: int = 7
    compact_dates: bool = False
    vague: bool = False
    holidays: HolidayCalendar | None = None
    timezone: tzinfo | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle", _enum(Cycle, self.cycle, "cycle"))
        try:
            policy = AmbiguousHour(self.ambiguous_hour)
        except ValueError as error:
            choices = ", ".join(p.value for p in AmbiguousHour)
            raise ValueError(
                f"ambiguous_hour는 {choices} 중 하나여야 합니다: {self.ambiguous_hour!r}"
            ) from error
        object.__setattr__(self, "ambiguous_hour", policy)
        if not isinstance(self.daytime_start, int) or not 0 <= self.daytime_start <= 12:
            raise ValueError(f"daytime_start는 0~12 사이 정수여야 합니다: {self.daytime_start!r}")
        if self.timezone is not None and not isinstance(self.timezone, tzinfo):
            raise TypeError(f"timezone은 tzinfo여야 합니다 (예: ZoneInfo('Asia/Seoul')): {self.timezone!r}")
        if self.holidays is not None and not isinstance(self.holidays, HolidayCalendar):
            raise TypeError("holidays는 HolidayCalendar(names, span_names, span)를 구현해야 합니다")
        for name in ("compact_dates", "vague"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name}은(는) bool이어야 합니다")


def _enum(kind: type[Cycle], value: object, name: str) -> Cycle:
    try:
        return kind(value)
    except ValueError as error:
        choices = ", ".join(member.value for member in kind)
        raise ValueError(f"{name}는 {choices} 중 하나여야 합니다: {value!r}") from error


DEFAULT_OPTIONS = ParseOptions()


def holiday_calendar(options: ParseOptions) -> HolidayCalendar:
    return options.holidays if options.holidays is not None else BUILTIN_HOLIDAYS
