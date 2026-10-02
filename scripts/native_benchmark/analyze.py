import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_libraries import (
    AihubCase,
    Predict,
    Prediction,
    _naive,
    _score_aihub,
    _score_curated,
    _score_false_alarms,
)

parser = argparse.ArgumentParser(
    description="Score private native benchmark output and export data-free evidence"
)
parser.add_argument("root", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
root = args.root
args.out.mkdir(parents=True, exist_ok=True)
corpus = [json.loads(x) for x in (root / "corpus.jsonl").read_text().splitlines()]
curated = [json.loads(x) for x in (root / "curated.jsonl").read_text().splitlines()]
all_inputs = corpus + curated
cases = [
    AihubCase(
        x["domain"], x["category"], x["text"], tuple(x["span"]), x["value"], datetime.fromisoformat(x["now"])
    )
    for x in corpus
    if not x["negative"]
]
empty = [(x["domain"], x["text"], datetime.fromisoformat(x["now"])) for x in corpus if x["negative"]]
outputs = {
    name: [json.loads(x) for x in (root / file).read_text().splitlines()]
    for name, file in [
        ("Duckling", "duckling-direct.jsonl"),
        ("korean-datetime", "korean-datetime-direct.jsonl"),
        ("korean-datetime-nearest", "korean-datetime-nearest-direct.jsonl"),
        ("dateparser", "dateparser-direct.jsonl"),
        ("Duckling HTTP", "duckling-http.jsonl"),
    ]
}


def predictions(name: str, row: dict[str, Any]) -> list[Prediction]:
    result = []
    cursor = 0
    for e in row["entities"]:
        if name.startswith("Duckling"):
            v = e["value"]
            if v.get("type") == "interval":
                start, end = _naive(v.get("from", {}).get("value")), _naive(v.get("to", {}).get("value"))
                first = start or end
                if first is not None:
                    result.append(
                        Prediction((e["start"], e["end"]), first, end, start is not None and end is not None)
                    )
            elif (start := _naive(v.get("value"))) is not None:
                result.append(Prediction((e["start"], e["end"]), start, None, False))
        elif name.startswith("korean-datetime"):
            result.append(
                Prediction(
                    tuple(e["span"]),
                    datetime.fromisoformat(e["start"]),
                    datetime.fromisoformat(e["end"]),
                    e["is_range"],
                )
            )
        else:
            at = all_inputs[row["id"]]["text"].find(e["text"], cursor)
            if at < 0:
                at = all_inputs[row["id"]]["text"].find(e["text"])
            cursor = at + len(e["text"]) if at >= 0 else cursor
            result.append(
                Prediction(
                    (max(at, 0), max(at, 0) + len(e["text"])), datetime.fromisoformat(e["value"]), None, False
                )
            )
    return sorted(result, key=lambda p: p.span[0])


expected = {
    (x["id"], x["round"])
    for x in [json.loads(line) for line in (root / "requests.jsonl").read_text().splitlines()]
}
for name, rows in outputs.items():
    actual = {(x["id"], x["round"]) for x in rows}
    assert len(rows) == len(actual) == len(expected) and actual == expected, (
        name,
        "missing or duplicate responses",
    )
direct = {(x["id"], x["round"]): x["entities"] for x in outputs["Duckling"]}
http = {(x["id"], x["round"]): x["entities"] for x in outputs["Duckling HTTP"]}
assert direct == http, "Duckling direct and HTTP JSON differ"
predictors: dict[str, Predict] = {}
for name, rows in outputs.items():
    cache: dict[tuple[str, datetime], list[Prediction]] = {}
    for r in rows:
        x = all_inputs[r["id"]]
        key = (x["text"], datetime.fromisoformat(x["now"]))
        value = predictions(name, r)
        if key in cache:
            assert cache[key] == value, (name, "nondeterministic", r["id"])
        cache[key] = value

    def cached_predict(
        text: str, now: datetime, cache: dict[tuple[str, datetime], list[Prediction]] = cache
    ) -> list[Prediction]:
        return cache[text, now]

    predictors[name] = cached_predict

for x in corpus:
    key = (x["text"], datetime.fromisoformat(x["now"]))
    assert predictors["Duckling"](*key) == predictors["Duckling HTTP"](*key), ("HTTP mismatch", x["id"])
scores = _score_aihub(cases, predictors)
fp = _score_false_alarms(empty, predictors)
curated_scores = _score_curated(predictors)
report: dict[str, Any] = {
    "corpus_sha256": hashlib.sha256((root / "corpus.jsonl").read_bytes()).hexdigest(),
    "positive_n": len(cases),
    "negative_n": len(empty),
    "scores": {},
    "timings": {},
    "categories": {name: dict(score) for name, score in scores.items()},
    "curated": {name: dict(score) for name, score in curated_scores.items()},
    "direct_http_equal_responses": len(direct),
}
for name, score in scores.items():
    report["scores"][name] = {
        "correct": score["전체.ok"],
        "found": score["전체.found"],
        "n": score["전체.n"],
        "false_positive_sentences": fp[name],
    }
for name, rows in outputs.items():
    times = [x for x in rows if x["round"] > 0]
    assert len(times) == 5 * len(corpus)
    metrics = {}
    for metric in ["ns", "parse_ns"]:
        if metric not in times[0]:
            continue

        def summarize(items: list[dict[str, Any]], metric: str = metric) -> dict[str, float]:
            samples = sorted(x[metric] / 1e6 for x in items)
            return {
                "median_ms": statistics.median(samples),
                "p95_ms": samples[math.ceil(len(samples) * 0.95) - 1],
                "per_second": len(samples) / (sum(samples) / 1000),
            }

        metrics[metric] = {
            "pooled": summarize(times),
            "rounds": {i: summarize([x for x in times if x["round"] == i]) for i in range(1, 6)},
        }
    report["timings"][name] = metrics
(args.out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
for name, rows in outputs.items():
    filename = name.lower().replace(" ", "-") + "-timings.jsonl"
    with (args.out / filename).open("w") as out:
        for row in rows:
            out.write(
                json.dumps({k: v for k, v in row.items() if k in ("id", "round", "ns", "parse_ns", "bytes")})
                + "\n"
            )
print(
    json.dumps(
        {"scores": report["scores"], "direct_http_equal_responses": len(direct)}, ensure_ascii=False, indent=2
    )
)
