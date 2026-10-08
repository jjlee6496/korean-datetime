# ruff: noqa: E501  (마크다운 문서 문장을 만드는 스크립트라 줄 길이 제한을 적용하지 않음)
"""korean-datetime · Duckling · dateparser를 같은 한국어 문장으로 비교해 마크다운 표 만들기

    docker run -d -p 8000:8000 rasa/duckling          # Duckling 서버
    uv run --with dateparser python scripts/compare_libraries.py --aihub <데이터 루트> > /tmp/comparison-http.md

직접 호출 속도 재현은 scripts/native_benchmark/와 docs/benchmarks/2026-10-02-native/README.md 참고.
이 스크립트의 속도 표는 Duckling HTTP 호출을 포함하므로 native 속도 표를 덮어쓰지 않습니다.

비교 라이브러리는 이 스크립트에서만 쓰며 korean-datetime의 의존성이 아닙니다.
두 갈래로 나눠 셉니다:
- A. 외부 데이터: AI허브 「시간 표현 탐지 데이터」 Training에서 표현 유형별로 고정 시드로 뽑은 문장과
  시간 표현이 없는 문장. 기준 시각은 문서 작성 시각. 정답 값 중 정해진 부분(연·월·일·시·분)만 비교
- B. 구성 표현: 이 저장소의 식 정답셋(temporal_gold.jsonl)을 기준 시각 하나에서 계산.
  **직접 만든 데이터라 korean-datetime에 유리**하므로 A와 따로 봐야 함
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import random
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aihub_eval import FULL, LUNAR_HOLIDAY, PARTIAL, _documents, _gold_spans, gold_class

from korean_datetime import Cycle, ParseOptions, TemporalParser
from korean_datetime.temporal.expectation import evaluate_expectation

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "tests" / "data" / "temporal_gold.jsonl"
CURATED_NOW = datetime(2026, 10, 1, 14, 30)  # 목요일
KST = timezone(timedelta(hours=9))
LIBRARIES = ("korean-datetime", "Duckling", "dateparser")
NEWS_SETTING = "korean-datetime (cycle=nearest)"  # 뉴스 권장 설정. 기본값 비교와 따로 표시


@dataclass(frozen=True)
class Prediction:
    span: tuple[int, int]
    start: datetime
    end: datetime | None
    is_range: bool


Predict = Callable[[str, datetime], list[Prediction]]


# ---------------------------------------------------------------- 라이브러리 어댑터 (공통 형식으로)


def korean_datetime_predict(options: ParseOptions | None = None) -> Predict:
    parser = TemporalParser(options)

    def predict(text: str, now: datetime) -> list[Prediction]:
        return [Prediction(r.span, r.start, r.end, r.is_range) for r in parser.parse_all(text, now=now)]

    return predict


def _naive(value: str | None) -> datetime | None:
    """Duckling 값(ISO 문자열). '0000-…'처럼 datetime으로 나타낼 수 없는 값은 결과 없음으로"""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except ValueError:
        return None


def duckling_predict(url: str) -> Predict:
    def predict(text: str, now: datetime) -> list[Prediction]:
        payload = {"locale": "ko_KR", "text": text, "dims": '["time"]', "tz": "Asia/Seoul"}
        payload["reftime"] = str(int(now.replace(tzinfo=KST).timestamp() * 1000))  # 기준 시각은 한국 시각
        with urllib.request.urlopen(
            f"{url}/parse", urllib.parse.urlencode(payload).encode(), timeout=30
        ) as res:
            entities = json.load(res)
        out = []
        for e in sorted(entities, key=lambda e: e["start"]):
            v = e["value"]
            if v.get("type") == "interval":
                start, end = _naive(v.get("from", {}).get("value")), _naive(v.get("to", {}).get("value"))
                first = start or end
                if first is not None:
                    out.append(
                        Prediction((e["start"], e["end"]), first, end, start is not None and end is not None)
                    )
            elif (start := _naive(v.get("value"))) is not None:
                out.append(Prediction((e["start"], e["end"]), start, None, False))
        return out

    return predict


def dateparser_predict() -> Predict:
    search = importlib.import_module("dateparser.search").search_dates

    def predict(text: str, now: datetime) -> list[Prediction]:
        settings = {"RELATIVE_BASE": now, "PREFER_DATES_FROM": "future"}
        found: Any = search(text, languages=["ko"], settings=settings) or []
        out, cursor = [], 0
        for body, value in found:
            at = text.find(body, cursor)
            at = at if at >= 0 else text.find(body)
            cursor = at + len(body) if at >= 0 else cursor
            out.append(
                Prediction((max(at, 0), max(at, 0) + len(body)), value.replace(tzinfo=None), None, False)
            )
        return out

    return predict


# ---------------------------------------------------------------- 값 비교


def _same_parts(pred: datetime, value: str) -> bool | None:
    """정답 TIMEX 값의 정해진 부분만 비교. 오전/오후 없는 시각은 12시간 단위 (세 라이브러리 똑같이)"""
    full, partial = FULL.match(value), PARTIAL.match(value)
    if full:
        year, month, day, hour, minute = full.groups()
        parts = [(pred.year, year)]
    elif partial:
        month, day, hour, minute = partial.groups()
        parts = []
    else:
        return None
    parts += [(pred.month, month), (pred.day, day)]
    if not all(g in (None, "XX") or got == int(g) for got, g in parts):
        return False
    return hour is None or (pred.hour % 12, pred.minute) == (int(hour) % 12, int(minute))


# ---------------------------------------------------------------- A. AI허브 표본


_CATEGORIES: tuple[tuple[str, str], ...] = (
    (
        "기간 전후",
        r"\d+\s*(?:일|주|주일|달|개월|년|시간|분)\s*(?:후|뒤|전)|(?:하루|이틀|사흘|한 ?달|일주일)\s*(?:후|뒤|전)",
    ),
    ("시각", r"\d+\s*시|\d+:\d\d|정오|자정|[한두세네다여일아열]+\s*시"),
    ("명절·기념일", r"추석|설날|설 |크리스마스|성탄|광복절|어린이날|한글날|개천절|삼일절|현충일|부처님"),
    ("요일", r"[월화수목금토일]요일"),
    ("상대 일", r"오늘|내일|모레|글피|어제|그제|그저께|그끄저께|당일|명일|금일|익일|전날|다음날|이튿날"),
    (
        "상대 주·월·년",
        r"(?:이번|다음|지난|저번|다다음|이달|이번 ?달|다음 ?달|지난 ?달)\s*(?:주|달|해)|올해|작년|지난해|내년|금년|전년|전월|익월",
    ),
    ("월·일", r"\d+\s*월\s*\d+\s*일|\d{4}\s*년|\d+\s*월|\d+\s*일"),
)


def _category(label: str) -> str | None:
    return next((name for name, pattern in _CATEGORIES if re.search(pattern, label)), None)


@dataclass(frozen=True)
class AihubCase:
    domain: str
    category: str
    text: str
    span: tuple[int, int]
    value: str
    now: datetime


def _comparable(domain: str, timex: dict[str, Any]) -> bool:
    """값을 비교할 수 있는 정답만: 뉴스는 완전한 값(작성 시각 기준으로 풀림), 그 밖은 정해진 부분이 있는 값.
    음력 명절은 정답이 음력 표기(추석 = XXXX-08-15)라 어떤 라이브러리도 맞출 수 없어 뺌"""
    cls = gold_class(timex["value"])
    wanted = cls == "explicit" if domain == "news" else cls in ("explicit", "partial")
    return wanted and not LUNAR_HOLIDAY.search(timex["text"])


def _aihub_pool(root: Path) -> tuple[list[AihubCase], list[tuple[str, str, datetime]]]:
    cases, empty = [], []
    for domain, document in _documents(root / "Training" / "02.라벨링데이터"):
        now = datetime.fromisoformat(document["meta_info"]["info.date_created"][:19])
        for sentence in document.get("sentences") or document.get("utterances") or []:
            gold = _gold_spans(sentence)
            if not gold:
                empty.append((domain, sentence["text"], now))
            for start, end, timex in gold:
                category = _category(timex["text"])
                if timex["type"] in ("DATE", "TIME") and category and _comparable(domain, timex):
                    cases.append(
                        AihubCase(domain, category, sentence["text"], (start, end), timex["value"], now)
                    )
    return cases, empty


def _stratified(cases: list[AihubCase], per_category: int, seed: int) -> list[AihubCase]:
    rng = random.Random(seed)
    groups: dict[str, list[AihubCase]] = defaultdict(list)
    for case in cases:
        groups[case.category].append(case)
    return [
        c for name, _ in _CATEGORIES for c in rng.sample(groups[name], min(per_category, len(groups[name])))
    ]


def _candidates(hit: Prediction, gold_span: tuple[int, int]) -> list[datetime]:
    """정답과 비교할 값. 범위의 뒷부분('7시부터 9시까지'의 9시)이 정답이면 범위 끝.
    끝 표기 관례가 라이브러리마다 달라(9시 / 10시 / 다음 날 0시) 셋 다 허용"""
    if hit.is_range and hit.end is not None and gold_span[0] > hit.span[0]:
        return [hit.end, hit.end - timedelta(hours=1), hit.end - timedelta(days=1)]
    return [hit.start]


def _score_aihub(cases: list[AihubCase], predictors: dict[str, Predict]) -> dict[str, Counter[str]]:
    scores: dict[str, Counter[str]] = {name: Counter() for name in predictors}
    for case in cases:
        for name, predict in predictors.items():
            preds = predict(case.text, case.now)
            hit = next((p for p in preds if p.span[0] < case.span[1] and case.span[0] < p.span[1]), None)
            ok = hit is not None and any(
                bool(_same_parts(c, case.value)) for c in _candidates(hit, case.span)
            )
            for key in ("전체", case.category):
                scores[name][f"{key}.n"] += 1
                scores[name][f"{key}.found"] += hit is not None
                scores[name][f"{key}.ok"] += ok
    return scores


def _score_false_alarms(
    sentences: list[tuple[str, str, datetime]], predictors: dict[str, Predict]
) -> Counter[str]:
    """시간 표현이 없는 문장에서 결과를 하나라도 낸 문장 수"""
    counts: Counter[str] = Counter()
    for _, text, now in sentences:
        for name, predict in predictors.items():
            counts[name] += bool(predict(text, now))
    return counts


# ---------------------------------------------------------------- B. 구성 표현 (자체 정답셋)


_CURATED_BUCKETS = {
    "relative_day": "상대 일·주·월", "relative_word": "상대 일·주·월", "weekday": "상대 일·주·월",
    "weekday_modifier": "상대 일·주·월", "month_relative": "상대 일·주·월",
    "day_offset": "기간 전후", "relative_time": "기간 전후",
    "range": "범위", "week_range": "범위", "month_year_range": "범위",
    "clock": "시각", "period": "시각", "datetime": "날짜+시각",
    "holiday": "명절·기념일", "month_day": "월·일", "formatted": "월·일",
    "negative": "인식하면 안 됨", "invalid_date": "인식하면 안 됨", "duration_not_date": "인식하면 안 됨",
}  # fmt: skip


def _curated_rows() -> Iterator[tuple[str, str, str]]:
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if "text" in row and row["category"] in _CURATED_BUCKETS:
            yield _CURATED_BUCKETS[row["category"]], row["text"], row["expect"]


def _range_end_ok(got: datetime | None, want: datetime) -> bool:
    """끝 표기 관례 차이는 허용: 반열린 끝(17:00) 또는 마지막 단위 포함 끝(18:00)"""
    return got is not None and got in (want, want + timedelta(hours=1), want - timedelta(microseconds=0))


def _score_curated(predictors: dict[str, Predict]) -> dict[str, Counter[str]]:
    scores: dict[str, Counter[str]] = {name: Counter() for name in predictors}
    for bucket, text, expect in _curated_rows():
        want = evaluate_expectation(expect, CURATED_NOW)
        for name, predict in predictors.items():
            preds = predict(text, CURATED_NOW)
            first = preds[0] if preds else None
            if want is None:
                ok = first is None
            elif first is None:
                ok = False
            elif want.kind == "date":
                ok = first.start.date() == want.start.date()
            else:
                ok = first.start.replace(second=0) == want.start.replace(second=0)
            if ok and want is not None and want.grain == "range":
                ok = (
                    first is not None
                    and first.is_range
                    and want.end is not None
                    and _range_end_ok(first.end, want.end)
                )
            scores[name][f"{bucket}.n"] += 1
            scores[name][f"{bucket}.ok"] += ok
            scores[name]["전체.n"] += 1
            scores[name]["전체.ok"] += ok
    return scores


# ---------------------------------------------------------------- 속도


@dataclass(frozen=True)
class Speed:
    median_ms: float
    p95_ms: float
    per_second: float


def _measure_speed(sentences: list[tuple[str, datetime]], predict: Predict, warmup: int = 10) -> Speed:
    """문장 하나씩 호출해 걸린 시간. 처음 warmup번은 예열(캐시·연결)로 버림"""
    for text, now in sentences[:warmup]:
        predict(text, now)
    times = []
    for text, now in sentences:
        started = time.perf_counter()
        predict(text, now)
        times.append(time.perf_counter() - started)
    ordered = sorted(times)
    return Speed(
        median_ms=1000 * ordered[len(ordered) // 2],
        p95_ms=1000 * ordered[int(len(ordered) * 0.95)],
        per_second=len(times) / sum(times),
    )


def _platform() -> str:
    return f"{platform.machine()} · Python {platform.python_version()} · {platform.system()}"


# ---------------------------------------------------------------- 표


def _pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.0f}%" if denominator else "-"


def _table(
    rows: list[str],
    cells: Callable[[str, str], str],
    header: str,
    label: Callable[[str], str] = str,
    extra: tuple[str, ...] = (),
) -> list[str]:
    """기본 설정 세 라이브러리 중 가장 좋은 값은 굵게. extra 열(권장 설정)은 굵게 비교에서 뺌"""
    names = (*LIBRARIES, *extra)
    lines = [f"| {header} | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for row in rows:
        values = [cells(lib, row) for lib in LIBRARIES]
        numeric = [float(v.rstrip("%")) for v in values if v.endswith("%")]
        best = max(numeric) if numeric else None
        shown = [
            f"**{v}**" if best is not None and v.endswith("%") and float(v.rstrip("%")) == best else v
            for v in values
        ]
        shown += [f"_{cells(lib, row)}_" for lib in extra]
        lines.append(f"| {label(row)} | " + " | ".join(shown) + " |")
    return lines


def build(aihub_root: Path, duckling_url: str, per_category: int, negatives: int, seed: int) -> str:
    predictors = {
        "korean-datetime": korean_datetime_predict(),
        "Duckling": duckling_predict(duckling_url),
        "dateparser": dateparser_predict(),
        NEWS_SETTING: korean_datetime_predict(ParseOptions(cycle=Cycle.NEAREST)),
    }
    compared = tuple(predictors)
    pool, empty = _aihub_pool(aihub_root)
    sample = _stratified(pool, per_category, seed)
    no_time = random.Random(seed).sample(empty, min(negatives, len(empty)))
    a = _score_aihub(sample, predictors)
    fa = _score_false_alarms(no_time, predictors)
    b = _score_curated(predictors)
    timed = [(c.text, c.now) for c in sample] + [(text, now) for _, text, now in no_time]
    speeds = {lib: _measure_speed(timed, predictors[lib]) for lib in compared}
    duckling_floor = _measure_speed([(".", now) for _, now in timed[:200]], predictors["Duckling"])
    avg_chars = statistics.mean(len(text) for text, _ in timed)
    categories = ["전체", *[name for name, _ in _CATEGORIES]]
    buckets = ["전체", *dict.fromkeys(_CURATED_BUCKETS.values())]
    dateparser_version = importlib.import_module("dateparser").__version__
    return "\n".join(
        [
            "# 라이브러리 비교: 같은 한국어 문장, 같은 기준 시각",
            "",
            "데이터 출처: AI허브(한국지능정보사회진흥원) [「시간 표현 탐지 데이터」](https://aihub.or.kr) Training.",
            "데이터는 이 저장소에 포함하지 않습니다.",
            "",
            f"비교 대상: [Duckling](https://github.com/facebook/duckling) (HTTP 서버, `ko_KR`), "
            f"[dateparser](https://github.com/scrapinghub/dateparser) {dateparser_version} (`languages=['ko']`). "
            "Microsoft Recognizers-Text는 한국어 DateTime이 아직 등록되지 않아 제외했습니다.",
            "",
            "`uv run --with dateparser python scripts/compare_libraries.py --aihub <데이터 루트>`로 다시 만듭니다. "
            f"표본은 고정 시드({seed})로 뽑습니다.",
            "",
            "## A. 외부 데이터 (AI허브, 공정 비교)",
            "",
            f"표현 유형별 최대 {per_category}개씩 뽑은 {len(sample)}개 표현. 기준 시각은 문서 작성 시각입니다.",
            "**정확도** = 그 표현을 찾았고 값의 정해진 부분(연·월·일·시·분)이 정답과 같은 비율 (못 찾으면 틀림).",
            "오전/오후가 문장에 없는 시각은 세 라이브러리 모두 12시간 단위로 비교합니다.",
            "유형은 정답 표현의 글자로 나눴습니다 (먼저 맞는 유형 하나).",
            "",
            "정확도",
            "",
            *_table(
                categories,
                lambda lib, c: _pct(a[lib][f"{c}.ok"], a[lib][f"{c}.n"]),
                "유형 (표현 수)",
                label=lambda c: f"{c} ({a['Duckling'][f'{c}.n']})",
                extra=(NEWS_SETTING,),
            ),
            "",
            f"_{NEWS_SETTING}_ 열은 뉴스용 권장 설정입니다(기울임, 굵게 비교에서 제외). "
            f"표본의 {_pct(sum(c.domain == 'news' for c in sample), len(sample))}가 뉴스이고, 나머지 열은 모두 기본 설정입니다.",
            "",
            "검출률 (값과 상관없이 위치만)",
            "",
            *_table(
                categories,
                lambda lib, c: _pct(a[lib][f"{c}.found"], a[lib][f"{c}.n"]),
                "유형",
                extra=(NEWS_SETTING,),
            ),
            "",
            "이 표본에서 korean-datetime이 놓친 표현은 대부분 혼자 쓴 '전날', '하루 전날', '이튿날'입니다.",
            "앞 문장을 가리키는 말이라 일부러 인식하지 않는데, 뉴스에서는 대개 기사 전날이라 Duckling이 점수를 얻습니다.",
            "이 표본(Training)은 처음 보는 데이터로 남겨 두려고 여기서 나온 오류로 규칙을 고치지 않았습니다.",
            "",
            f"오탐률: 시간 표현이 하나도 없는 문장 {len(no_time)}개에서 무언가를 시간으로 낸 비율 (낮을수록 좋음)",
            "",
            "| | " + " | ".join(compared) + " |",
            "|---|" + "---:|" * len(compared),
            "| 오탐률 | "
            + " | ".join(
                f"{fa[lib] / len(no_time):.1%} ({fa[lib]}/{len(no_time)})" if no_time else "—"
                for lib in compared
            )
            + " |",
            "",
            "이 표본에서 Duckling의 오탐은 대개 숫자나 낱말 조각이었습니다 ('2천 명분'의 2천, '1,573명', '춘천'의 천, '일반', '이후').",
            "",
            "### 실패 사례를 읽는 방법",
            "",
            "아래는 위 측정에서 관찰한 표현 조각을 풀어 쓴 설명입니다. 새로 측정한 점수나 원문 전체가 아니며, 개별 사례만으로 전체 성능을 판단하지 않습니다.",
            "",
            "| 표현 / 상황 | 관찰된 한계 | 사용 시 의미 |",
            "|---|---|---|",
            "| 단독 `전날`, `하루 전날`, `이튿날` | korean-datetime은 선행 문맥 없이 날짜를 정하지 않아 놓칩니다. 이 표본에서는 Duckling이 정답을 얻는 경우가 있습니다. | 문맥 의존 표현까지 필요하면 앞 문장의 기준 날짜를 별도로 처리해야 합니다. |",
            "| `2천 명분`, `1,573명` | Duckling이 인원 수의 일부를 시간으로 검출한 오탐이 있었습니다. | 숫자 검출 범위가 넓을수록 비시간 문장도 함께 평가해야 합니다. |",
            "| `춘천`의 `천`, `일반` | Duckling이 낱말 조각을 시간으로 검출한 오탐이 있었습니다. | 한국어 단어 경계가 정밀도에 영향을 줍니다. |",
            "| 연·월이 생략된 뉴스 날짜 | korean-datetime 기본 `FUTURE`는 지난 일을 미래로 해석할 수 있습니다. | `NEAREST` 열을 기본값과 분리해 비교하고, 실제 용도에 맞게 설정합니다. |",
            "",
            "korean-datetime도 오탐이 없는 파서는 아닙니다. 이 표본은 Training에서 추출했으며 독립적인 미공개 테스트셋 성능으로 해석하지 않습니다.",
            "## 속도",
            "",
            f"A의 문장 {len(timed)}개(평균 {avg_chars:.0f}자)를 하나씩 넣었을 때 문장당 걸린 시간. 처음 10번은 예열로 버립니다.",
            f"측정 환경: {_platform()}.",
            "",
            "| | " + " | ".join(compared) + " |",
            "|---|" + "---:|" * len(compared),
            "| 중앙값 (ms/문장) | " + " | ".join(f"{speeds[lib].median_ms:.2f}" for lib in compared) + " |",
            "| 95번째 백분위 (ms/문장) | "
            + " | ".join(f"{speeds[lib].p95_ms:.2f}" for lib in compared)
            + " |",
            "| 처리량 (문장/초) | " + " | ".join(f"{speeds[lib].per_second:,.0f}" for lib in compared) + " |",
            "",
            "- korean-datetime과 dateparser는 같은 프로세스 안에서 함수로 호출합니다.",
            "- dateparser는 한국어 문장 대부분에서 아무것도 찾지 못하고 끝나서(검출률 위 표 참고) 빠르게 나옵니다.",
            f"- Duckling은 별도 서버(Haskell)에 HTTP로 요청하므로 통신 시간이 들어갑니다. 빈 문장('.')만 보내도 중앙값 "
            f"{duckling_floor.median_ms:.2f}ms가 걸렸습니다. 이 값에도 서버의 분석·직렬화 비용이 포함되므로 순수 통신 비용으로 빼지 않습니다.",
            "  Python 직접 호출과 Duckling HTTP 호출의 시간을 파서 자체 속도로 비교하지 않습니다.",
            "  native 직접 호출 비교는 docs/benchmarks/2026-10-02-native/README.md를 참고하세요.",
            "",
            "## B. 구성 표현 (자체 정답셋, korean-datetime에 유리)",
            "",
            f"이 저장소의 정답셋을 {CURATED_NOW:%Y-%m-%d %H:%M}(목) 기준으로 계산한 값과 첫 결과를 비교합니다.",
            "korean-datetime을 만들며 쓴 데이터이므로 **절대 성능이 아니라 어떤 유형을 다루는지** 보는 용도입니다.",
            "범위는 시작과 끝이 모두 맞아야 정답 (끝 표기 관례 차이, 예: 17:00과 18:00은 허용).",
            "정답은 korean-datetime의 해석 정책을 따릅니다. 예를 들어 '다음 주말'을 다음 주의 주말로 보는데,",
            "Duckling은 이번 주말로 봅니다. 이렇게 정책이 갈리는 표현은 틀린 것으로 셉니다.",
            "",
            *_table(
                buckets,
                lambda lib, c: _pct(b[lib][f"{c}.ok"], b[lib][f"{c}.n"]),
                "유형 (문장 수)",
                label=lambda c: f"{c} ({b['Duckling'][f'{c}.n']})",
                extra=(NEWS_SETTING,),
            ),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aihub", type=Path, required=True, help="Training/02.라벨링데이터가 있는 데이터 루트")
    ap.add_argument("--duckling", default="http://localhost:8000", help="Duckling 서버 주소")
    ap.add_argument("--per-category", type=int, default=50, help="A: 유형별 표본 수")
    ap.add_argument("--negatives", type=int, default=200, help="A: 시간 표현이 없는 문장 수")
    ap.add_argument("--seed", type=int, default=20261001)
    args = ap.parse_args(argv)
    if not (args.aihub / "Training" / "02.라벨링데이터").is_dir():
        print(f"Training 라벨링데이터가 없습니다: {args.aihub}", file=sys.stderr)
        return 2
    print(build(args.aihub, args.duckling, args.per_category, args.negatives, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
