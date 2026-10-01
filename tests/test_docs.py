"""docs/expectation-dsl.md가 코드·정답셋과 맞는지 검사 (함수·메서드·단위·카테고리가 모두 문서에 있어야 함)"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ko_normalizer.temporal import expectation

ROOT = Path(__file__).parent.parent
DOC = (ROOT / "docs" / "expectation-dsl.md").read_text(encoding="utf-8")
GOLD = ROOT / "tests" / "data" / "temporal_gold.jsonl"
_PROSE = re.sub(r"```.*?```", "", DOC, flags=re.DOTALL)  # 코드 블록을 빼야 인라인 `코드` 짝이 맞음
DOCUMENTED = set(re.findall(r"`([^`\n]+)`", _PROSE))


def _mentioned(name: str) -> bool:
    """`name`, `name(...)`, `.name(...)` 중 하나로 문서에 등장"""
    return any(re.fullmatch(rf"\.?{re.escape(name)}(\(.*\))?", item) for item in DOCUMENTED)


@pytest.mark.parametrize("name", [*expectation._ATOMS, "future", "past"])
def test_every_atom_is_documented(name: str) -> None:
    assert _mentioned(name), f"기본 값 {name}이(가) docs/expectation-dsl.md에 없습니다"


@pytest.mark.parametrize("name", list(expectation._METHOD_GRAIN))
def test_every_method_is_documented(name: str) -> None:
    assert _mentioned(name), f"메서드 .{name}()이(가) docs/expectation-dsl.md에 없습니다"


@pytest.mark.parametrize("unit", ["d", "w", "mo", "y", "h", "min", "s"])
def test_every_offset_unit_is_documented(unit: str) -> None:
    assert unit in DOCUMENTED


@pytest.mark.parametrize("weekday", list(expectation.WEEKDAY_NAMES))
def test_every_weekday_name_is_documented(weekday: str) -> None:
    assert weekday in DOC


def test_every_gold_category_is_documented() -> None:
    categories = {
        row["category"]
        for row in map(json.loads, GOLD.read_text(encoding="utf-8").splitlines())
        if "text" in row
    }
    missing = sorted(c for c in categories if c not in DOCUMENTED)
    assert missing == [], f"문서 6장에 없는 카테고리: {missing}"


def test_doc_examples_evaluate() -> None:
    """문서에 적힌 식 예시가 실제로 계산되는지 (자리표시자 WD, M, D … 가 든 문법 설명은 제외)"""
    from datetime import datetime

    ref = datetime(2026, 9, 28, 14, 30)
    atoms = {*expectation._ATOMS, "future", "past"}
    placeholder = re.compile(r"\b(WD|[MDKYTNABHX]|앞|뒤)\b")

    def is_expression(item: str) -> bool:
        head = re.match(r"\(|[a-z_]+", item)
        if head is None or placeholder.search(item):
            return False
        # 본문에 이름만 적힌 것('at', 'day')은 제외하고, 인자 없는 기본 값과 괄호가 있는 식만
        return item in ("today", "now", "none") or ("(" in item and (head[0] == "(" or head[0] in atoms))

    examples = sorted(item for item in DOCUMENTED if is_expression(item))
    assert len(examples) >= 40
    for expr in examples:
        if expr in INTENDED_ERRORS:
            with pytest.raises(expectation.ExpectationError):
                expectation.evaluate_expectation(expr, ref)
        else:
            expectation.evaluate_expectation(expr, ref)


# 문서에 "이렇게 쓰면 오류"로 적어 둔 예시
INTENDED_ERRORS = {"today.weekday(MON)"}
