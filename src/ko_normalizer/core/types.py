"""입력 검증 공용 함수"""

from __future__ import annotations

from datetime import date, datetime, tzinfo

from .clock import current_reference


def to_datetime(now: datetime | date | None, tz: tzinfo | None = None) -> datetime:
    """None이면 기준 시각(reference_time() 또는 서버 시각, tz가 있으면 그 시간대), date는 그날 00:00."""
    if now is None:
        return current_reference(tz)
    if isinstance(now, datetime):
        return now
    if isinstance(now, date):
        return datetime(now.year, now.month, now.day)
    raise TypeError(f"now는 datetime, date 또는 None이어야 합니다: {type(now).__name__}")


def require_text(text: object) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text는 str이어야 합니다: {type(text).__name__}")
    return text
