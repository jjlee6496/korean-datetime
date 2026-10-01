"""날짜/시간 표현 파서 — 공개 API

    >>> from datetime import datetime
    >>> now = datetime(2026, 9, 28, 14, 30)
    >>> parse("다음주 월요일 저녁 7시 반", now=now).start
    datetime.datetime(2026, 10, 5, 19, 30)
    >>> parse_date("크리스마스", now=now)
    datetime.date(2026, 12, 25)

처리 흐름: scan(토큰화) → postprocess(기간 병합) → build_frames(슬롯 조립) → resolve(해석) → merge_ranges
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from functools import lru_cache

from ..core.scanner import Scanner
from ..core.types import require_text, to_datetime
from .frame import Frame, apply_corrections, build_frames, link_alternatives, link_day_shifts
from .holiday_calendar import BUILTIN_HOLIDAYS
from .model import Kind, TemporalExpression
from .options import DEFAULT_OPTIONS, Cycle, ParseOptions
from .postprocess import postprocess
from .ranges import merge_ranges
from .resolve import resolve
from .rules import build_rules


@lru_cache(maxsize=4)
def _builtin_scanner(compact_dates: bool, vague: bool) -> Scanner:
    return Scanner(build_rules(compact_dates, BUILTIN_HOLIDAYS, vague))


def _make_scanner(options: ParseOptions) -> Scanner:
    """내장 달력이면 공유 스캐너, 주입된 달력이면 그 달력의 이름으로 새로 만든 스캐너"""
    if options.holidays is None:
        return _builtin_scanner(options.compact_dates, options.vague)
    return Scanner(build_rules(options.compact_dates, options.holidays, options.vague))


class TemporalParser:
    """옵션을 고정한 재사용 가능한 파서 (상태 없음, 스레드 안전)"""

    def __init__(self, options: ParseOptions | None = None) -> None:
        if options is not None and not isinstance(options, ParseOptions):
            raise TypeError("options는 ParseOptions여야 합니다")
        self.options = options or DEFAULT_OPTIONS
        self._scanner = _make_scanner(self.options)

    def parse_all(self, text: str, now: datetime | date | None = None) -> list[TemporalExpression]:
        """텍스트의 모든 날짜/시간 표현을 위치 순으로 반환합니다."""
        require_text(text)
        reference = to_datetime(now, self.options.timezone)
        tokens = postprocess(self._scanner.scan(text), text)
        frames = apply_corrections(build_frames(tokens, text), text)
        frames = link_day_shifts(link_alternatives(frames, text), text)
        resolved = [(frame, result) for frame in frames if (result := self._resolve(frame, text, reference))]
        return merge_ranges(resolved, text, lambda frame, ref, cycle: self._resolve(frame, text, ref, cycle))

    def parse(self, text: str, now: datetime | date | None = None) -> TemporalExpression | None:
        """첫 번째 날짜/시간 표현. 없으면 None."""
        results = self.parse_all(text, now)
        return results[0] if results else None

    def _resolve(
        self, frame: Frame, text: str, now: datetime, cycle: Cycle | None = None
    ) -> TemporalExpression | None:
        options = self.options
        if cycle is not None and cycle is not options.cycle:
            options = replace(options, cycle=cycle)
        try:
            return resolve(frame, text, now, options)
        except (ValueError, OverflowError):  # 달력 범위를 벗어나는 값(9999년 이후 등)은 인식하지 않음
            return None


@lru_cache(maxsize=32)
def _parser_for(options: ParseOptions | None) -> TemporalParser:
    return TemporalParser(options)


def parse(
    text: str, now: datetime | date | None = None, options: ParseOptions | None = None
) -> TemporalExpression | None:
    return _parser_for(options).parse(text, now)


def parse_all(
    text: str, now: datetime | date | None = None, options: ParseOptions | None = None
) -> list[TemporalExpression]:
    return _parser_for(options).parse_all(text, now)


def parse_date(
    text: str, now: datetime | date | None = None, options: ParseOptions | None = None
) -> date | None:
    """첫 표현의 날짜 (시각만 있으면 추론된 날짜)"""
    result = parse(text, now, options)
    return result.date if result else None


def parse_time(
    text: str, now: datetime | date | None = None, options: ParseOptions | None = None
) -> time | None:
    """첫 표현의 시각. 날짜만 있는 표현이면 None."""
    result = parse(text, now, options)
    return result.time if result else None


def parse_datetime(
    text: str, now: datetime | date | None = None, options: ParseOptions | None = None
) -> datetime | None:
    """첫 표현의 시작 시각 (날짜만 있으면 00:00)"""
    result = parse(text, now, options)
    return result.start if result else None


__all__ = [
    "Kind",
    "TemporalParser",
    "parse",
    "parse_all",
    "parse_date",
    "parse_datetime",
    "parse_time",
]
