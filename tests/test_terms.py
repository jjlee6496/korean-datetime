"""사용자 시각 어휘: ParseOptions(terms={...})로 '장 마감' 같은 도메인 시각·시간대를 넣음"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from korean_datetime import Cycle, Kind, ParseOptions, TemporalParser, WeekdayCalendar

TERMS = {
    "장 마감": time(15, 30),
    "장 시작": time(9, 0),
    "정규장": (time(9, 0), time(15, 30)),
    "동시호가": (time(15, 20), time(15, 30)),
}
MARKET = TemporalParser(ParseOptions(terms=TERMS))
DURING = datetime(2026, 10, 7, 10, 0)  # 수요일 장중
AFTER = datetime(2026, 10, 7, 16, 0)  # 장 마감 뒤


def test_single_time_term() -> None:
    result = MARKET.parse("장 마감 가격 알려줘", now=DURING)
    assert result is not None and (result.text, result.start) == ("장 마감", datetime(2026, 10, 7, 15, 30))
    assert result.ambiguities == ()  # 정해진 시각이라 오전/오후 모호성 없음


def test_term_after_it_passed_follows_cycle() -> None:
    """장 마감 뒤: 기본(미래 우선)은 내일 마감, 과거 조회(cycle=PAST)는 오늘 마감"""
    assert MARKET.parse("장 마감", now=AFTER).start == datetime(2026, 10, 8, 15, 30)  # type: ignore[union-attr]
    past = TemporalParser(ParseOptions(terms=TERMS, cycle=Cycle.PAST))
    assert past.parse("장 마감", now=AFTER).start == datetime(2026, 10, 7, 15, 30)  # type: ignore[union-attr]


def test_range_term() -> None:
    result = MARKET.parse("정규장 동안 거래량", now=DURING)
    assert result is not None
    assert (result.start, result.end, result.kind) == (
        datetime(2026, 10, 7, 9),
        datetime(2026, 10, 7, 15, 30),
        Kind.TIME,
    )
    auction = MARKET.parse("동시호가", now=DURING)
    assert auction is not None and (auction.start, auction.end) == (
        datetime(2026, 10, 7, 15, 20),
        datetime(2026, 10, 7, 15, 30),
    )


def test_term_combines_with_dates() -> None:
    assert MARKET.parse("어제 장 마감", now=DURING).start == datetime(2026, 10, 6, 15, 30)  # type: ignore[union-attr]
    calendar = TemporalParser(
        ParseOptions(terms=TERMS, business_calendar=WeekdayCalendar([date(2026, 10, 9)]))
    )
    monday = datetime(2026, 10, 12, 10)
    assert calendar.parse("전 거래일 장 마감", now=monday).start == datetime(2026, 10, 8, 15, 30)  # type: ignore[union-attr]


def test_terms_are_off_by_default_and_respect_word_boundaries() -> None:
    assert TemporalParser().parse_all("장 마감 가격", now=DURING) == []
    assert MARKET.parse_all("정규장비 점검", now=DURING) == []


@pytest.mark.parametrize(
    "bad",
    [{"": time(9)}, {"장 마감": "15:30"}, {"정규장": (time(15, 30), time(9))}, {"정규장": (time(9),)}],
)
def test_invalid_terms_rejected(bad: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        ParseOptions(terms=bad)  # type: ignore[arg-type]


def test_terms_keep_options_hashable() -> None:
    assert hash(ParseOptions(terms=TERMS)) == hash(ParseOptions(terms=dict(reversed(list(TERMS.items())))))
