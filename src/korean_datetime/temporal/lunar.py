"""한국 음력(태음태양력) → 양력 변환 — 외부 라이브러리·연도표 없이 천문 계산

1. 삭(new moon) 시각: Meeus, *Astronomical Algorithms* 49장 (오차 수 분 이내)
2. 중기(태양 황경 30°마다) 시각: Meeus 25장 저정밀 태양 위치 (오차 약 0.01° ≈ 15분)
3. 날짜는 한국 표준시(UTC+9) 기준. 동지가 든 달을 11월로 두고, 13달인 해에는 중기가 없는 첫 달을 윤달로 한다.

삭이나 중기가 자정 몇 분 전후에 걸리는 드문 경우 하루 어긋날 수 있습니다.
지원 범위는 1900~2100년이며, tests/test_holidays.py에서 한국천문연구원 역서 날짜로 검증합니다.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from functools import lru_cache

MIN_YEAR, MAX_YEAR = 1900, 2100
_SYNODIC_MONTH = 29.530588861
_TROPICAL_YEAR = 365.24219
_KST_HOURS = 9
_JD_ORDINAL_OFFSET = 1721424.5  # JD - 이 값 = date.toordinal() (00:00 UT 기준)


def _sin(degrees: float) -> float:
    return math.sin(math.radians(degrees))


def _delta_t_days(year: float) -> float:
    """역학시(TT) - 세계시(UT), Espenak & Meeus 다항식 (일 단위)"""
    if year < 1941:
        t = year - 1920
        seconds = 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
    elif year < 1961:
        t = year - 1950
        seconds = 29.07 + 0.407 * t - t**2 / 233 + t**3 / 2547
    elif year < 1986:
        t = year - 1975
        seconds = 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
    elif year < 2005:
        t = year - 2000
        seconds = (
            63.86
            + 0.3345 * t
            - 0.060374 * t**2
            + 0.0017275 * t**3
            + 0.000651814 * t**4
            + 0.00002373599 * t**5
        )
    elif year < 2050:
        t = year - 2000
        seconds = 62.92 + 0.32217 * t + 0.005589 * t**2
    else:
        seconds = -20 + 32 * ((year - 1820) / 100) ** 2 - 0.5628 * (2150 - year)
    return seconds / 86400


def _kst_date(jde: float) -> date:
    year = 2000 + (jde - 2451545.0) / 365.25
    local = jde - _delta_t_days(year) + _KST_HOURS / 24
    return date.fromordinal(math.floor(local - _JD_ORDINAL_OFFSET))


def _jd(day: date) -> float:
    return day.toordinal() + _JD_ORDINAL_OFFSET


_NEW_MOON_TERMS = (  # (계수, M'계수, M계수, F계수, E 차수)
    (-0.40720, 1, 0, 0, 0),
    (0.17241, 0, 1, 0, 1),
    (0.01608, 2, 0, 0, 0),
    (0.01039, 0, 0, 2, 0),
    (0.00739, 1, -1, 0, 1),
    (-0.00514, 1, 1, 0, 1),
    (0.00208, 0, 2, 0, 2),
    (-0.00111, 1, 0, -2, 0),
    (-0.00057, 1, 0, 2, 0),
    (0.00056, 2, 1, 0, 1),
    (-0.00042, 3, 0, 0, 0),
    (0.00042, 0, 1, 2, 1),
    (0.00038, 0, 1, -2, 1),
    (-0.00024, 2, -1, 0, 1),
    (-0.00007, 1, 2, 0, 0),
    (0.00004, 2, 0, -2, 0),
    (0.00004, 0, 3, 0, 0),
    (0.00003, 1, 1, -2, 0),
    (0.00003, 2, 0, 2, 0),
    (-0.00003, 1, 1, 2, 0),
    (0.00003, 1, -1, 2, 0),
    (-0.00002, 1, -1, -2, 0),
    (-0.00002, 3, 1, 0, 0),
    (0.00002, 4, 0, 0, 0),
)
_PLANETARY = (  # (계수, 기준각, k 계수)
    (0.000325, 299.77, 0.107408),
    (0.000165, 251.88, 0.016321),
    (0.000164, 251.83, 26.651886),
    (0.000126, 349.42, 36.412478),
    (0.000110, 84.66, 18.206239),
    (0.000062, 141.74, 53.303771),
    (0.000060, 207.14, 2.453732),
    (0.000056, 154.84, 7.306860),
    (0.000047, 34.52, 27.261239),
    (0.000042, 207.19, 0.121824),
    (0.000040, 291.34, 1.844379),
    (0.000037, 161.72, 24.198154),
    (0.000035, 239.56, 25.513099),
    (0.000023, 331.55, 3.592518),
)


def _new_moon_jde(k: int) -> float:
    """k번째 삭(2000년 1월 6일 삭이 k=0)의 역학시 율리우스일"""
    t = k / 1236.85
    jde = 2451550.09766 + _SYNODIC_MONTH * k + 0.00015437 * t**2 - 0.000000150 * t**3 + 0.00000000073 * t**4
    m = 2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3
    mp = 201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4
    f = 160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3 + 0.000000011 * t**4
    omega = 124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3
    e = 1 - 0.002516 * t - 0.0000074 * t**2
    correction = sum(c * e**ep * _sin(a * mp + b * m + g * f) for c, a, b, g, ep in _NEW_MOON_TERMS)
    correction -= 0.00017 * _sin(omega)
    a1 = 299.77 + 0.107408 * k - 0.009173 * t**2
    planetary = _PLANETARY[0][0] * _sin(a1) + sum(
        c * _sin(base + rate * k) for c, base, rate in _PLANETARY[1:]
    )
    return jde + correction + planetary


def _sun_longitude(jde: float) -> float:
    """태양의 겉보기 황경(도)"""
    t = (jde - 2451545.0) / 36525
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t**2
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t**2
    center = (
        (1.914602 - 0.004817 * t - 0.000014 * t**2) * _sin(m)
        + (0.019993 - 0.000101 * t) * _sin(2 * m)
        + 0.000289 * _sin(3 * m)
    )
    omega = 125.04 - 1934.136 * t
    return (l0 + center - 0.00569 - 0.00478 * _sin(omega)) % 360


def _solar_term_jde(target: float, guess: float) -> float:
    """태양 황경이 target(도)이 되는 시각 (guess 근처에서 뉴턴법)"""
    jde = guess
    for _ in range(50):
        diff = (target - _sun_longitude(jde) + 180) % 360 - 180
        jde += diff * _TROPICAL_YEAR / 360
        if abs(diff) < 1e-7:
            break
    return jde


def _new_moon_on_or_before(day: date) -> int:
    k = math.floor((_jd(day) - 2451550.09766) / _SYNODIC_MONTH) + 1
    while _kst_date(_new_moon_jde(k)) > day:
        k -= 1
    while _kst_date(_new_moon_jde(k + 1)) <= day:
        k += 1
    return k


@lru_cache(maxsize=256)
def _sui_months(year: int) -> tuple[tuple[int, bool, date, date], ...]:
    """(year-1)년 동지가 든 달 ~ year년 동지가 든 달 직전까지의 (월, 윤달 여부, 시작일, 다음 달 시작일)"""
    ws_prev_jde = _solar_term_jde(270, _jd(date(year - 1, 12, 21)))
    ws_prev = _kst_date(ws_prev_jde)
    ws = _kst_date(_solar_term_jde(270, _jd(date(year, 12, 21))))
    k_first, k_last = _new_moon_on_or_before(ws_prev), _new_moon_on_or_before(ws)
    starts = [_kst_date(_new_moon_jde(k)) for k in range(k_first, k_last + 1)]
    count = k_last - k_first
    leap_index = -1
    if count == 13:
        terms = [_kst_date(_solar_term_jde((270 + 30 * i) % 360, ws_prev_jde + i * 30.44)) for i in range(14)]
        leap_index = next(
            i for i in range(1, count) if not any(starts[i] <= term < starts[i + 1] for term in terms)
        )
    months: list[tuple[int, bool, date, date]] = []
    number = 11
    for i in range(count):
        leap = i == leap_index
        if i > 0 and not leap:
            number = number % 12 + 1
        months.append((number, leap, starts[i], starts[i + 1]))
    return tuple(months)


def _lunar_year_months(year: int) -> list[tuple[int, bool, date, date]]:
    """음력 year년 1월 ~ 12월 (윤달 포함)"""
    current = list(_sui_months(year))
    following = list(_sui_months(year + 1))
    first = next(i for i, (number, leap, _, _) in enumerate(current) if number == 1 and not leap)
    new_year_next = next(i for i, (number, leap, _, _) in enumerate(following) if number == 1 and not leap)
    return current[first:] + following[:new_year_next]


def lunar_to_solar(year: int, month: int, day: int, leap: bool = False) -> date:
    """
    음력 날짜를 양력으로 바꿉니다.

        >>> lunar_to_solar(2026, 8, 15)  # 2026년 추석
        datetime.date(2026, 9, 25)

    Raises:
        ValueError: 범위를 벗어나거나 존재하지 않는 음력 날짜
    """
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"지원 연도는 {MIN_YEAR}~{MAX_YEAR}년입니다: {year}")
    if not 1 <= month <= 12 or not 1 <= day <= 30:
        raise ValueError(f"올바른 음력 날짜가 아닙니다: {year}-{month}-{day}")
    for number, is_leap, start, end in _lunar_year_months(year):
        if number == month and is_leap == leap:
            if day > (end - start).days:
                raise ValueError(f"음력 {year}년 {month}월은 {(end - start).days}일까지입니다")
            return start + timedelta(days=day - 1)
    raise ValueError(f"음력 {year}년에는 {'윤' if leap else ''}{month}월이 없습니다")
