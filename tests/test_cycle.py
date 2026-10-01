"""ParseOptions.cycle: 생략된 연/월/날짜의 주기 선택을 기준 시각 292개에서 식과 대조

정답셋은 기본값(FUTURE)으로 평가하므로, 다른 주기 선택은 여기서 같은 식을 감싸 검증합니다.
    FUTURE → future(X), PAST → latest(X), NEAREST → closest(X), CURRENT → X
"""

from __future__ import annotations

import pytest
from references import sampled_references

from korean_datetime import Cycle, ParseOptions, TemporalParser
from korean_datetime.core.evaluation import GoldCase
from korean_datetime.temporal.evaluation import evaluate_temporal
from korean_datetime.temporal.expectation import evaluate_expectation

# (문장, 주기를 감쌀 식, 뒤에 붙일 메서드). 주기는 날짜 단위로 고르고 시각은 그 뒤에 붙음
OMITTED: list[tuple[str, ...]] = [
    ("29일", "day(29)"),
    ("15일", "day(15)"),
    ("31일", "day(31)"),
    ("10월 13일", "md(10, 13)"),
    ("2월 29일", "md(2, 29)"),
    ("12월", "mon(12)"),
    ("크리스마스", "md(12, 25)"),
    ("추석", "lunar(8, 15)"),
    ("금요일", "week(0).weekday(FRI)"),
    ("15일 오후 3시", "day(15)", ".at(15:00)"),
]
WRAP = {
    Cycle.FUTURE: "future({})",
    Cycle.PAST: "latest({})",
    Cycle.NEAREST: "closest({})",
    Cycle.CURRENT: "{}",
}


def _cases(rows: list[tuple[str, ...]], wrap: str) -> list[GoldCase]:
    cases = []
    for ref in sampled_references():
        for text, inner, *suffix in rows:
            expected = evaluate_expectation(wrap.format(inner) + "".join(suffix), ref)
            cases.append(GoldCase(text, expected.as_expected() if expected else None, "cycle", now=ref))
    return cases


@pytest.mark.parametrize("cycle", [Cycle.PAST, Cycle.NEAREST, Cycle.CURRENT, Cycle.FUTURE])
def test_cycle_matches_expressions_over_references(cycle: Cycle) -> None:
    # 요일만 쓴 '금요일'은 FUTURE·CURRENT에서 항상 오늘 이후의 금요일 (정답셋의 next(FRI))
    weekday_upcoming = cycle in (Cycle.FUTURE, Cycle.CURRENT)
    rows = [r for r in OMITTED if not (weekday_upcoming and r[0] == "금요일")]
    report = evaluate_temporal(_cases(rows, WRAP[cycle]), TemporalParser(ParseOptions(cycle=cycle)))
    failures = [f"{r.case.text!r} @ {r.case.now}: {r.detail}" for r in report.failures[:10]]
    assert report.overall.accuracy == 1.0, "\n".join(failures)


@pytest.mark.parametrize("cycle", [Cycle.PAST, Cycle.NEAREST, Cycle.CURRENT])
def test_written_direction_overrides_cycle(cycle: Cycle) -> None:
    """'오는', '다가오는'은 미래, '지난'은 과거: 문장에 적힌 방향이 옵션보다 우선"""
    rows = [
        ("오는 15일", "future(day(15))"),
        ("다가오는 크리스마스", "future(md(12, 25))"),
        ("지난 15일", "past(day(15))"),
    ]
    report = evaluate_temporal(_cases(rows, "{}"), TemporalParser(ParseOptions(cycle=cycle)))
    assert report.overall.accuracy == 1.0, [r.detail for r in report.failures[:5]]


def test_cycle_accepts_string_and_rejects_unknown() -> None:
    assert ParseOptions(cycle="nearest").cycle is Cycle.NEAREST  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cycle"):
        ParseOptions(cycle="sometimes")  # type: ignore[arg-type]
