"""정답셋(gold) 기반 정량 평가 (값 하나를 예측하는 파서 공용)

정답셋은 JSONL입니다. 첫 줄에 `{"_meta": {"now": "..."}}`로 기본 기준 시각을 둘 수 있고,
각 줄은 `{"category": str, "text": str, "expected": {...} | null, "now"?: str}` 형식입니다.
expected가 null이면 "아무것도 인식하지 않아야 함"(음성 케이스)입니다.

지표:
- 검출: TP(정답 있음·예측 있음), FN(정답 있음·예측 없음), FP(정답 없음·예측 있음), TN
- precision = TP/(TP+FP), recall = TP/(TP+FN), F1
- value_accuracy = 값까지 맞은 TP / TP (검출한 것 중 정규화가 맞은 비율)
- accuracy = (값까지 맞은 TP + TN) / 전체
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

Expected = Mapping[str, Any]
Prediction = Any  # 예측 결과 (예: TemporalExpression). None이면 인식하지 않음
Predict = Callable[[str, datetime], Prediction | None]
Match = Callable[[Prediction, Expected], bool]


@dataclass(frozen=True, slots=True)
class GoldCase:
    text: str
    expected: Expected | None
    category: str
    now: datetime


@dataclass(frozen=True, slots=True)
class Metrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    correct: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def value_accuracy(self) -> float:
        """검출한 것(TP) 중 값까지 맞은 비율 — 정규화 품질"""
        return (self.correct - self.tn) / self.tp if self.tp else 1.0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 1.0

    def add(self, result: CaseResult) -> Metrics:
        expected, predicted = result.case.expected is not None, result.predicted is not None
        return Metrics(
            tp=self.tp + (expected and predicted),
            fp=self.fp + (not expected and predicted),
            fn=self.fn + (expected and not predicted),
            tn=self.tn + (not expected and not predicted),
            correct=self.correct + result.correct,
        )


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: GoldCase
    predicted: Prediction | None
    correct: bool
    detail: str = ""


@dataclass(frozen=True)
class EvaluationReport:
    results: tuple[CaseResult, ...]
    overall: Metrics
    by_category: Mapping[str, Metrics] = field(default_factory=dict)

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.correct]

    def format(self, max_failures: int = 20) -> str:
        columns = ("precision", 11), ("recall", 8), ("f1", 7), ("value_acc", 11), ("accuracy", 10)
        header = f"{'category':<18}{'n':>7}" + "".join(f"{name:>{width}}" for name, width in columns)
        rows = [header, "-" * len(header)]
        items = [*sorted(self.by_category.items()), ("TOTAL", self.overall)]
        for name, m in items:
            rows.append(
                f"{name:<18}{m.total:>7}{m.precision:>11.3f}{m.recall:>8.3f}{m.f1:>7.3f}"
                f"{m.value_accuracy:>11.3f}{m.accuracy:>10.3f}"
            )
        failures = self.failures
        rows.append(f"실패 {len(failures)}건")
        rows.extend(
            f"  [{r.case.category}] {r.case.text!r} @ {r.case.now:%Y-%m-%d %H:%M}: {r.detail}"
            for r in failures[:max_failures]
        )
        return "\n".join(rows)


def evaluate(cases: Iterable[GoldCase], predict: Predict, match: Match) -> EvaluationReport:
    """cases마다 predict(text, now)를 실행하고 match(예측, 정답)로 값을 비교합니다."""
    results = tuple(_run_case(case, predict, match) for case in cases)
    overall = Metrics()
    by_category: dict[str, Metrics] = {}
    for result in results:
        overall = overall.add(result)
        by_category = {
            **by_category,
            result.case.category: by_category.get(result.case.category, Metrics()).add(result),
        }
    return EvaluationReport(results=results, overall=overall, by_category=by_category)


def _run_case(case: GoldCase, predict: Predict, match: Match) -> CaseResult:
    try:
        predicted = predict(case.text, case.now)
    except Exception as error:  # 한 케이스의 예외가 전체 평가를 멈추지 않도록 실패로 기록
        return CaseResult(case, None, False, f"예외 {type(error).__name__}: {error}")
    if case.expected is None:
        ok = predicted is None
        return CaseResult(
            case, predicted, ok, "" if ok else f"인식하지 않아야 함, 예측={_describe(predicted)}"
        )
    if predicted is None:
        return CaseResult(case, None, False, f"인식 실패, 정답={dict(case.expected)}")
    ok = match(predicted, case.expected)
    return CaseResult(
        case, predicted, ok, "" if ok else f"예측={_describe(predicted)} 정답={dict(case.expected)}"
    )


def _describe(prediction: Prediction | None) -> str:
    if prediction is None:
        return "없음"
    to_dict = getattr(prediction, "to_dict", None)
    return str(to_dict()) if callable(to_dict) else f"{prediction.text!r}={prediction.value!r}"


def load_gold(path: str | Path) -> list[GoldCase]:
    """JSONL 정답셋을 읽습니다. 형식 오류는 줄 번호와 함께 ValueError로 알립니다."""
    default_now: datetime | None = None
    cases: list[GoldCase] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if "_meta" in row:
                default_now = datetime.fromisoformat(row["_meta"]["now"])
                continue
            cases.append(_to_case(row, default_now))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{path}:{number} 정답셋 형식 오류: {error}") from error
    return cases


def _to_case(row: Mapping[str, Any], default_now: datetime | None) -> GoldCase:
    now = datetime.fromisoformat(row["now"]) if "now" in row else default_now
    if now is None:
        raise ValueError("now가 없습니다 (_meta.now 또는 케이스의 now 필요)")
    expected = row["expected"]
    if expected is not None and not isinstance(expected, Mapping):
        raise TypeError("expected는 객체 또는 null이어야 합니다")
    return GoldCase(
        text=str(row["text"]), expected=expected, category=str(row.get("category", "default")), now=now
    )


__all__: Sequence[str] = ["CaseResult", "EvaluationReport", "GoldCase", "Metrics", "evaluate", "load_gold"]
