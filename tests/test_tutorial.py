"""docs/tutorial.md의 코드 예시를 실제로 실행: `식  # → 값`의 값이 str(식)과 같아야 함

튜토리얼이 코드와 어긋나면 이 테스트가 실패하므로, 문서의 '실제 결과'는 항상 실제 결과입니다.
"""

from __future__ import annotations

import re
from pathlib import Path

TUTORIAL = Path(__file__).parent.parent / "docs" / "tutorial.md"
_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
_ARROW = re.compile(r"^(?P<indent>\s*)(?P<expr>.+?)\s+#\s*→\s*(?P<want>.*)$")


def _program() -> tuple[str, int]:
    """모든 블록을 이은 코드. '식  # → 값' 줄은 같은 들여쓰기에서 (식, 실제, 기대)를 기록하는 줄로 바꿈"""
    lines, count = [], 0
    for block in _BLOCK.findall(TUTORIAL.read_text(encoding="utf-8")):
        for line in block.splitlines():
            match = _ARROW.match(line)
            if match:
                expr, want = match["expr"].strip(), match["want"].strip()
                lines.append(f"{match['indent']}_checks.append(({expr!r}, str({expr}), {want!r}))")
                count += 1
            else:
                lines.append(line)
    return "\n".join(lines), count


def test_tutorial_examples_match_actual_results() -> None:
    program, count = _program()
    checks: list[tuple[str, str, str]] = []
    exec(program, {"_checks": checks})  # 저장소 문서의 예시 코드만 실행
    assert len(checks) == count
    mismatches = [f"{expr}\n    문서: {want}\n    실제: {got}" for expr, got, want in checks if got != want]
    assert not mismatches, "\n".join(mismatches)


def test_tutorial_has_examples() -> None:
    assert _program()[1] > 40
