"""명령행: 날짜/시간 표현을 JSON Lines로 출력

    $ python -m korean_datetime "내일 저녁 7시" --now 2026-09-28T14:30
    {"text": "내일 저녁 7시", ..., "value": "2026-09-29T19:00:00", ...}

인식 결과가 없으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime

from .temporal import AmbiguousHour, Cycle, ParseOptions, TemporalParser


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="korean-datetime", description="한국어 날짜/시간 표현 정규화")
    parser.add_argument("text", nargs="?", help="분석할 텍스트 (생략하면 표준 입력)")
    parser.add_argument("--now", help="기준 시각 (ISO 8601, 예: 2026-09-28T14:30). 기본: 현재 시각")
    parser.add_argument("--all", action="store_true", help="모든 표현 출력 (기본: 첫 표현만)")
    parser.add_argument(
        "--ambiguous-hour", choices=[p.value for p in AmbiguousHour], default="nearest_future"
    )
    parser.add_argument(
        "--cycle",
        choices=[c.value for c in Cycle],
        default=Cycle.FUTURE.value,
        help="생략된 연/월/날짜의 주기",
    )
    parser.add_argument("--compact-dates", action="store_true", help="1015, 261015 같은 숫자를 날짜로 인식")
    parser.add_argument("--vague", action="store_true", help="'최근', '향후' 같은 막연한 때도 인식")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arg_parser = _build_arg_parser()
    args = arg_parser.parse_args(argv)
    try:
        now = datetime.fromisoformat(args.now) if args.now else None
    except ValueError:
        arg_parser.error(f"--now 형식이 올바르지 않습니다: {args.now!r}")
    options = ParseOptions(
        cycle=Cycle(args.cycle),
        ambiguous_hour=AmbiguousHour(args.ambiguous_hour),
        compact_dates=args.compact_dates,
        vague=args.vague,
    )
    text = args.text if args.text is not None else sys.stdin.read()
    parser = TemporalParser(options)
    results = parser.parse_all(text, now) if args.all else [r for r in [parser.parse(text, now)] if r]
    for result in results:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
