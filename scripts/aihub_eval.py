"""AI허브 '시간 표현 탐지 데이터'(TIMEX3 주석)로 실제 문장 평가

    uv run python scripts/aihub_eval.py <라벨링데이터 폴더>              # VL_*.zip 또는 압축 푼 *.json
    uv run python scripts/aihub_eval.py <폴더> --cycle nearest          # 생략된 날짜의 주기 선택 비교
    uv run python scripts/aihub_eval.py <폴더> --samples 20             # 놓친 것·틀린 것·오탐 예시

데이터는 라이선스상 저장소에 넣지 않습니다. 평가 방식:
- 검출: 정답의 DATE/TIME 표현과 위치가 겹치는 예측이 있으면 찾은 것 (범위 예측은 여러 정답을 덮을 수 있음).
  DURATION/SET은 이 라이브러리가 값으로 내지 않으므로 재현율에서 빼고, 거기에 겹친 예측은 오탐으로 세지 않음.
- 값: 기준 시각 = 문서 작성 시각(info.date_created). 뉴스는 완전한 값(2021-03-08), 모든 분야에서 일부만 정해진
  값(XXXX-08-20, XXXX-XX-XXT19:00)의 정해진 부분만 비교. 음력 명절(추석 등)은 정답이 음력 표기라 제외.
  오전/오후가 문장에 없는 시각은 대화 시각을 알 수 없으므로 12시간 단위로 비교하고 오전/오후 일치는 따로 셈.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ko_normalizer import Ambiguity, AmbiguousHour, Cycle, ParseOptions, TemporalExpression, TemporalParser

FULL = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2})(?:T(\d{2}):(\d{2}))?)?)?$")
PARTIAL = re.compile(r"^XXXX-(\d{2}|XX)(?:-(\d{2}|XX)(?:T(\d{2}):(\d{2}))?)?$")
LUNAR_HOLIDAY = re.compile(r"추석|한가위|설|구정|단오|대보름|석가|부처님")
DETECTED_TYPES = ("DATE", "TIME")


@dataclass
class Tally:
    counts: Counter[str] = field(default_factory=Counter)
    samples: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))

    def add(self, key: str, amount: int = 1) -> None:
        self.counts[key] += amount

    def sample(self, key: str, item: Any, limit: int) -> None:
        if len(self.samples[key]) < limit:
            self.samples[key].append(item)


def _domain(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    return (
        "news" if "뉴스" in name else "dialog" if "대화" in name else "history" if "역사" in name else "other"
    )


def _documents(root: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """(분야, 문서). VL_*.zip은 풀지 않고 읽고, 압축을 푼 폴더면 *.json을 읽음"""
    for archive in sorted(root.rglob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.filename.endswith(".json"):
                    yield _domain(archive.stem), json.loads(zf.read(info))
    for path in sorted(root.rglob("*.json")):
        yield _domain(path.parent.name), json.loads(path.read_text(encoding="utf-8"))


def gold_class(value: str) -> str:
    if FULL.match(value):
        return "explicit"
    match = PARTIAL.match(value)
    if match and any(group and group != "XX" for group in match.groups()):
        return "partial"
    if re.search(r"T(MO|AF|EV|NI|NN|AM|PM|EM|DT)$", value):
        return "period"
    if re.search(r"-(SP|SU|FA|WI)$|\d+C$|\dX$|Q\d|-H\d|W\d", value):
        return "season_decade_quarter"
    return "vague"  # 기준이 풀리지 않은 XXXX-XX-XX('오늘', '최근'), PRESENT_REF 등


def _gold_spans(sentence: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    text, spans = sentence["text"], []
    for timex in sentence.get("timex3", []):
        start, end = timex["extent"]
        label = timex["text"].strip()
        if text[start:end].strip() != label and label in text:  # 위치가 어긋난 주석은 글자로 다시 찾음
            start = text.find(label)
            end = start + len(label)
        spans.append((start, end, timex))
    return spans


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _value_check(pred: TemporalExpression, value: str) -> tuple[bool, bool | None] | None:
    """(값 일치, 오전/오후 일치 또는 None). 비교할 수 없으면 None"""
    full, partial = FULL.match(value), PARTIAL.match(value)
    if full:
        year, month, day, hour, minute = full.groups()
        if pred.start.year != int(year):
            return False, None
    elif partial:
        month, day, hour, minute = partial.groups()
    else:
        return None
    start = pred.start
    same_date = (month in (None, "XX") or start.month == int(month)) and (
        day in (None, "XX") or start.day == int(day)
    )
    if hour is None:
        return same_date, None
    want = (int(hour), int(minute))
    if Ambiguity.MERIDIEM in pred.ambiguities:  # 오전/오후가 문장에 없음: 12시간 단위로 비교
        return same_date and (start.hour % 12, start.minute) == (want[0] % 12, want[1]), start.hour == want[0]
    return same_date and (start.hour, start.minute) == want, None


def _score_sentence(
    tally: Tally, domain: str, sentence: dict[str, Any], preds: list[TemporalExpression], limit: int
) -> None:
    gold = _gold_spans(sentence)
    matched: set[int] = set()
    for start, end, timex in (g for g in gold if g[2]["type"] in DETECTED_TYPES):
        cls = gold_class(timex["value"])
        tally.add(f"{domain}.gold")
        tally.add(f"{domain}.{cls}.gold")
        hit = next((i for i, p in enumerate(preds) if _overlaps(p.span, (start, end))), None)
        if hit is None:
            tally.sample(f"{domain}.{cls}.missed", (timex["text"], timex["value"], sentence["text"]), limit)
            continue
        matched.add(hit)
        tally.add(f"{domain}.found")
        tally.add(f"{domain}.{cls}.found")
        _score_value(tally, domain, cls, preds[hit], timex, sentence["text"], limit)
    for i, pred in enumerate(preds):
        tally.add(f"{domain}.predicted")
        if i not in matched and not any(_overlaps(pred.span, g[:2]) for g in gold):
            tally.add(f"{domain}.false_alarm")
            tally.sample(f"{domain}.false_alarm", (pred.text, sentence["text"]), limit)


def _score_value(
    tally: Tally,
    domain: str,
    cls: str,
    pred: TemporalExpression,
    timex: dict[str, Any],
    text: str,
    limit: int,
) -> None:
    if cls not in ("explicit", "partial") or (cls == "explicit" and domain != "news"):
        return  # 대화·역사의 완전한 값은 기준 시각(작성 시각)과 무관하게 매겨져 비교하지 않음
    if LUNAR_HOLIDAY.search(timex["text"]):
        return
    checked = _value_check(pred, timex["value"])
    if checked is None:
        return
    ok, meridiem = checked
    tally.add(f"{domain}.{cls}.valued")
    tally.add(f"{domain}.{cls}.value_ok", ok)
    if meridiem is not None:
        tally.add(f"{domain}.meridiem_checked")
        tally.add(f"{domain}.meridiem_ok", meridiem)
    if not ok:
        tally.sample(
            f"{domain}.{cls}.wrong", (pred.text, pred.start.isoformat(), timex["value"], text), limit
        )


def evaluate(root: Path, options: ParseOptions, limit: int) -> Tally:
    parser = TemporalParser(options)
    tally = Tally()
    for domain, document in _documents(root):
        reference = datetime.fromisoformat(document["meta_info"]["info.date_created"][:19])
        for sentence in document.get("sentences") or document.get("utterances") or []:
            _score_sentence(tally, domain, sentence, parser.parse_all(sentence["text"], now=reference), limit)
    return tally


def _ratio(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.3f}" if denominator else "-"


def report(tally: Tally) -> str:
    c = tally.counts
    domains = sorted({key.split(".")[0] for key in c})
    lines = [f"{'domain':10} {'gold':>7} {'recall':>7} {'pred':>7} {'precision':>9} {'meridiem':>9}"]
    for d in domains:
        precision = _ratio(c[f"{d}.predicted"] - c[f"{d}.false_alarm"], c[f"{d}.predicted"])
        meridiem = _ratio(c[f"{d}.meridiem_ok"], c[f"{d}.meridiem_checked"])
        lines.append(
            f"{d:10} {c[f'{d}.gold']:7} {_ratio(c[f'{d}.found'], c[f'{d}.gold']):>7} "
            f"{c[f'{d}.predicted']:7} {precision:>9} {meridiem:>9}"
        )
    lines += ["", f"{'domain.class':32} {'gold':>6} {'recall':>7} {'valued':>7} {'value_acc':>9}"]
    classes = sorted({key.rsplit(".", 1)[0] for key in c if key.count(".") == 2})
    for k in classes:
        lines.append(
            f"{k:32} {c[k + '.gold']:6} {_ratio(c[k + '.found'], c[k + '.gold']):>7} "
            f"{c[k + '.valued']:7} {_ratio(c[k + '.value_ok'], c[k + '.valued']):>9}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="라벨링데이터 폴더 (VL_*.zip 또는 압축 푼 *.json)")
    ap.add_argument(
        "--cycle", choices=[c.value for c in Cycle], default=Cycle.FUTURE.value, help="ParseOptions.cycle"
    )
    ap.add_argument("--samples", type=int, default=0, help="종류별 예시 개수")
    ap.add_argument(
        "--vague", action="store_true", help="'최근', '향후' 같은 막연한 때도 인식 (ParseOptions.vague)"
    )
    ap.add_argument(
        "--ambiguous-hour",
        choices=[policy.name.lower() for policy in AmbiguousHour],
        default="nearest_future",
        help="오전/오후 없는 시각 정책 (ParseOptions.ambiguous_hour)",
    )
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        print(f"폴더가 아닙니다: {args.root}", file=sys.stderr)
        return 2
    options = ParseOptions(
        cycle=Cycle(args.cycle), ambiguous_hour=AmbiguousHour[args.ambiguous_hour.upper()], vague=args.vague
    )
    tally = evaluate(args.root, options, limit=args.samples)
    print(report(tally))
    for key in sorted(k for k, items in tally.samples.items() if items):
        print(f"\n== {key}")
        for item in tally.samples[key]:
            print("  ", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
