"""커밋 전 전체 검사: ruff → mypy(strict) → 정답셋 검사 → pytest

    uv run python scripts/check.py          # 기본 (표본 기준 시각)
    uv run python scripts/check.py --full   # 전체 스윕(-m slow)까지

하나라도 실패하면 종료 코드 1. 실패한 단계에서 멈추지 않고 끝까지 실행해 결과를 한 번에 보여줍니다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def steps(full: bool) -> list[tuple[str, list[str]]]:
    python = sys.executable
    plan = [
        ("ruff", [python, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("ruff format", [python, "-m", "ruff", "format", "--check", "src", "tests", "scripts"]),
        ("mypy", [python, "-m", "mypy"]),
        ("gold", [python, str(ROOT / "scripts" / "gold.py"), "check"]),
        ("pytest", [python, "-m", "pytest", "-p", "no:cacheprovider"]),
    ]
    if full:
        plan.append(("pytest slow", [python, "-m", "pytest", "-p", "no:cacheprovider", "-m", "slow"]))
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ruff, mypy, 정답셋 검사, pytest를 차례로 실행합니다.")
    parser.add_argument("--full", action="store_true", help="전체 스윕(-m slow)까지 실행")
    args = parser.parse_args(argv)
    results = []
    for name, command in steps(args.full):
        shown = " ".join(Path(part).name if part == sys.executable else part for part in command)
        print(f"\n=== {name}: {shown}")
        results.append((name, subprocess.run(command, cwd=ROOT, check=False).returncode))
    print("\n=== 요약")
    for name, code in results:
        print(f"  {'통과' if code == 0 else '실패'}  {name}")
    return 0 if all(code == 0 for _, code in results) else 1


if __name__ == "__main__":
    sys.exit(main())
