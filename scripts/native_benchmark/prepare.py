"""Prepare private inputs; never commit the generated corpus or parser responses."""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_libraries import (
    CURATED_NOW,
    KST,
    _aihub_pool,
    _curated_rows,
    _stratified,
)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--aihub", type=Path)
    source.add_argument("--reuse-corpus", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.reuse_corpus:
        corpus = [json.loads(line) for line in args.reuse_corpus.read_text().splitlines()]
    else:
        pool, empty = _aihub_pool(args.aihub)
        corpus = []
        for c in _stratified(pool, 50, 20261001):
            corpus.append(
                {
                    "id": len(corpus),
                    "text": c.text,
                    "now": c.now.isoformat(),
                    "reftime": int(c.now.replace(tzinfo=KST).timestamp() * 1000),
                    "domain": c.domain,
                    "category": c.category,
                    "span": list(c.span),
                    "value": c.value,
                    "negative": False,
                }
            )
        for domain, text, now in random.Random(20261001).sample(empty, min(200, len(empty))):
            corpus.append(
                {
                    "id": len(corpus),
                    "text": text,
                    "now": now.isoformat(),
                    "reftime": int(now.replace(tzinfo=KST).timestamp() * 1000),
                    "domain": domain,
                    "negative": True,
                }
            )
    write_rows(args.out / "corpus.jsonl", corpus)
    requests: list[dict[str, Any]] = []
    for round_no in range(6):
        shuffled = list(corpus)
        random.Random(20261002 + round_no).shuffle(shuffled)
        requests.extend(dict(row, round=round_no) for row in shuffled)
    curated = [
        {
            "id": len(corpus) + i,
            "text": text,
            "now": CURATED_NOW.isoformat(),
            "reftime": int(CURATED_NOW.replace(tzinfo=KST).timestamp() * 1000),
            "category": bucket,
            "expect": expect,
            "round": -1,
        }
        for i, (bucket, text, expect) in enumerate(_curated_rows())
    ]
    write_rows(args.out / "curated.jsonl", curated)
    write_rows(args.out / "requests.jsonl", requests + curated)
    print(f"Prepared {len(corpus)} external cases × 6 passes + {len(curated)} curated cases")


if __name__ == "__main__":
    main()
