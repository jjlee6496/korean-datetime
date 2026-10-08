"""공개 API, 결과 모델, 입력 검증, 직렬화, CLI (기준: 2026-09-28 14:30)"""

from __future__ import annotations

import json
from datetime import date, time, timedelta, timezone

import pytest
from helpers import NOW, at, days, must

from korean_datetime import (
    Grain,
    Kind,
    TemporalParser,
    parse,
    parse_all,
    parse_date,
    parse_datetime,
    parse_time,
)
from korean_datetime.__main__ import main


def test_convenience_functions() -> None:
    assert parse_date("다음주 월요일", now=NOW) == days(7)
    assert parse_date("다음주 월요일 3시", now=NOW) == days(7)
    assert parse_time("저녁 7시 반", now=NOW) == time(19, 30)
    assert parse_time("내일", now=NOW) is None
    assert parse_datetime("내일 오후 3시", now=NOW) == at(2026, 9, 29, 15)
    assert parse_datetime("내일", now=NOW) == at(2026, 9, 29)
    assert parse_date("아무것도 없음", now=NOW) is None


def test_kind_grain_and_value() -> None:
    assert (must("내일").kind, must("내일").grain, must("내일").value) == (Kind.DATE, Grain.DAY, days(1))
    assert must("내일").time is None
    assert must("다음주").grain is Grain.WEEK
    assert must("다음달").grain is Grain.MONTH
    assert must("올해").grain is Grain.YEAR
    assert must("주말").grain is Grain.DAY
    three = must("3시")
    assert (three.kind, three.grain, three.value) == (Kind.TIME, Grain.HOUR, time(15))
    assert must("3시 30분").grain is Grain.MINUTE
    assert must("1시간 후").kind is Kind.DATETIME
    assert must("내일 3시").value == at(2026, 9, 29, 15)


def test_range_flag_and_text() -> None:
    ranged = must("3시부터 5시까지")
    assert ranged.is_range and ranged.text == "3시부터 5시까지"
    assert not must("주말").is_range


def test_parse_all_finds_each_expression_with_span() -> None:
    text = "내일 3시에 보고 모레 5시에 또 보자"
    results = parse_all(text, now=NOW)
    assert [r.start for r in results] == [at(2026, 9, 29, 15), at(2026, 9, 30, 17)]
    assert [r.text for r in results] == ["내일 3시", "모레 5시"]
    for r in results:
        assert text[r.span[0] : r.span[1]] == r.text


def test_now_can_be_a_date() -> None:
    result = parse("내일", now=date(2026, 9, 28))
    assert result is not None and result.start == at(2026, 9, 29)


def test_timezone_is_preserved() -> None:
    kst = timezone(timedelta(hours=9))
    result = parse("내일 3시", now=NOW.replace(tzinfo=kst))
    assert result is not None
    assert result.start.tzinfo is kst


def test_input_validation() -> None:
    with pytest.raises(TypeError):
        parse(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        parse("내일", now="2026-09-28")  # type: ignore[arg-type]
    assert parse("", now=NOW) is None
    assert parse_all("", now=NOW) == []


def test_to_dict() -> None:
    assert must("내일 저녁 7시").to_dict() == {
        "text": "내일 저녁 7시",
        "span": [0, 8],
        "kind": "datetime",
        "grain": "hour",
        "start": "2026-09-29T19:00:00",
        "end": "2026-09-29T20:00:00",
        "value": "2026-09-29T19:00:00",
        "is_range": False,
        "ambiguities": [],
    }
    assert must("내일").to_dict()["value"] == "2026-09-29"
    assert must("3시").to_dict()["value"] == "15:00:00"


def test_parser_is_reusable_and_results_immutable() -> None:
    parser = TemporalParser()
    first = parser.parse("내일", now=NOW)
    assert first == parser.parse("내일", now=NOW)
    with pytest.raises(AttributeError):
        first.text = "x"  # type: ignore[misc, union-attr]


def test_kind_values() -> None:
    assert {k.value for k in Kind} == {
        "date",
        "time",
        "datetime",
        "duration",
        "vague",
    }  # vague는 ParseOptions(vague=True)일 때만


def test_cli_outputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["내일 3시에 보고 모레 5시", "--now", "2026-09-28T14:30", "--all"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["value"] for line in lines] == ["2026-09-29T15:00:00", "2026-09-30T17:00:00"]


def test_cli_no_match_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["아무 말", "--now", "2026-09-28T14:30"]) == 1
    assert capsys.readouterr().out == ""


def test_cli_rejects_bad_now() -> None:
    with pytest.raises(SystemExit):
        main(["내일", "--now", "not-a-date"])


def test_cli_policy_option(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["9시", "--now", "2026-09-28T08:05", "--ambiguous-hour", "pm"]) == 0
    assert json.loads(capsys.readouterr().out)["value"] == "21:00:00"


def test_alternatives_inherit_missing_context() -> None:
    """'A 아니면 B': B에 빠진 정보는 A에서 이어받는다 (결과는 둘 다 반환)"""
    cases = {
        "다음주 월요일 아니면 화요일": ["2026-10-05", "2026-10-06"],
        "다음주 화요일 아니면 월요일": ["2026-10-06", "2026-10-05"],  # '월요일 이후'가 아니라 같은 주
        "다음달 3일 또는 5일": ["2026-10-03", "2026-10-05"],
        "월요일이나 화요일": ["2026-10-05", "2026-09-29"],  # 이어받을 것이 없으면 각자
    }
    for text, expected in cases.items():
        assert [r.start.date().isoformat() for r in parse_all(text, now=NOW)] == expected, text
    tomorrow = parse_all("내일 오후 3시 아니면 5시", now=NOW)
    assert [r.start for r in tomorrow] == [at(2026, 9, 29, 15), at(2026, 9, 29, 17)]
    assert tomorrow[1].ambiguities == ()  # '오후'를 이어받아 오전/오후가 정해짐


def test_timezone_names_are_ignored() -> None:
    """'뉴욕 시간'은 해석하지 않는다. 시간대 변환은 호출하는 쪽의 몫"""
    result = parse("뉴욕 시간 내일 오전 3시", now=NOW)
    assert result is not None and result.text == "내일 오전 3시" and result.start == at(2026, 9, 29, 3)
