"""내부 기반: 한글 수사 파서, 스캐너 경계 규칙"""

from __future__ import annotations

import re

import pytest

from ko_normalizer.core.numerals import parse_korean_number, parse_native, parse_sino
from ko_normalizer.core.scanner import Scanner, TokenRule


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("일", 1),
        ("십", 10),
        ("십일", 11),
        ("이십", 20),
        ("삼십일", 31),
        ("오십구", 59),
        ("백", 100),
        ("백이십삼", 123),
        ("구백구십구", 999),
    ],
)
def test_parse_sino(text: str, value: int) -> None:
    assert parse_sino(text) == value


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("한", 1),
        ("하나", 1),
        ("두", 2),
        ("세", 3),
        ("석", 3),
        ("열", 10),
        ("열한", 11),
        ("열 두", 12),
        ("스무", 20),
        ("스물네", 24),
        ("서른", 30),
        ("아흔아홉", 99),
    ],
)
def test_parse_native(text: str, value: int) -> None:
    assert parse_native(text) == value


@pytest.mark.parametrize("bad", ["", "십십", "하나둘", "abc", "일일"])
def test_invalid_numbers(bad: str) -> None:
    assert parse_korean_number(bad) is None


def test_parse_korean_number_accepts_all_forms() -> None:
    assert parse_korean_number("15") == 15
    assert parse_korean_number("십오") == 15
    assert parse_korean_number("열다섯") == 15


def test_scanner_longest_match_and_hangul_boundaries() -> None:
    scanner = Scanner(
        [
            TokenRule("short", re.compile(r"내일"), lambda m: m.group()),
            TokenRule("long", re.compile(r"내일\s*모레"), lambda m: m.group()),
            TokenRule("oil", re.compile(r"오일"), lambda m: m.group(), right_boundary=True),
        ]
    )
    assert [t.kind for t in scanner.scan("내일모레")] == ["long"]
    assert [t.kind for t in scanner.scan("그내일")] == []  # 단어 중간에서 시작하지 않음
    assert [t.kind for t in scanner.scan("오일에")] == ["oil"]  # 조사는 허용
    assert [t.kind for t in scanner.scan("오일교환")] == []  # 단어가 이어지면 거부


def test_scanner_rejecting_builder_skips_match() -> None:
    scanner = Scanner(
        [TokenRule("even", re.compile(r"\d+"), lambda m: int(m.group()) if int(m.group()) % 2 == 0 else None)]
    )
    assert [t.value for t in scanner.scan("3 4")] == [4]


def test_parse_korean_number_rejects_non_decimal_digits() -> None:
    assert parse_korean_number("²") is None
    assert parse_korean_number("１５") == 15  # 전각 숫자
