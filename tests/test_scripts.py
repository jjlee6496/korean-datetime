"""scripts/ 관리 스크립트: 실제로 실행해서 동작을 확인한다"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"


def run(script: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def test_every_script_has_help() -> None:
    for path in sorted(SCRIPTS.glob("*.py")):
        result = run(path.name, "--help")
        assert result.returncode == 0, (path.name, result.stderr)
        assert "usage" in result.stdout.lower(), path.name


# ---------------------------------------------------------------- vendor.py


def test_vendor_copies_package_with_manifest(tmp_path: Path) -> None:
    result = run("vendor.py", str(tmp_path / "_vendor"), "--name", "temporal_ko")
    assert result.returncode == 0, result.stderr
    copy = tmp_path / "_vendor" / "temporal_ko"
    manifest = json.loads((copy / "VENDORED.json").read_text(encoding="utf-8"))
    assert manifest["version"] and manifest["files"]
    assert (copy / "temporal" / "data" / "holidays.json").exists()
    assert not list(copy.rglob("__pycache__"))
    assert run("vendor.py", "--check", str(copy)).returncode == 0


def test_vendor_check_detects_local_edits(tmp_path: Path) -> None:
    run("vendor.py", str(tmp_path), "--name", "ko")
    target = tmp_path / "ko" / "temporal" / "lexicon.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# 로컬 수정\n", encoding="utf-8")
    result = run("vendor.py", "--check", str(tmp_path / "ko"))
    assert result.returncode == 1
    assert "temporal/lexicon.py" in result.stdout


def test_vendor_refuses_to_overwrite_modified_copy(tmp_path: Path) -> None:
    run("vendor.py", str(tmp_path), "--name", "ko")
    (tmp_path / "ko" / "core" / "types.py").write_text("# 수정됨\n", encoding="utf-8")
    assert run("vendor.py", str(tmp_path), "--name", "ko").returncode == 1
    assert run("vendor.py", str(tmp_path), "--name", "ko", "--force").returncode == 0
    assert run("vendor.py", "--check", str(tmp_path / "ko")).returncode == 0


def test_vendor_refuses_non_vendored_directory(tmp_path: Path) -> None:
    (tmp_path / "ko").mkdir()
    (tmp_path / "ko" / "mine.py").write_text("x = 1\n", encoding="utf-8")
    assert run("vendor.py", str(tmp_path), "--name", "ko", "--force").returncode == 1  # 남의 폴더는 덮지 않음


# ---------------------------------------------------------------- gold.py


def test_gold_check_passes_on_repository_gold() -> None:
    result = run("gold.py", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "문제 없음" in result.stdout


def test_gold_check_reports_problems(tmp_path: Path) -> None:
    bad = tmp_path / "gold.jsonl"
    bad.write_text(
        '{"category": "x", "text": "내일", "expect": "today + 1d"}\n'
        '{"category": "x", "text": "내일", "expect": "today + 1d"}\n'
        '{"category": "x", "text": "모레", "expect": "today +"}\n'
        "not json\n",
        encoding="utf-8",
    )
    result = run("gold.py", "check", "--gold", str(bad), "--no-docs")
    assert result.returncode == 1
    for fragment in ("중복", "식 오류", "JSON"):
        assert fragment in result.stdout


def test_gold_add_validates_and_appends(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        '{"category": "relative_day", "text": "내일", "expect": "today + 1d"}\n', encoding="utf-8"
    )
    ok = run(
        "gold.py",
        "add",
        "--gold",
        str(gold),
        "--category",
        "relative_day",
        "--text",
        "모레",
        "--expect",
        "today + 2d",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert '"모레"' in gold.read_text(encoding="utf-8")
    assert (
        run(
            "gold.py", "add", "--gold", str(gold), "--category", "x", "--text", "모레", "--expect", "today"
        ).returncode
        == 1
    )
    wrong = run(
        "gold.py", "add", "--gold", str(gold), "--category", "x", "--text", "글피", "--expect", "today + 1d"
    )
    assert wrong.returncode == 1  # 파서 값과 식이 다르면 기본은 거부
    assert "불일치" in wrong.stdout


def test_gold_show_compares_parser_and_expectation() -> None:
    result = run("gold.py", "show", "3시", "--now", "2026-09-28T14:30", "--now", "2026-09-28T23:50")
    assert result.returncode == 0, result.stderr
    assert "2026-09-28T15:00" in result.stdout and "2026-09-29T03:00" in result.stdout
    assert "meridiem" in result.stdout


# ---------------------------------------------------------------- evaluate.py


def test_evaluate_at_given_references() -> None:
    result = run("evaluate.py", "--now", "2026-09-28T14:30", "--now", "2028-02-29T08:05")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TOTAL" in result.stdout and "ambiguity" in result.stdout


def test_evaluate_date_range() -> None:
    result = run("evaluate.py", "--from", "2026-12-25", "--to", "2027-01-05", "--at", "09:00")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "기준 시각 12개" in result.stdout


# ---------------------------------------------------------------- aihub_eval.py


def _aihub_document(date_created: str, text: str, timex: list[dict[str, object]]) -> dict[str, object]:
    return {"meta_info": {"info.date_created": date_created}, "sentences": [{"text": text, "timex3": timex}]}


def test_aihub_eval_scores_detection_and_values(tmp_path: Path) -> None:
    """TIMEX3 형식의 가짜 데이터: 맞은 값 1, 음력 명절은 값 비교 제외, 오탐 1, 기간은 재현율에서 제외"""
    folder = tmp_path / "VL_뉴스_사회"
    folder.mkdir()
    text = "오늘 회의가 3일 동안 열렸고 추석에 시너지를 낼 수 있는 내일 계획이 있다"
    timex = [
        {"text": "오늘", "extent": [0, 2], "type": "DATE", "value": "2021-03-08"},
        {"text": "3일", "extent": [7, 9], "type": "DURATION", "value": "P3D"},
        {"text": "추석", "extent": [16, 18], "type": "DATE", "value": "XXXX-08-15"},
    ]
    document = _aihub_document("2021-03-08 00:00:00", text, timex)
    (folder / "doc.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    result = run("aihub_eval.py", str(tmp_path), "--samples", "5")
    assert result.returncode == 0, result.stderr
    news = next(line.split() for line in result.stdout.splitlines() if line.startswith("news "))
    assert news[1:3] == ["2", "1.000"]  # 정답 2개(오늘, 추석) 모두 찾음
    assert news[3:5] == ["3", "0.667"]  # 예측 3개 중 '내일'은 정답에 없음
    assert "news.explicit                         1   1.000       1     1.000" in result.stdout
    assert "('내일'," in result.stdout


def test_aihub_eval_rejects_missing_folder(tmp_path: Path) -> None:
    assert run("aihub_eval.py", str(tmp_path / "없음")).returncode == 2
