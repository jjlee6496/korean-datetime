"""AI허브 시간 표현 탐지 데이터로 옵션별 벤치마크 표(마크다운) 만들기

    uv run python scripts/aihub_benchmark.py <데이터 루트> > docs/benchmark.md

<데이터 루트>는 Training/, Validation/ 아래에 02.라벨링데이터가 있는 폴더입니다.
옵션을 하나씩 바꿔 가며(나머지는 기본값) scripts/aihub_eval.py의 평가를 돌립니다.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from aihub_eval import Tally, evaluate

from korean_datetime import AmbiguousHour, Cycle, ParseOptions, __version__

SPLITS = ("Training", "Validation")
DOMAINS = (("news", "뉴스"), ("dialog", "대화"), ("history", "역사"))


@dataclass(frozen=True)
class Run:
    label: str
    options: ParseOptions


def _ratio(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.3f}" if denominator else "-"


def _value_accuracy(tally: Tally, domain: str) -> str:
    c = tally.counts
    ok = sum(c[f"{domain}.{cls}.value_ok"] for cls in ("explicit", "partial"))
    valued = sum(c[f"{domain}.{cls}.valued"] for cls in ("explicit", "partial"))
    return _ratio(ok, valued)


def _precision(tally: Tally, domain: str) -> str:
    c = tally.counts
    return _ratio(c[f"{domain}.predicted"] - c[f"{domain}.false_alarm"], c[f"{domain}.predicted"])


def _recall(tally: Tally, domain: str) -> str:
    return _ratio(tally.counts[f"{domain}.found"], tally.counts[f"{domain}.gold"])


def _meridiem(tally: Tally, domain: str) -> str:
    c = tally.counts
    return _ratio(c[f"{domain}.meridiem_ok"], c[f"{domain}.meridiem_checked"])


def _evaluate_all(root: Path, runs: list[Run]) -> dict[tuple[str, str], Tally]:
    results = {}
    for split in SPLITS:
        for run in runs:
            print(f"평가 중: {split} {run.label}", file=sys.stderr)
            results[split, run.label] = evaluate(root / split / "02.라벨링데이터", run.options, limit=0)
    return results


def _size_table(results: dict[tuple[str, str], Tally]) -> list[str]:
    lines = ["| 분야 | " + " | ".join(f"{s} 정답 수" for s in SPLITS) + " |", "|---|" + "---:|" * len(SPLITS)]
    for key, name in DOMAINS:
        counts = " | ".join(f"{results[s, 'default'].counts[f'{key}.gold']:,}" for s in SPLITS)
        lines.append(f"| {name} | {counts} |")
    return lines


def _metric_table(
    results: dict[tuple[str, str], Tally],
    labels: list[str],
    metric: str,
    domains: tuple[tuple[str, str], ...],
) -> list[str]:
    fn = {"value": _value_accuracy, "meridiem": _meridiem, "recall": _recall, "precision": _precision}[metric]
    header = "| 설정 | " + " | ".join(f"{name} {split}" for _, name in domains for split in SPLITS) + " |"
    lines = [header, "|---|" + "---:|" * (len(domains) * len(SPLITS))]
    columns = [(key, split) for key, _ in domains for split in SPLITS]
    values = {label: [fn(results[split, label], key) for key, split in columns] for label in labels}
    best = [max((v[i] for v in values.values() if v[i] != "-"), default="-") for i in range(len(columns))]
    for label in labels:
        cells = [
            f"**{v}**" if len(labels) > 1 and v == best[i] and v != "-" else v
            for i, v in enumerate(values[label])
        ]
        lines.append(f"| `{label}` | {' | '.join(cells)} |")
    return lines


def _meridiem_counts(results: dict[tuple[str, str], Tally]) -> str:
    parts = []
    for split in SPLITS:
        c = results[split, "ambiguous_hour=context"].counts
        parts.append(
            f"{split} " + ", ".join(f"{name} {c[f'{key}.meridiem_checked']}건" for key, name in DOMAINS[:2])
        )
    return " / ".join(parts)


def build(root: Path) -> str:
    cycles = [Run(f"cycle={c.value}", ParseOptions(cycle=c)) for c in Cycle]
    hours = [Run(f"ambiguous_hour={h.value}", ParseOptions(ambiguous_hour=h)) for h in AmbiguousHour]
    runs = [Run("default", ParseOptions()), Run("vague=True", ParseOptions(vague=True)), *cycles, *hours]
    r = _evaluate_all(root, runs)
    out = [
        "# 벤치마크: 옵션별 실제 문장 평가",
        "",
        "데이터 출처: AI허브(한국지능정보사회진흥원) [「시간 표현 탐지 데이터」](https://aihub.or.kr).",
        "데이터는 이 저장소에 포함하지 않습니다.",
        "",
        f"korean-datetime {__version__}, {date.today().isoformat()} 측정. "
        "`uv run python scripts/aihub_benchmark.py <데이터 루트> > docs/benchmark.md`로 다시 만듭니다.",
        "옵션은 하나씩만 바꾸고 나머지는 기본값입니다.",
        "평가 방식은 `scripts/aihub_eval.py` 머리말에 있습니다.",
        "Validation은 규칙을 다듬을 때 오류를 본 데이터라,",
        "처음 보는 데이터인 **Training 수치가 실제 성능에 가깝습니다**.",
        "",
        "라이브러리 간 표본 비교와 속도는 [별도 비교 문서](comparison.md)에 있습니다.",
        "",
        "## 데이터 규모 (DATE·TIME 정답 표현 수)",
        "",
        *_size_table(r),
        "",
        "## 기본 설정",
        "",
        "검출(재현율·정밀도)은 위치가 겹치면 맞은 것.",
        "값 정확도는 문서 작성 시각을 기준 시각으로 놓고 정답 값의 정해진 부분을 비교.",
        "",
        "재현율",
        "",
        *_metric_table(r, ["default"], "recall", DOMAINS),
        "",
        "정밀도",
        "",
        *_metric_table(r, ["default"], "precision", DOMAINS),
        "",
        "값 정확도",
        "",
        *_metric_table(r, ["default"], "value", DOMAINS),
        "",
        "각 표에서 가장 좋은 값은 굵게 표시합니다.",
        "",
        "## `cycle`: 생략된 연·월·날짜의 주기 → 값 정확도",
        "",
        *_metric_table(r, [run.label for run in cycles], "value", DOMAINS),
        "",
        "## `ambiguous_hour`: 오전/오후 없는 시각 → 오전/오후 일치율",
        "",
        f"정답에 시각이 있고 문장에 오전/오후가 없는 경우만 셉니다 ({_meridiem_counts(r)}).",
        "건수가 적은 칸은 참고만 하세요.",
        "데이터의 기준 시각은 발화 시각이 아니라 수집 시각이라,",
        "실시간 대화용 기본값(`nearest_future`)에는 불리합니다.",
        "",
        *_metric_table(r, [run.label for run in hours], "meridiem", DOMAINS[:2]),
        "",
        "## `vague`: '최근', '향후' 같은 막연한 때",
        "",
        "재현율",
        "",
        *_metric_table(r, ["default", "vague=True"], "recall", DOMAINS),
        "",
        "정밀도",
        "",
        *_metric_table(r, ["default", "vague=True"], "precision", DOMAINS),
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Training/, Validation/ 가 있는 데이터 루트")
    args = ap.parse_args(argv)
    missing = [s for s in SPLITS if not (args.root / s / "02.라벨링데이터").is_dir()]
    if missing:
        print(f"라벨링데이터 폴더가 없습니다: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(build(args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
