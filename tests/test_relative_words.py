"""반복 접두 규칙(다다다음, 저저저번, 그그제)과 한자어 상대 표현 (기준: 2026-09-28 월요일)"""

from __future__ import annotations

import pytest
from helpers import d, date_span, days, must, p


@pytest.mark.parametrize(
    ("text", "offset"),
    [
        ("금일", 0),
        ("당일", 0),
        ("명일", 1),
        ("익일", 1),
        ("명후일", 2),
        ("익익일", 2),
        ("작일", -1),
        ("전일", -1),
        ("그제", -2),
        ("그저께", -2),
        ("그그제", -3),
        ("그끄제", -3),
        ("그끄저께", -3),
        ("그그그제", -4),
        ("글피", 3),
        ("그글피", 4),
        ("그그글피", 5),
    ],
)
def test_relative_days(text: str, offset: int) -> None:
    assert must(text).start.date() == days(offset)


@pytest.mark.parametrize(
    ("text", "weeks"),
    [
        ("금주", 0),
        ("내주", 1),
        ("익주", 1),
        ("차주", 1),
        ("다음주", 1),
        ("다다음주", 2),
        ("다다다음주", 3),
        ("담주", 1),
        ("다담주", 2),
        ("다다담주", 3),
        ("저번주", -1),
        ("저저번주", -2),
        ("저저저번주", -3),
        ("지난주", -1),
        ("지지난주", -2),
        ("지지지난주", -3),
        ("전전주", -2),
        ("전전전주", -3),
    ],
)
def test_relative_weeks(text: str, weeks: int) -> None:
    start, end = date_span(text)
    assert (start, end) == (days(7 * weeks), days(7 * weeks + 7))


@pytest.mark.parametrize(
    ("text", "month"),
    [
        ("이달", 9),
        ("금월", 9),
        ("당월", 9),
        ("다음달", 10),
        ("내달", 10),
        ("익월", 10),
        ("다다다음달", 12),
        ("저번달", 8),
        ("전월", 8),
        ("전전달", 7),
        ("전전월", 7),
        ("지지지난달", 6),
    ],
)
def test_relative_months(text: str, month: int) -> None:
    assert date_span(text)[0] == d(2026, month, 1)


def test_jeondal_is_not_last_month() -> None:
    """'전달'은 실제 문장(AI허브 시간 표현 데이터)에서 거의 전부 전달(傳達)하다라 지난달로 보지 않음"""
    assert p("메시지를 전달했다") is None
    assert p("전달") is None


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("올해", 2026),
        ("금년", 2026),
        ("내년", 2027),
        ("명년", 2027),
        ("익년", 2027),
        ("다음 해", 2027),
        ("내후년", 2028),
        ("후년", 2028),
        ("후후년", 2029),
        ("작년", 2025),
        ("전년", 2025),
        ("지난해", 2025),
        ("재작년", 2024),
        ("재재작년", 2023),
        ("지지난해", 2024),
    ],
)
def test_relative_years(text: str, year: int) -> None:
    assert date_span(text) == (d(year, 1, 1), d(year + 1, 1, 1))


@pytest.mark.parametrize(
    "text",
    [
        "전주에 다녀왔다",  # 지명 전주
        "내내후년",  # 쓰지 않는 말
        "다다다다다다음주",  # 반복 한도(4회) 초과
        "그그그그그그제",
        "전일제 근무",
        "당일치기",
    ],
)
def test_not_relative(text: str) -> None:
    assert p(text) is None, text


def test_repetition_combines_with_other_slots() -> None:
    assert must("다다다음주 금요일").start.date() == days(21 + 4)
    assert must("저저번달 말일").start.date() == d(2026, 7, 31)
    assert must("재작년 크리스마스").start.date() == d(2024, 12, 25)
