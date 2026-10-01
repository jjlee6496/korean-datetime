"""설치 없이 폴더를 복사해 쓰는 경우(vendoring): 다른 이름·위치로 복사해도 동작해야 한다"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).parent.parent / "src" / "ko_normalizer"
MODULE_PATH = re.compile(r"ko_normalizer(\.\w+)+")  # 'ko_normalizer.temporal.data' 같은 절대 모듈 경로


def test_package_never_imports_itself_by_absolute_name() -> None:
    """절대 import('from ko_normalizer…')나 패키지 이름 문자열이 있으면 다른 이름으로 복사했을 때 깨진다"""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and (node.module or "").startswith("ko_normalizer")
            ):
                offenders.append(f"{path.name}:{node.lineno} from {node.module}")
            if isinstance(node, ast.Import) and any(a.name.startswith("ko_normalizer") for a in node.names):
                offenders.append(f"{path.name}:{node.lineno} import")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and MODULE_PATH.fullmatch(node.value)
            ):
                offenders.append(f"{path.name}:{node.lineno} 모듈 경로 문자열 {node.value!r}")
    assert offenders == []


def test_vendored_copy_under_another_name_works(tmp_path: Path) -> None:
    """설치된 패키지가 보이지 않게(-S: site-packages 제외) 실행해 복사본만으로 동작하는지 확인"""
    vendor = tmp_path / "myapp" / "_vendor"
    vendor.mkdir(parents=True)
    (tmp_path / "myapp" / "__init__.py").write_text("")
    (vendor / "__init__.py").write_text("")
    shutil.copytree(PACKAGE, vendor / "temporal_ko", ignore=shutil.ignore_patterns("__pycache__"))
    script = (
        "from datetime import datetime\n"
        "from myapp._vendor.temporal_ko import parse, reference_time\n"
        "now = datetime(2026, 9, 28, 14, 30)\n"
        "print(parse('내일 3시', now=now).start.isoformat())\n"
        "print(parse('추석', now=now).start.date().isoformat())\n"  # 패키지 데이터(holidays.json) + 음력
        "with reference_time(now):\n"
        "    print(parse('모레').start.date().isoformat())\n"
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(tmp_path), "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["2026-09-29T15:00:00", "2027-09-15", "2026-09-30"]
