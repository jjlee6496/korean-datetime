"""막연한 때('최근', '향후'): ParseOptions(vague=True)일 때만 Kind.VAGUE로 인식"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from korean_datetime import Direction, Kind, ParseOptions, TemporalParser, parse_all
from korean_datetime.temporal import lexicon as lx

NOW = datetime(2026, 10, 1, 10, 0)
VAGUE = TemporalParser(ParseOptions(vague=True))


@pytest.mark.parametrize(
    ("text", "word", "direction"),
    [
        ("최근 3년간 매출이 늘었다", "최근", Direction.RECENT),
        ("요즘 날씨가 좋다", "요즘", Direction.RECENT),
        ("예전에는 그랬지", "예전", Direction.PAST),
        ("향후 일정은 미정", "향후", Direction.FUTURE),
        ("나중에 보자", "나중", Direction.FUTURE),
    ],
)
def test_vague_words_when_enabled(text: str, word: str, direction: Direction) -> None:
    result = VAGUE.parse(text, now=NOW)
    assert result is not None
    assert (result.text, result.kind, result.direction) == (word, Kind.VAGUE, direction)
    assert result.value == date(2026, 10, 1)  # 값은 기준일, 뜻은 direction
    assert result.time is None
    assert result.to_dict()["direction"] == direction.value


def test_off_by_default() -> None:
    assert parse_all("최근 매출이 늘었고 향후 전망도 밝다", now=NOW) == []
    assert "direction" not in parse_all("내일", now=NOW)[0].to_dict()  # 기존 결과 형식은 그대로


def test_excluded_words_and_word_boundaries() -> None:
    for text in ("앞으로 나아가다", "요새를 쌓았다", "미래 기술", "최근접 이웃", "곧 출시"):
        assert VAGUE.parse_all(text, now=NOW) == [], text


def test_vague_does_not_merge_into_ranges_or_frames() -> None:
    results = VAGUE.parse_all("최근부터 내일까지", now=NOW)
    assert [(r.text, r.kind) for r in results] == [("최근", Kind.VAGUE), ("내일", Kind.DATE)]


def test_word_table_is_the_single_place_to_edit() -> None:
    """어휘를 넣고 빼는 곳은 lexicon.VAGUE_WORDS 하나: 표의 모든 방향 값이 Direction이어야 함"""
    assert {Direction(value) for value in lx.VAGUE_WORDS.values()} <= set(Direction)
    assert "앞으로" not in lx.VAGUE_WORDS and "곧" not in lx.VAGUE_WORDS
