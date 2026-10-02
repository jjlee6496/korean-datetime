import gc
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from korean_datetime import Cycle, ParseOptions, parse_all

search_dates = importlib.import_module("dateparser.search").search_dates

root = Path(sys.argv[2])
requests = [json.loads(line) for line in (root / "requests.jsonl").read_text().splitlines()]


def korean(text: str, now: datetime) -> list[dict[str, Any]]:
    return [r.to_dict() for r in parse_all(text, now=now)]


NEAREST = ParseOptions(cycle=Cycle.NEAREST)


def nearest(text: str, now: datetime) -> list[dict[str, Any]]:
    return [r.to_dict() for r in parse_all(text, now=now, options=NEAREST)]


def dates(text: str, now: datetime) -> list[dict[str, Any]]:
    found = (
        search_dates(text, languages=["ko"], settings={"RELATIVE_BASE": now, "PREFER_DATES_FROM": "future"})
        or []
    )
    return [{"text": text, "value": value.isoformat()} for text, value in found]


name = sys.argv[1]
fn = {"korean-datetime": korean, "korean-datetime-nearest": nearest, "dateparser": dates}[name]
with (root / (name + "-direct.jsonl")).open("w") as out:
    for item in requests:
        text, now = item["text"], datetime.fromisoformat(item["now"])
        begin = time.perf_counter_ns()
        result = fn(text, now)
        parsed = time.perf_counter_ns()
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        elapsed = time.perf_counter_ns() - begin
        out.write(
            json.dumps(
                {
                    "id": item["id"],
                    "round": item["round"],
                    "ns": elapsed,
                    "parse_ns": parsed - begin,
                    "bytes": len(encoded),
                    "entities": result,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
print(
    json.dumps(
        {
            "name": name,
            "version": importlib.metadata.version(
                "korean-datetime" if name.startswith("korean-datetime") else name
            ),
            "python": platform.python_version(),
            "arch": platform.machine(),
            "gc_enabled": gc.isenabled(),
        }
    )
)
