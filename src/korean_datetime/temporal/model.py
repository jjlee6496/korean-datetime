"""시간 표현 결과 모델

모든 결과는 반열린 구간 [start, end)와 정밀도(grain)로 표현합니다.
- "내일"          → [09-29 00:00, 09-30 00:00), grain=day,  kind=date
- "저녁 7시"      → [19:00, 20:00),             grain=hour, kind=time
- "이번 주말"     → [토 00:00, 월 00:00),        grain=day,  kind=date
- "3시부터 5시까지" → [15:00, 17:00), is_range=True
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from enum import Enum
from typing import Any

from .ambiguity import Ambiguity


class Kind(str, Enum):
    DATE = "date"  # 날짜만 (일/주/월/연 단위)
    TIME = "time"  # 시각만 (날짜는 기준일에서 추론)
    DATETIME = "datetime"  # 날짜와 시각이 모두 정해짐 ('내일 3시', '1시간 후', '지금')
    DURATION = "duration"  # 기간 값('6개월', '30분 동안'). 길이는 duration, start = end = 기준 시각
    VAGUE = (
        "vague"  # 막연한 때 ('최근', '향후'). ParseOptions(vague=True)일 때만. 값은 기준일, 뜻은 direction
    )


@dataclass(frozen=True, slots=True)
class Duration:
    """기간의 길이. 달은 날 수가 일정하지 않아 따로 셈 ('1개월' = months=1)"""

    months: int = 0
    days: int = 0
    seconds: int = 0

    @property
    def iso(self) -> str:
        """ISO 8601 길이 ('P6M', 'P2W', 'PT1H30M'). 주 단위로 떨어지는 날 수만 있으면 W"""
        if not self.months and not self.seconds and self.days and self.days % 7 == 0:
            return f"P{self.days // 7}W"
        parts = ((self.months // 12, "Y"), (self.months % 12, "M"), (self.days, "D"))
        date_part = "".join(f"{value}{unit}" for value, unit in parts if value)
        hours, rest = divmod(self.seconds, 3600)
        minutes, secs = divmod(rest, 60)
        time_part = "".join(f"{v}{u}" for v, u in ((hours, "H"), (minutes, "M"), (secs, "S")) if v)
        if not date_part and not time_part:
            return "P0D"
        return "P" + date_part + (f"T{time_part}" if time_part else "")


class Direction(str, Enum):
    """막연한 표현이 기준일에서 가리키는 쪽 (TIMEX3의 mod와 같은 구분)"""

    RECENT = "recent"  # 최근, 요즘: 기준일 무렵까지
    PAST = "past"  # 과거, 예전: 기준일보다 앞
    FUTURE = "future"  # 향후, 앞으로: 기준일보다 뒤


class Grain(str, Enum):
    YEAR = "year"
    HALF_YEAR = "half_year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"


@dataclass(frozen=True, slots=True)
class TemporalExpression:
    """텍스트에서 찾은 날짜/시간 표현"""

    text: str
    span: tuple[int, int]
    kind: Kind
    grain: Grain
    start: datetime
    end: datetime
    is_range: bool = False
    ambiguities: tuple[Ambiguity, ...] = ()  # 추정이 들어간 부분 (값은 그대로)
    direction: Direction | None = None  # kind=VAGUE일 때만
    duration: Duration | None = None  # kind=DURATION일 때만

    @property
    def value(self) -> Date | Time | datetime | Duration:
        """kind에 맞는 대표값: date·time·datetime은 start 기준 값, duration은 Duration"""
        if self.kind is Kind.DURATION and self.duration is not None:
            return self.duration
        if self.kind in (Kind.DATE, Kind.VAGUE):
            return self.start.date()
        if self.kind is Kind.TIME:
            return self.start.timetz()
        return self.start

    @property
    def date(self) -> Date:
        return self.start.date()

    @property
    def time(self) -> Time | None:
        return None if self.kind in (Kind.DATE, Kind.VAGUE, Kind.DURATION) else self.start.timetz()

    def to_dict(self) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if self.direction is not None:
            extra["direction"] = self.direction.value
        if self.duration is not None:
            extra["duration"] = self.duration.iso
        value = self.value
        shown = value.iso if isinstance(value, Duration) else value.isoformat()
        return {
            "text": self.text,
            "span": list(self.span),
            "kind": self.kind.value,
            "grain": self.grain.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "value": shown,
            "is_range": self.is_range,
            "ambiguities": [a.value for a in self.ambiguities],
            **extra,
        }
