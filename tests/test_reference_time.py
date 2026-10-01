"""기준 시각 결정: now 인자 > 요청 단위 reference_time() > ParseOptions.timezone의 서버 시각 > 서버 시각"""

from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from ko_normalizer import (
    ParseOptions,
    TemporalParser,
    current_reference,
    parse,
    parse_date,
    parse_time,
    reference_time,
)

KST = timezone(timedelta(hours=9), "KST")
REQUEST = datetime(2026, 9, 28, 14, 30, tzinfo=KST)


def test_reference_time_is_used_when_now_is_omitted() -> None:
    with reference_time(REQUEST):
        assert parse_time("3시") == datetime(2026, 9, 28, 15, tzinfo=KST).timetz()  # 시간대도 유지
        assert parse_date("내일") == date(2026, 9, 29)
        assert current_reference() == REQUEST
    assert current_reference() != REQUEST  # 블록을 나오면 원래대로


def test_every_call_in_a_request_shares_one_reference() -> None:
    with reference_time(REQUEST):
        first = parse("지금")
        second = parse("지금")
    assert first is not None and second is not None
    assert first.start == second.start == REQUEST


def test_explicit_now_wins_over_reference_time() -> None:
    with reference_time(REQUEST):
        result = parse("내일", now=datetime(2030, 1, 1))
    assert result is not None and result.start.date() == date(2030, 1, 2)


def test_nested_reference_times_restore_outer() -> None:
    with reference_time(REQUEST):
        with reference_time(datetime(2027, 1, 1, tzinfo=KST)):
            assert parse_date("오늘") == date(2027, 1, 1)
        assert parse_date("오늘") == date(2026, 9, 28)


def test_reference_time_accepts_date() -> None:
    with reference_time(date(2026, 9, 28)) as moment:
        assert moment == datetime(2026, 9, 28)
        assert parse_date("모레") == date(2026, 9, 30)


def test_reference_time_rejects_bad_type() -> None:
    with pytest.raises(TypeError), reference_time("2026-09-28"):  # type: ignore[arg-type]
        pass


def test_reference_time_is_isolated_between_threads() -> None:
    seen: list[datetime] = []
    with reference_time(REQUEST):
        worker = threading.Thread(target=lambda: seen.append(current_reference()))
        worker.start()
        worker.join()
    assert seen[0] != REQUEST  # 다른 스레드(다른 요청)에는 퍼지지 않음


def test_reference_time_is_isolated_between_async_requests() -> None:
    async def handle(moment: datetime) -> date | None:
        with reference_time(moment):
            await asyncio.sleep(0)  # 다른 요청으로 전환되어도
            return parse_date("오늘")

    async def main() -> list[date | None]:
        return list(
            await asyncio.gather(
                handle(datetime(2026, 1, 1, tzinfo=KST)), handle(datetime(2027, 6, 6, tzinfo=KST))
            )
        )

    assert asyncio.run(main()) == [date(2026, 1, 1), date(2027, 6, 6)]


def test_timezone_option_reads_server_clock_in_that_zone() -> None:
    parser = TemporalParser(ParseOptions(timezone=KST))
    result = parser.parse("오늘")
    assert result is not None
    assert result.start.tzinfo == KST
    assert result.start.date() == datetime.now(KST).date()


def test_reference_time_wins_over_timezone_option() -> None:
    with reference_time(REQUEST):
        result = TemporalParser(ParseOptions(timezone=timezone.utc)).parse("오늘")
    assert result is not None and result.start == datetime(2026, 9, 28, tzinfo=KST)


def test_timezone_option_is_validated() -> None:
    with pytest.raises(TypeError):
        ParseOptions(timezone="Asia/Seoul")  # type: ignore[arg-type]
