"""정답셋 기반 정량 평가

1. 기대값 식 정답셋(temporal_gold.jsonl)을 여러 기준 시각에서 계산해 검출(precision/recall/F1)과
   값 정확도를 측정합니다. 기준 시각에는 실제 현재 시각도 들어가므로 언제 실행해도 의미가 있습니다.
   - 기본 실행: 표본 기준 시각 (sampled_references)
   - 전체 스윕: `uv run pytest -m slow` (2년 매일 + 하루 중 여러 시각)
2. 식 평가기 자체 검증: 2026-09-28 14:30에서 계산한 식 = 손으로 계산한 절대값(temporal_anchor.jsonl)
3. 절대값 앵커 정답셋도 그대로 평가합니다.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from references import (
    ANCHOR,
    GOLD,
    full_references,
    real_now,
    sampled_ambiguity_report,
    sampled_references,
    sampled_report,
)

from korean_datetime import parse
from korean_datetime.core.evaluation import EvaluationReport, GoldCase, Metrics, evaluate, load_gold
from korean_datetime.temporal.evaluation import evaluate_temporal, load_expression_gold, temporal_matches
from korean_datetime.temporal.expectation import evaluate_expectation

# 임계값: 정답셋은 회귀 기준이므로 전부 맞아야 한다. 어려운 케이스를 추가하며 조정할 수 있다.
MIN_ACCURACY = 1.0
MIN_PRECISION = 1.0
MIN_RECALL = 1.0
ANCHOR_REF = datetime(2026, 9, 28, 14, 30)


def _gold_rows() -> list[dict[str, str]]:
    return [row for row in map(json.loads, GOLD.read_text(encoding="utf-8").splitlines()) if "text" in row]


def _assert_thresholds(report: EvaluationReport) -> None:
    print("\n" + report.format())
    failures = "\n".join(f"  {r.case.text!r} @ {r.case.now}: {r.detail}" for r in report.failures[:20])
    assert report.overall.accuracy >= MIN_ACCURACY, f"정확도 미달\n{failures}"
    assert report.overall.precision >= MIN_PRECISION, failures
    assert report.overall.recall >= MIN_RECALL, failures


def test_gold_set_is_non_trivial() -> None:
    rows = _gold_rows()
    assert len(rows) >= 300
    assert len({r["category"] for r in rows}) >= 15
    assert sum(r["expect"] == "none" for r in rows) >= 60  # 인식하지 않아야 하는 음성 케이스
    assert len(sampled_references()) >= 250


def test_expression_gold_over_sampled_references() -> None:
    report = sampled_report()
    assert report.overall.total == len(_gold_rows()) * len(sampled_references())
    _assert_thresholds(report)


def test_expression_gold_at_real_now() -> None:
    """실행 시점의 실제 현재 시각으로 한 번 더 (스모크). 실패하면 리포트에 그 시각이 찍힌다."""
    now = real_now()
    print(f"\n실제 현재 시각: {now:%Y-%m-%d %H:%M}")
    _assert_thresholds(evaluate_temporal(load_expression_gold(GOLD, [now])))


@pytest.mark.slow
def test_expression_gold_over_full_sweep() -> None:
    _assert_thresholds(evaluate_temporal(load_expression_gold(GOLD, full_references())))


def test_expressions_agree_with_hand_computed_anchor() -> None:
    """식 평가기 검증: 앵커 행마다 그 기준 시각에서 식을 계산해 손계산 절대값과 대조"""
    expressions = {row["text"]: row["expect"] for row in _gold_rows()}
    checked, mismatches = 0, []
    for case in load_gold(ANCHOR):
        if case.text not in expressions:
            continue
        checked += 1
        got = evaluate_expectation(expressions[case.text], case.now)
        if case.expected is None or got is None:
            ok = case.expected is None and got is None
        else:
            computed = got.as_expected()
            ok = (
                all(
                    datetime.fromisoformat(str(case.expected[key]))
                    == datetime.fromisoformat(str(computed[key]))
                    for key in ("start", "end")
                    if key in case.expected and key in computed
                )
                and case.expected.get("kind", computed["kind"]) == computed["kind"]
            )
        if not ok:
            mismatches.append((case.text, case.now, expressions[case.text], got, case.expected))
    assert checked >= 360
    assert len({case.now for case in load_gold(ANCHOR)}) >= 3  # 기준 시각 3개 이상에서 손계산
    assert mismatches == []


def test_anchor_metrics() -> None:
    _assert_thresholds(evaluate_temporal(load_gold(ANCHOR)))


def test_metrics_arithmetic() -> None:
    m = Metrics(tp=8, fp=2, fn=2, tn=8, correct=14)
    assert (m.total, m.precision, m.recall) == (20, 0.8, 0.8)
    assert m.f1 == pytest.approx(0.8)
    assert m.accuracy == pytest.approx(0.7)
    assert Metrics().precision == 1.0 and Metrics().recall == 1.0 and Metrics().accuracy == 1.0


def test_evaluate_counts_detection_and_value_errors() -> None:
    cases = [
        GoldCase(text="내일", expected={"start": "2026-09-29"}, category="ok", now=ANCHOR_REF),
        GoldCase(text="내일", expected={"start": "2026-09-30"}, category="wrong_value", now=ANCHOR_REF),
        GoldCase(text="아무 말", expected={"start": "2026-09-29"}, category="missed", now=ANCHOR_REF),
        GoldCase(text="내일", expected=None, category="false_alarm", now=ANCHOR_REF),
    ]
    rep = evaluate_temporal(cases)
    assert (rep.overall.tp, rep.overall.fp, rep.overall.fn, rep.overall.correct) == (2, 1, 1, 1)
    assert [r.case.category for r in rep.failures] == ["wrong_value", "missed", "false_alarm"]
    assert "wrong_value" in rep.format()


def test_generic_evaluate_with_custom_matcher() -> None:
    cases = [GoldCase(text="a", expected={"value": 1}, category="x", now=ANCHOR_REF)]
    rep = evaluate(cases, predict=lambda text, _now: None, match=lambda m, e: True)
    assert rep.overall.fn == 1


def test_temporal_matches_checks_all_given_fields() -> None:
    result = parse("내일", now=ANCHOR_REF)
    assert result is not None
    assert temporal_matches(result, {"start": "2026-09-29", "end": "2026-09-30", "kind": "date"})
    assert not temporal_matches(result, {"start": "2026-09-29", "kind": "time"})
    assert not temporal_matches(result, {"start": "2026-09-29", "end": "2026-10-01"})


def test_expression_gold_reports_bad_expressions(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "bad.jsonl"
    path.write_text('{"category": "x", "text": "내일", "expect": "today +"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:1"):
        load_expression_gold(path, [ANCHOR_REF])


def test_instant_expectation_rejects_range_prediction() -> None:
    ranged = parse("3시부터 5시까지", now=ANCHOR_REF)
    assert ranged is not None
    assert not temporal_matches(ranged, {"start": "2026-09-28T15:00:00", "kind": "time", "shape": "instant"})
    single = parse("3시", now=ANCHOR_REF)
    assert single is not None
    assert temporal_matches(single, {"start": "2026-09-28T15:00:00", "kind": "time", "shape": "instant"})
    assert not temporal_matches(single, {"start": "2026-09-28T15:00:00", "kind": "time", "is_range": True})


def test_value_accuracy_among_detected() -> None:
    m = Metrics(tp=10, fp=0, fn=0, tn=5, correct=13)  # 검출 10건 중 8건 값 일치
    assert m.value_accuracy == pytest.approx(0.8)
    assert "value_acc" in evaluate_temporal([]).format()


def test_timezone_is_compared_when_given() -> None:
    from datetime import timedelta, timezone

    kst = timezone(timedelta(hours=9))
    result = parse("내일", now=ANCHOR_REF.replace(tzinfo=kst))
    assert result is not None
    assert temporal_matches(result, {"start": "2026-09-29T00:00:00+09:00", "kind": "date"})
    assert not temporal_matches(result, {"start": "2026-09-29T00:00:00+00:00", "kind": "date"})


def test_sampled_references_are_reproducible() -> None:
    assert sampled_references() == sampled_references()
    assert all(ref.year <= 2028 for ref in sampled_references())
    assert any(ref.tzinfo is not None for ref in sampled_references())


def test_ambiguity_detection_over_sampled_references() -> None:
    """모호성 표시: 식이 계산한 것(주기 넘김, 같은 요일 …) ∪ 정답셋의 ambiguous 와 정확히 같아야 한다"""
    report = sampled_ambiguity_report()
    print("\n" + report.format())
    assert report.overall.tp > 1000  # 실제로 모호성 케이스를 검사하고 있는지
    assert report.overall.precision == 1.0, report.format()
    assert report.overall.recall == 1.0, report.format()
    assert report.mismatches == ()


def test_ambiguous_field_must_be_list(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "bad.jsonl"
    path.write_text(
        '{"category": "x", "text": "내일", "expect": "today", "ambiguous": "x"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="ambiguous"):
        load_expression_gold(path, [ANCHOR_REF])
