"""정답셋을 돌릴 기준 시각 모음과 평가 결과 캐시"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from ko_normalizer.core.evaluation import EvaluationReport
from ko_normalizer.temporal.evaluation import (
    AmbiguityReport,
    ambiguity_from_report,
    evaluate_temporal,
    load_expression_gold,
)

DATA = Path(__file__).parent / "data"
GOLD = DATA / "temporal_gold.jsonl"  # 기대값 식 (기준 시각 무관)
ANCHOR = DATA / "temporal_anchor.jsonl"  # 2026-09-28 14:30 기준 손계산 절대값

START = datetime(2026, 1, 1, 14, 30)
DAYS = 730  # 2026~2027
# 하루 중 시각. 16:57은 "17시 5분 전"처럼 오프셋 경계를 넘나드는 시각
OTHER_TIMES = ((0, 10), (6, 0), (8, 5), (11, 59), (12, 0), (16, 57), (18, 30), (23, 50))
KST = timezone(timedelta(hours=9), "KST")


def real_now() -> datetime:
    """테스트를 실행하는 실제 현재 시각 (분 단위). 고정 목록과 분리해 재현성을 지킨다."""
    return datetime.now().replace(second=0, microsecond=0)


def _with_timezone() -> list[datetime]:
    """시간대가 있는 기준 시각 (KST): 결과에 시간대가 그대로 붙는지 비교"""
    return [datetime(2026, month, 15, 23, 50, tzinfo=KST) for month in range(1, 13)]


def _boundaries() -> list[datetime]:
    """월초·월말·연말·윤일"""
    days = []
    for year in (2026, 2027):
        for month in range(1, 13):
            last = calendar.monthrange(year, month)[1]
            days += [datetime(year, month, 1, 14, 30), datetime(year, month, last, 14, 30)]
    return [*days, datetime(2028, 2, 28, 14, 30), datetime(2028, 2, 29, 14, 30)]


def sampled_references() -> list[datetime]:
    """기본 실행용 고정 목록: 5일 간격 + 경계일 + 하루 중 여러 시각 + KST 시각 (항상 같은 목록)"""
    every_fifth = [START + timedelta(days=i) for i in range(0, DAYS, 5)]
    times = [datetime(2026, month, 1, h, m) for month in range(1, 13) for h, m in OTHER_TIMES]
    naive = sorted({*every_fifth, *_boundaries(), *times})
    return [*naive, *_with_timezone()]


def full_references() -> list[datetime]:
    """전체 스윕: 2년 매일 14:30 + 주 1회 하루 중 여러 시각 + 경계일 + KST 시각"""
    daily = [START + timedelta(days=i) for i in range(DAYS)]
    times = [
        datetime(2026, 1, 1, h, m) + timedelta(days=i) for i in range(0, DAYS, 7) for h, m in OTHER_TIMES
    ]
    return [*sorted({*daily, *times, *_boundaries()}), *_with_timezone()]


@lru_cache(maxsize=1)
def sampled_report() -> EvaluationReport:
    return evaluate_temporal(load_expression_gold(GOLD, sampled_references()))


@lru_cache(maxsize=1)
def sampled_ambiguity_report() -> AmbiguityReport:
    return ambiguity_from_report(sampled_report())
