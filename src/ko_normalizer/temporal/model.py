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
    VAGUE = (
        "vague"  # 막연한 때 ('최근', '향후'). ParseOptions(vague=True)일 때만. 값은 기준일, 뜻은 direction
    )


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

    @property
    def value(self) -> Date | Time | datetime:
        """kind에 맞는 대표값: date → date, time → time, datetime → datetime (모두 start 기준)"""
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
        return None if self.kind in (Kind.DATE, Kind.VAGUE) else self.start.timetz()

    def to_dict(self) -> dict[str, Any]:
        vague = {"direction": self.direction.value} if self.direction is not None else {}
        return {
            "text": self.text,
            "span": list(self.span),
            "kind": self.kind.value,
            "grain": self.grain.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "value": self.value.isoformat(),
            "is_range": self.is_range,
            "ambiguities": [a.value for a in self.ambiguities],
            **vague,
        }
