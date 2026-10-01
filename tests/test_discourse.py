"""한 문장 안의 여러 표현 사이 관계: 정정, 앞 날짜 기준 전날/다음 날, 문맥 의존 표현, 다가오는/매월

정답셋(temporal_gold.jsonl)은 첫 결과만 비교하므로, 두 번째 결과나 빠져야 하는 결과는 여기서 검증합니다.
"""

from __future__ import annotations

from datetime import datetime

from korean_datetime import parse, parse_all

SUNDAY_NIGHT = datetime(2026, 10, 4, 23, 59)


def _values(text: str, now: datetime) -> list[tuple[str, datetime]]:
    return [(r.text, r.start) for r in parse_all(text, now=now)]


def test_day_shift_links_to_previous_expression_in_same_sentence() -> None:
    assert _values("다음 주 화요일과 그다음 날 오전 9시에 각각 만나자", SUNDAY_NIGHT) == [
        ("다음 주 화요일", datetime(2026, 10, 6)),
        ("그다음 날 오전 9시", datetime(2026, 10, 7, 9)),
    ]


def test_day_shift_without_anchor_in_sentence_is_not_recognized() -> None:
    """'전날'이 가리키는 날은 앞 문장·대화에 있으므로 기준 시각으로 계산하지 않음"""
    assert parse_all("전날 오후 6시에 알려줘", now=SUNDAY_NIGHT) == []
    assert parse_all("회의가 있어. 그 전날 같은 시간에 전화해줘", now=SUNDAY_NIGHT) == []


def test_day_shift_of_multi_day_span() -> None:
    monday = datetime(2026, 9, 28, 14, 30)  # 이번 주말 = 10월 3~4일
    assert _values("이번 주말 전날", monday) == [("이번 주말 전날", datetime(2026, 10, 2))]
    assert _values("이번 주말 다음 날", monday) == [("이번 주말 다음 날", datetime(2026, 10, 5))]


def test_correction_keeps_only_the_replacement() -> None:
    now = datetime(2026, 10, 5)
    assert _values("내일 오전 3시가 아니라 내일 오후 3시로 바꿔", now) == [
        ("내일 오후 3시", datetime(2026, 10, 6, 15)),
    ]
    assert _values("내일이 아니라 모레", now) == [("모레", datetime(2026, 10, 7))]
    # 빠진 정보는 정정 전 표현에서 이어받음
    assert _values("다음 주 월요일 아니라 화요일이야", now) == [("화요일", datetime(2026, 10, 13))]


def test_anaphoric_expressions_are_not_recognized() -> None:
    for text in ("그다음 주 토요일에 마쳐", "그날 오전 9시", "거기서 세 시간 지나면", "그해 겨울"):
        assert parse_all(text, now=SUNDAY_NIGHT) == [], text


def test_calendar_dependent_units_are_not_recognized() -> None:
    assert parse_all("이번 달 마지막 영업일 오후 3시에 보내줘", now=SUNDAY_NIGHT) == []
    assert parse_all("3영업일 이내", now=SUNDAY_NIGHT) == []


def test_upcoming_marker_checks_the_time_not_only_the_date() -> None:
    """'다가오는/오는/매월'은 오늘 날짜라도 시각이 지났으면 다음 주기, 수식어가 없으면 날짜 단위로만 판단"""
    after_nine = datetime(2027, 1, 31, 9, 1)
    assert parse("31일 오전 9시", now=after_nine).start == datetime(2027, 1, 31, 9)  # type: ignore[union-attr]
    assert parse("다가오는 31일 오전 9시", now=after_nine).start == datetime(2027, 3, 31, 9)  # type: ignore[union-attr]
    assert parse("매월 31일 오전 9시", now=after_nine).start == datetime(2027, 3, 31, 9)  # type: ignore[union-attr]
    before_nine = datetime(2027, 1, 31, 8, 59)
    assert parse("다가오는 31일 오전 9시", now=before_nine).start == datetime(2027, 1, 31, 9)  # type: ignore[union-attr]


def test_range_end_offset_counts_from_range_start() -> None:
    at_1656 = datetime(2026, 9, 28, 16, 56)
    result = parse("오후 5시 5분 전부터 두 시간 후까지", now=at_1656)
    assert result is not None and result.is_range
    assert (result.start, result.end) == (datetime(2026, 9, 29, 16, 55), datetime(2026, 9, 29, 18, 55))
    # '까지'가 없으면 범위가 아니라 기준점 ('내일부터 3일 뒤' = 내일 + 3일)
    point = parse("내일부터 3일 뒤", now=at_1656)
    assert point is not None and not point.is_range and point.start == datetime(2026, 10, 2)


def test_year_level_nth_weekday() -> None:
    now = datetime(2026, 12, 31, 23, 59)
    assert _values("올해 마지막 금요일부터 내년 첫 월요일까지", now) == [
        ("올해 마지막 금요일부터 내년 첫 월요일까지", datetime(2026, 12, 25)),
    ]
    assert parse_all("올해 다섯째 금요일", now=now) == []  # 1월인지 2월인지 정할 수 없음
