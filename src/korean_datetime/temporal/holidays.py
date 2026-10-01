"""기념일/명절 — data/holidays.json을 읽어 이름 → 날짜로 변환

기념일을 추가하려면 JSON에 항목만 추가하면 됩니다 (코드 수정 불필요).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from importlib import resources
from typing import Any

from .lunar import lunar_to_solar

# 패키지 이름을 적지 않고 현재 모듈 기준으로 찾음 → 다른 이름으로 복사(vendoring)해도 동작
_RESOURCE = (f"{__name__.rpartition('.')[0]}.data", "holidays.json")


@dataclass(frozen=True, slots=True)
class Holiday:
    key: str
    names: tuple[str, ...]
    calendar: str = "solar"
    month: int = 0
    day: int = 0
    span: tuple[int, int] = (0, 0)
    span_names: tuple[str, ...] = ()
    relative_to: str | None = None
    offset_days: int = 0


def _to_holiday(raw: dict[str, Any]) -> Holiday:
    holiday = Holiday(
        key=raw["key"],
        names=tuple(raw["names"]),
        calendar=raw.get("calendar", "solar"),
        month=int(raw.get("month", 0)),
        day=int(raw.get("day", 0)),
        span=(int(raw.get("span", (0, 0))[0]), int(raw.get("span", (0, 0))[1])),
        span_names=tuple(raw.get("span_names", ())),
        relative_to=raw.get("relative_to"),
        offset_days=int(raw.get("offset_days", 0)),
    )
    if holiday.relative_to is None and (holiday.calendar not in ("solar", "lunar") or not holiday.month):
        raise ValueError(f"기념일 정의 오류: {holiday.key}")
    return holiday


@lru_cache(maxsize=1)
def load_holidays() -> dict[str, Holiday]:
    package, filename = _RESOURCE
    try:
        raw = json.loads(resources.files(package).joinpath(filename).read_text(encoding="utf-8"))
        holidays = [_to_holiday(item) for item in raw["holidays"]]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"기념일 데이터를 읽을 수 없습니다: {package}/{filename}: {error}") from error
    return {h.key: h for h in holidays}


def holiday_names() -> tuple[dict[str, str], dict[str, str]]:
    """(이름 → key, 연휴 이름 → key)"""
    holidays = load_holidays().values()
    day_names = {name: h.key for h in holidays for name in h.names}
    span_names = {name: h.key for h in holidays for name in h.span_names}
    return day_names, span_names


def holiday_date(key: str, year: int) -> date:
    """year년의 기념일 날짜 (음력은 양력으로 변환)"""
    holiday = load_holidays()[key]
    if holiday.relative_to is not None:
        return holiday_date(holiday.relative_to, year) + timedelta(days=holiday.offset_days)
    if holiday.calendar == "lunar":
        return lunar_to_solar(year, holiday.month, holiday.day)
    return date(year, holiday.month, holiday.day)


def holiday_span(key: str, year: int, *, as_holidays: bool) -> tuple[date, date]:
    """[시작, 끝) 날짜. as_holidays면 연휴 기간."""
    day = holiday_date(key, year)
    before, after = load_holidays()[key].span if as_holidays else (0, 0)
    return day - timedelta(days=before), day + timedelta(days=after + 1)
