"""korean_datetime를 설치 없이 다른 프로젝트에 복사(vendoring)합니다.

    uv run python scripts/vendor.py <대상 폴더> [--name 이름] [--force]
    uv run python scripts/vendor.py --check <복사본 폴더>

- 복사본에 VENDORED.json(버전, 파일별 sha256)을 남깁니다.
- --check: 복사본이 복사 당시와 같은지 검사합니다. 복사본은 직접 고치지 않는 것이 원칙입니다.
- 이미 있는 복사본이 수정되었으면 --force 없이는 덮어쓰지 않습니다.
  VENDORED.json이 없는 폴더(이 스크립트가 만들지 않은 폴더)는 --force여도 덮어쓰지 않습니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "korean_datetime"
MANIFEST = "VENDORED.json"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", MANIFEST)


def _version() -> str:
    for line in (SOURCE / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("__version__을 찾을 수 없습니다")


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.name != MANIFEST
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def check(copy: Path) -> list[str]:
    """복사 당시와 달라진 파일 목록 (수정/추가/삭제)"""
    manifest_path = copy / MANIFEST
    if not manifest_path.exists():
        return [f"{MANIFEST}이 없습니다 (vendor.py로 만든 복사본이 아님)"]
    recorded: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    current = _hashes(copy)
    problems = [
        f"수정됨: {name}"
        for name in sorted(recorded.keys() & current.keys())
        if recorded[name] != current[name]
    ]
    problems += [f"추가됨: {name}" for name in sorted(current.keys() - recorded.keys())]
    problems += [f"삭제됨: {name}" for name in sorted(recorded.keys() - current.keys())]
    return problems


def vendor(target_dir: Path, name: str, force: bool) -> int:
    destination = target_dir / name
    if destination.exists():
        if not (destination / MANIFEST).exists():
            print(f"거부: {destination}는 vendor.py가 만든 복사본이 아닙니다 ({MANIFEST} 없음).")
            print("      직접 확인한 뒤 지우세요.")
            return 1
        problems = check(destination)
        if problems and not force:
            print("거부: 기존 복사본이 수정되었습니다. 덮어쓰려면 --force\n  " + "\n  ".join(problems))
            return 1
        shutil.rmtree(destination)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, destination, ignore=IGNORE)
    manifest = {
        "package": "korean_datetime",
        "vendored_as": name,
        "version": _version(),
        "copied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "직접 수정하지 말고 원본 저장소에서 고친 뒤 scripts/vendor.py로 다시 복사하세요.",
        "files": _hashes(destination),
    }
    (destination / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"복사함: {destination} (버전 {manifest['version']}, 파일 {len(manifest['files'])}개)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="korean_datetime를 설치 없이 복사(vendoring)합니다.")
    parser.add_argument(
        "target", type=Path, help="복사할 상위 폴더 (예: myapp/_vendor), --check면 복사본 폴더"
    )
    parser.add_argument(
        "--name", default="korean_datetime", help="복사본 패키지 이름 (기본: korean_datetime)"
    )
    parser.add_argument("--force", action="store_true", help="수정된 복사본도 덮어씀")
    parser.add_argument("--check", action="store_true", help="복사본이 복사 당시와 같은지 검사")
    args = parser.parse_args(argv)
    if args.check:
        problems = check(args.target)
        print("\n".join(problems) if problems else f"변경 없음: {args.target}")
        return 1 if problems else 0
    return vendor(args.target, args.name, args.force)


if __name__ == "__main__":
    sys.exit(main())
