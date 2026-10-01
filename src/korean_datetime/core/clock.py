"""기준 시각 — 상대 표현('내일', '3시', '1시간 후')을 계산하는 기준

우선순위:
    1. 함수에 넘긴 now
    2. reference_time()으로 정한 요청 단위 기준 시각
    3. 서버 시각 (시간대를 지정했으면 그 시간대로)

웹 서버에서는 요청마다 한 번 정해 두면, 그 요청 안의 모든 호출이 now 없이 같은 기준을 씁니다.

    @app.middleware("http")
    async def set_request_time(request, call_next):
        with reference_time(datetime.now(KST)):
            return await call_next(request)

ContextVar 기반이라 스레드·비동기 요청끼리 섞이지 않습니다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, tzinfo

_REFERENCE: ContextVar[datetime | None] = ContextVar("korean_datetime_reference_time", default=None)


def _as_datetime(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    raise TypeError(f"기준 시각은 datetime 또는 date여야 합니다: {type(value).__name__}")


@contextmanager
def reference_time(value: datetime | date) -> Iterator[datetime]:
    """블록 안에서 now를 생략한 호출이 쓸 기준 시각을 정합니다. 블록을 나오면 이전 값으로 돌아갑니다."""
    moment = _as_datetime(value)
    token = _REFERENCE.set(moment)
    try:
        yield moment
    finally:
        _REFERENCE.reset(token)


def current_reference(tz: tzinfo | None = None) -> datetime:
    """reference_time()으로 정한 기준 시각. 없으면 서버 시각 (tz가 있으면 그 시간대)."""
    fixed = _REFERENCE.get()
    return fixed if fixed is not None else datetime.now(tz)
