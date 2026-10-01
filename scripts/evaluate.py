"""원하는 기준 시각으로 temporal 정답셋을 평가합니다 (실패 재현·특정 기간 점검용).

    uv run python scripts/evaluate.py                                   # 실제 현재 시각
    uv run python scripts/evaluate.py --now 2026-09-28T14:30 --now 2028-02-29T08:05
    uv run python scripts/evaluate.py --from 2026-12-25 --to 2027-01-05 --at 09:00 --at 23:50
    uv run python scripts/evaluate.py --gold my_gold.jsonl --max-failures 50

값 리포트와 모호성 리포트를 출력하고, 실패가 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path

from ko_normalizer.temporal.evaluation import ambiguity_from_report, evaluate_temporal, load_expression_gold

GOLD = Path(__file__).resolve().parent.parent / "tests" / "data" / "temporal_gold.jsonl"


def references(
    nows: list[datetime], start: date | None, end: date | None, times: list[time]
) -> list[datetime]:
    moments = list(nows)
    if start or end:
        if not (start and end) or end < start:
            raise SystemExit("--from과 --to를 함께, --from ≤ --to로 지정하세요")
        day = start
        while day <= end:
            moments += [datetime.combine(day, at) for at in times or [time(14, 30)]]
            day += timedelta(days=1)
    return moments or [datetime.now().replace(second=0, microsecond=0)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="원하는 기준 시각으로 temporal 정답셋을 평가합니다.")
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument(
        "--now", action="append", default=[], type=datetime.fromisoformat, help="기준 시각 (여러 번)"
    )
    parser.add_argument("--from", dest="start", type=date.fromisoformat, help="기간 시작일")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="기간 끝일 (포함)")
    parser.add_argument(
        "--at", action="append", default=[], type=time.fromisoformat, help="기간의 하루 중 시각"
    )
    parser.add_argument("--max-failures", type=int, default=20)
    args = parser.parse_args(argv)

    refs = references(args.now, args.start, args.end, args.at)
    report = evaluate_temporal(load_expression_gold(args.gold, refs))
    ambiguity = ambiguity_from_report(report)
    period = f"{min(refs):%Y-%m-%d %H:%M} ~ {max(refs):%Y-%m-%d %H:%M}"
    print(f"기준 시각 {len(refs)}개 ({period}), 검사 {report.overall.total}건\n")
    print(report.format(args.max_failures))
    print()
    print(ambiguity.format(args.max_failures))
    return 1 if report.failures or ambiguity.mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
