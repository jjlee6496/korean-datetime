from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ko_normalizer import Kind, ParseOptions, TemporalExpression, parse

# 기준 시각: 2026-09-28 (월요일) 14:30 — 정답셋(tests/data/temporal_gold.jsonl)과 동일
NOW = datetime(2026, 9, 28, 14, 30)
TODAY = NOW.date()


def p(text: str, now: datetime = NOW, **options: object) -> TemporalExpression | None:
    opts = ParseOptions(**options) if options else None  # type: ignore[arg-type]
    return parse(text, now=now, options=opts)


def must(text: str, now: datetime = NOW, **options: object) -> TemporalExpression:
    result = p(text, now, **options)
    assert result is not None, f"인식 실패: {text!r}"
    return result


def as_date(text: str, **options: object) -> date:
    result = must(text, **options)
    assert result.kind is Kind.DATE, f"{text!r}: kind={result.kind}"
    return result.start.date()


def date_span(text: str, **options: object) -> tuple[date, date]:
    result = must(text, **options)
    return result.start.date(), result.end.date()


def dt(text: str, now: datetime = NOW, **options: object) -> datetime:
    return must(text, now, **options).start


def d(y: int, m: int, day: int) -> date:
    return date(y, m, day)


def at(y: int, m: int, day: int, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(y, m, day, hh, mm, ss)


def hm(hh: int, mm: int = 0) -> time:
    return time(hh, mm)


def days(n: int) -> date:
    """기준일로부터 n일 뒤"""
    return TODAY + timedelta(days=n)
