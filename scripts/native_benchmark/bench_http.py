import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(sys.argv[1])
with (root / "duckling-http.jsonl").open("w") as out:
    for line in (root / "requests.jsonl").read_text().splitlines():
        item = json.loads(line)
        data = urllib.parse.urlencode(
            {
                "text": item["text"],
                "locale": "ko_KR",
                "dims": '["time"]',
                "tz": "Asia/Seoul",
                "reftime": item["reftime"],
            }
        ).encode()
        begin = time.perf_counter_ns()
        with urllib.request.urlopen("http://127.0.0.1:8000/parse", data, timeout=30) as res:
            entities = json.load(res)
        elapsed = time.perf_counter_ns() - begin
        out.write(
            json.dumps(
                {"id": item["id"], "round": item["round"], "ns": elapsed, "entities": entities},
                ensure_ascii=False,
            )
            + "\n"
        )
