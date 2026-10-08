"""temporal 정답셋 평가 어댑터

정답(expected) 필드: start(필수), end, kind. 날짜만 적으면('2026-09-29') 00:00으로 비교합니다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..core.evaluation import EvaluationReport, GoldCase, evaluate
from .ambiguity import Ambiguity
from .expectation import ExpectationError, evaluate_expectation
from .model import TemporalExpression
from .parser import TemporalParser


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _same_moment(predicted: datetime, expected: str) -> bool:
    """정답에 시간대가 있으면 시간대까지, 없으면 벽시계 시각만 비교"""
    wanted = _moment(expected)
    if wanted.tzinfo is None:
        return predicted.replace(tzinfo=None) == wanted
    return (
        predicted.tzinfo is not None and predicted.utcoffset() == wanted.utcoffset() and predicted == wanted
    )


def temporal_matches(predicted: object, expected: Mapping[str, Any]) -> bool:
    """
    정답 필드: start(필수), end, kind, shape(instant | span), is_range.
    shape=instant이면 예측도 한 시각(범위가 아니고 길이 1시간 이하)이어야 합니다.
    """
    if not isinstance(predicted, TemporalExpression):
        return False
    if not _same_moment(predicted.start, expected["start"]):
        return False
    if "end" in expected and not _same_moment(predicted.end, expected["end"]):
        return False
    if "kind" in expected and predicted.kind.value != expected["kind"]:
        return False
    if "is_range" in expected and predicted.is_range != bool(expected["is_range"]):
        return False
    if "duration" in expected:
        return predicted.duration is not None and predicted.duration.iso == expected["duration"]
    if expected.get("shape") == "instant":
        return not predicted.is_range and predicted.end - predicted.start <= _INSTANT_MAX
    return True


_INSTANT_MAX = timedelta(hours=1)


def evaluate_temporal(cases: Iterable[GoldCase], parser: TemporalParser | None = None) -> EvaluationReport:
    active = parser or TemporalParser()
    return evaluate(cases, predict=lambda text, now: active.parse(text, now), match=temporal_matches)


def load_expression_gold(path: str | Path, references: Iterable[datetime]) -> list[GoldCase]:
    """
    기대값 식 정답셋(`{"category", "text", "expect"}` JSONL)을 기준 시각마다 계산해 GoldCase로 펼칩니다.
    같은 정답셋을 어떤 날짜·시각으로도 돌릴 수 있습니다.
    """
    rows: list[tuple[int, dict[str, Any]]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip() and "_meta" not in (row := json.loads(line)):
            rows.append((number, row))
    cases: list[GoldCase] = []
    for ref in references:
        for number, row in rows:
            try:
                expected = evaluate_expectation(row["expect"], ref)
            except (ExpectationError, KeyError) as error:
                raise ValueError(f"{path}:{number} 기대값 식 오류: {error}") from error
            if expected is not None:
                static = row.get("ambiguous", [])
                if not isinstance(static, list) or not all(isinstance(a, str) for a in static):
                    raise ValueError(f"{path}:{number} ambiguous는 문자열 목록이어야 합니다")
                expected = expected.flagged(*static)
            cases.append(
                GoldCase(
                    text=row["text"],
                    expected=expected.as_expected() if expected else None,
                    category=row.get("category", "default"),
                    now=ref,
                )
            )
    return cases


@dataclass(frozen=True, slots=True)
class AmbiguityCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


@dataclass(frozen=True)
class AmbiguityReport:
    """모호성 검출 지표. 값과 별개로, 값까지 맞힌 케이스에서 모호성 표시가 맞는지 종류별로 센다."""

    by_type: Mapping[str, AmbiguityCounts]
    mismatches: tuple[tuple[GoldCase, tuple[str, ...], tuple[str, ...]], ...]

    @property
    def overall(self) -> AmbiguityCounts:
        counts = list(self.by_type.values())
        return AmbiguityCounts(
            sum(c.tp for c in counts), sum(c.fp for c in counts), sum(c.fn for c in counts)
        )

    def format(self, max_mismatches: int = 20) -> str:
        rows = [f"{'ambiguity':<20}{'tp':>7}{'fp':>6}{'fn':>6}{'precision':>11}{'recall':>8}"]
        for name, c in [*sorted(self.by_type.items()), ("TOTAL", self.overall)]:
            rows.append(f"{name:<20}{c.tp:>7}{c.fp:>6}{c.fn:>6}{c.precision:>11.3f}{c.recall:>8.3f}")
        rows.append(f"불일치 {len(self.mismatches)}건")
        rows.extend(
            f"  {case.text!r} @ {case.now:%Y-%m-%d %H:%M}: 예측={list(got)} 정답={list(want)}"
            for case, got, want in self.mismatches[:max_mismatches]
        )
        return "\n".join(rows)


def ambiguity_from_report(report: EvaluationReport) -> AmbiguityReport:
    """값 평가 결과(예측 포함)를 재사용해 모호성 표시를 센다. 값이 틀린 케이스는 제외."""
    counts: dict[str, AmbiguityCounts] = {a.value: AmbiguityCounts() for a in Ambiguity}
    mismatches: list[tuple[GoldCase, tuple[str, ...], tuple[str, ...]]] = []
    for result in report.results:
        case, predicted = result.case, result.predicted
        if not result.correct or case.expected is None or not isinstance(predicted, TemporalExpression):
            continue
        got = {a.value for a in predicted.ambiguities}
        want = set(case.expected.get("ambiguities", ()))
        for name in got | want:
            c = counts.get(name, AmbiguityCounts())
            counts[name] = AmbiguityCounts(
                c.tp + (name in got and name in want),
                c.fp + (name in got - want),
                c.fn + (name in want - got),
            )
        if got != want:
            mismatches.append((case, tuple(sorted(got)), tuple(sorted(want))))
    return AmbiguityReport(by_type=counts, mismatches=tuple(mismatches))
