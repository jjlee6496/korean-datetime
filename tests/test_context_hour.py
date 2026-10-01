"""AmbiguousHour.CONTEXT: 오전/오후 없는 시각을 같은 텍스트 안의 단서로 정함

1. 앞에 오전/오후가 정해진 시각이 있으면 그 뒤로 이어지는 쪽 ('오후 5시 반에 만나서 7시에' → 19시)
2. 없으면 가장 가까운 시간대 말 ('저녁 먹으러 8시쯤' → 20시). 시간대 어휘는 lexicon.PERIODS 그대로
3. 둘 다 없으면 DAYTIME (7~11시 오전, 1~6시 오후)
값을 정해도 문장에 오전/오후가 없었다는 표시(meridiem)는 그대로 남음
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ko_normalizer import Ambiguity, AmbiguousHour, ParseOptions, TemporalParser

NOW = datetime(2026, 10, 1, 9, 0)
CONTEXT = TemporalParser(ParseOptions(ambiguous_hour=AmbiguousHour.CONTEXT))
DAYTIME = TemporalParser(ParseOptions(ambiguous_hour=AmbiguousHour.DAYTIME))


def _hours(parser: TemporalParser, text: str) -> list[int]:
    """'N시' 표현의 시 ('저녁', '아침'처럼 혼자 쓴 시간대 말도 결과에 나오지만 여기서는 시각만 비교)"""
    return [r.start.hour for r in parser.parse_all(text, now=NOW) if "시" in r.text]


@pytest.mark.parametrize(
    ("text", "context", "daytime"),
    [
        # 1. 앞 시각에서 이어짐
        ("오후 5시 반에 만나서 저녁 먹고 7시에 들어가자", [17, 19], [17, 7]),
        ("오후 6시에 끝나고 8시 영화 보자", [18, 20], [18, 8]),
        ("오전 6시에 일어나서 7시에 나가", [6, 7], [6, 7]),
        ("15시 회의 끝나고 9시에 다시 모여", [15, 21], [15, 9]),
        # 2. 시간대 말
        ("어제 저녁 먹으러 8시쯤 한정식집에 갔어요", [20], [8]),
        ("아침에 2시간 운동하고 출근", [], []),
        ("새벽까지 놀다가 5시에 잤어", [5], [17]),
        # 3. 단서가 없으면 DAYTIME
        ("3시에 보자", [15], [15]),
        ("8시에 보자", [8], [8]),
    ],
)
def test_context_hour(text: str, context: list[int], daytime: list[int]) -> None:
    assert _hours(CONTEXT, text) == context
    assert _hours(DAYTIME, text) == daytime


def test_meridiem_flag_stays() -> None:
    result = CONTEXT.parse_all("저녁 먹으러 8시쯤 갔어요", now=NOW)[-1]
    assert (result.text, result.start.hour) == ("8시", 20)
    assert Ambiguity.MERIDIEM in result.ambiguities


def test_explicit_meridiem_is_never_changed() -> None:
    assert _hours(CONTEXT, "저녁 먹고 오전 9시에 출발") == [9]
    assert _hours(CONTEXT, "아침 먹고 오후 3시") == [15]


def test_time_only_rolls_again_after_meridiem_changes() -> None:
    """'7시'@9시: DAYTIME의 07시는 지나서 내일이지만, 문맥으로 19시가 되면 오늘"""
    result = CONTEXT.parse_all("오후 5시 반에 만나서 7시에 들어가자", now=NOW)[-1]
    assert result.start == datetime(2026, 10, 1, 19, 0)
    assert Ambiguity.CYCLE_SHIFTED not in result.ambiguities
    late = CONTEXT.parse_all("오후 5시 반에 만나서 7시에 들어가자", now=datetime(2026, 10, 1, 20, 0))[-1]
    assert late.start == datetime(2026, 10, 2, 19, 0)  # 19시도 지났으면 내일
    assert Ambiguity.CYCLE_SHIFTED in late.ambiguities


def test_context_uses_only_the_same_text() -> None:
    """앞 호출의 결과는 쓰지 않음: 같은 입력이면 항상 같은 결과"""
    CONTEXT.parse_all("오후 6시에 끝나고", now=NOW)
    assert _hours(CONTEXT, "8시 영화 보자") == [8]
