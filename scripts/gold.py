"""temporal 정답셋(tests/data/temporal_gold.jsonl) 관리

    uv run python scripts/gold.py check                         # 형식·중복·식 오류·문서 누락 검사
    uv run python scripts/gold.py add --category C --text T --expect E [--ambiguous a,b] [--allow-mismatch]
    uv run python scripts/gold.py show "3시" [--now 2026-09-28T14:30 ...]   # 식 값과 파서 값 비교

add는 식을 여러 기준 시각에서 계산해 보고, 파서 값과 다르면 기본적으로 거부합니다.
파서를 고치기 전에 실패 케이스부터 넣는 경우(TDD)에는 --allow-mismatch를 씁니다.
식 문법: docs/expectation-dsl.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from ko_normalizer import TemporalParser
from ko_normalizer.temporal.evaluation import temporal_matches
from ko_normalizer.temporal.expectation import ExpectationError, evaluate_expectation

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "tests" / "data" / "temporal_gold.jsonl"
DOC = ROOT / "docs" / "expectation-dsl.md"
# 식을 시험 계산할 대표 기준 시각: 평상시, 월말 밤, 연말, 윤일 오전
PROBES = (
    datetime(2026, 9, 28, 14, 30),
    datetime(2026, 1, 31, 23, 50),
    datetime(2027, 12, 31, 23, 10),
    datetime(2028, 2, 29, 8, 5),
)


def _rows(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    rows, problems = [], []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append(f"{number}행 JSON 오류: {error}")
            continue
        if "_meta" not in row:
            rows.append((number, row))
    return rows, problems


def _expression_problem(row: dict[str, Any]) -> str | None:
    for key in ("category", "text", "expect"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            return f"'{key}' 필드가 없거나 비었습니다"
    ambiguous = row.get("ambiguous", [])
    if not isinstance(ambiguous, list) or not all(isinstance(a, str) for a in ambiguous):
        return "'ambiguous'는 문자열 목록이어야 합니다"
    try:
        for probe in PROBES:
            evaluate_expectation(row["expect"], probe)
    except (ExpectationError, ValueError) as error:
        return f"식 오류: {error}"
    return None


def check(path: Path, with_docs: bool) -> list[str]:
    rows, problems = _rows(path)
    seen: dict[str, int] = {}
    for number, row in rows:
        problem = _expression_problem(row)
        if problem:
            problems.append(f"{number}행 {row.get('text')!r}: {problem}")
        text = row.get("text")
        if isinstance(text, str):
            if text in seen:
                problems.append(f"{number}행 {text!r}: 중복 ({seen[text]}행과 같은 문장)")
            seen.setdefault(text, number)
    if with_docs:
        documented = set(re.findall(r"`([a-z_]+)`", DOC.read_text(encoding="utf-8")))
        categories = {str(r["category"]) for _, r in rows if isinstance(r.get("category"), str)}
        for category in sorted(categories):
            if category not in documented:
                problems.append(f"카테고리 {category!r}가 docs/expectation-dsl.md 6장에 없습니다")
    return problems


def _mismatches(parser: TemporalParser, text: str, expect: str, ambiguous: list[str]) -> list[str]:
    problems = []
    for probe in PROBES:
        expected = evaluate_expectation(expect, probe)
        got = parser.parse(text, probe)
        if expected is None or got is None:
            if (expected is None) != (got is None):
                problems.append(
                    f"@{probe:%Y-%m-%d %H:%M} 식={expected and expected.start} 파서={got and got.start}"
                )
            continue
        want = expected.flagged(*ambiguous).as_expected()
        if not temporal_matches(got, want):
            problems.append(f"@{probe:%Y-%m-%d %H:%M} 식={want['start']} 파서={got.start.isoformat()}")
        elif {a.value for a in got.ambiguities} != set(want["ambiguities"]):  # type: ignore[arg-type]
            flags = [a.value for a in got.ambiguities]
            problems.append(f"@{probe:%Y-%m-%d %H:%M} 모호성 식={want['ambiguities']} 파서={flags}")
    return problems


def add(path: Path, row: dict[str, Any], allow_mismatch: bool) -> int:
    problem = _expression_problem(row)
    if problem:
        print(f"거부: {problem}")
        return 1
    rows, _ = _rows(path)
    if any(existing.get("text") == row["text"] for _, existing in rows):
        print(f"거부: {row['text']!r}는 이미 있습니다")
        return 1
    mismatches = _mismatches(TemporalParser(), row["text"], row["expect"], row.get("ambiguous", []))
    if mismatches and not allow_mismatch:
        print(
            "거부: 파서 값과 불일치 (파서를 고치기 전이라면 --allow-mismatch)\n  " + "\n  ".join(mismatches)
        )
        return 1
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"추가함: {row['text']!r}" + (f" (불일치 {len(mismatches)}건 — 파서 수정 필요)" if mismatches else "")
    )
    return 0


def show(text: str, expect: str | None, nows: list[datetime]) -> int:
    parser = TemporalParser()
    if expect is None:
        rows, _ = _rows(GOLD)
        expect = next((r["expect"] for _, r in rows if r.get("text") == text), None)
    print(f"문장: {text!r}  식: {expect or '(정답셋에 없음)'}")
    for now in nows:
        got = parser.parse(text, now)
        parsed = (
            f"{got.start.isoformat()} {got.kind.value} {[a.value for a in got.ambiguities]}"
            if got
            else "인식 안 함"
        )
        line = f"  @{now:%Y-%m-%d %H:%M}  파서 {parsed}"
        if expect:
            expected = evaluate_expectation(expect, now)
            line += (
                f"\n  {'':17}식   {expected.start.isoformat() + ' ' + expected.kind if expected else 'none'}"
            )
        print(line)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="temporal 정답셋 관리 (check / add / show)")
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check", help="형식·중복·식 오류·문서 누락 검사")
    check_cmd.add_argument("--gold", type=Path, default=GOLD)
    check_cmd.add_argument("--no-docs", action="store_true", help="카테고리 문서 검사를 건너뜀")
    add_cmd = sub.add_parser("add", help="검증 후 케이스 추가")
    add_cmd.add_argument("--gold", type=Path, default=GOLD)
    add_cmd.add_argument("--category", required=True)
    add_cmd.add_argument("--text", required=True)
    add_cmd.add_argument("--expect", required=True)
    add_cmd.add_argument("--ambiguous", default="", help="문장으로 정해지는 모호성 (쉼표 구분)")
    add_cmd.add_argument("--allow-mismatch", action="store_true", help="파서와 달라도 추가 (TDD)")
    show_cmd = sub.add_parser("show", help="식 값과 파서 값 비교")
    show_cmd.add_argument("text")
    show_cmd.add_argument("--expect", help="정답셋 대신 이 식으로 비교")
    show_cmd.add_argument(
        "--now", action="append", type=datetime.fromisoformat, help="기준 시각 (여러 번 가능)"
    )
    args = parser.parse_args(argv)

    if args.command == "check":
        problems = check(args.gold, with_docs=not args.no_docs)
        rows, _ = _rows(args.gold)
        print("\n".join(problems) if problems else f"문제 없음: {len(rows)}건")
        return 1 if problems else 0
    if args.command == "add":
        row: dict[str, Any] = {"category": args.category, "text": args.text, "expect": args.expect}
        if args.ambiguous:
            row["ambiguous"] = [a.strip() for a in args.ambiguous.split(",") if a.strip()]
        return add(args.gold, row, args.allow_mismatch)
    return show(args.text, args.expect, args.now or list(PROBES))


if __name__ == "__main__":
    sys.exit(main())
