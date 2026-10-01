"""한글 수사 파서 (한자어 수사 '이십삼', 고유어 수사 '스물세')

정규식 조각(SINO, NATIVE)은 다른 규칙에 끼워 넣어 쓰고, 매칭된 문자열은 parse_* 함수로 정수로 바꿉니다.
목록을 나열하지 않고 구조로 파싱하므로 '열한시 십오분', '삼십일일' 같은 조합도 정확히 처리합니다.
"""

from __future__ import annotations

import re

_SINO_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SINO_BODY = "(?:[이삼사오육칠팔구]?백)?(?:[이삼사오육칠팔구]?십)?[일이삼사오육칠팔구]?"
# 1~999. lookahead로 빈 문자열 매칭을 막는다.
SINO = f"(?=[일이삼사오육칠팔구십백]){_SINO_BODY}"

_NATIVE_UNITS = {
    "하나": 1,
    "한": 1,
    "둘": 2,
    "두": 2,
    "셋": 3,
    "세": 3,
    "석": 3,
    "넷": 4,
    "네": 4,
    "넉": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
}
_NATIVE_TENS = {
    "열": 10,
    "스물": 20,
    "서른": 30,
    "마흔": 40,
    "쉰": 50,
    "예순": 60,
    "일흔": 70,
    "여든": 80,
    "아흔": 90,
}
_TENS_ALT = "|".join(sorted(_NATIVE_TENS, key=len, reverse=True))
_UNITS_ALT = "|".join(sorted(_NATIVE_UNITS, key=len, reverse=True))
# 1~99. '스무'는 단위명사 앞에서만 쓰는 20.
NATIVE = f"(?:(?:{_TENS_ALT})(?:\\s?(?:{_UNITS_ALT}))?|스무|(?:{_UNITS_ALT}))"

_SINO_FULL = re.compile(SINO)
_NATIVE_FULL = re.compile(
    f"(?:(?P<tens>{_TENS_ALT})\\s?(?P<unit>{_UNITS_ALT})?|(?P<twenty>스무)|(?P<only>{_UNITS_ALT}))"
)


def parse_sino(text: str) -> int | None:
    """한자어 수사를 정수로 바꿉니다. 형식이 틀리면 None ('십십', '일일')."""
    if not text or _SINO_FULL.fullmatch(text) is None:
        return None
    total, current = 0, 0
    for char in text:
        if char == "백":
            total, current = total + (current or 1) * 100, 0
        elif char == "십":
            total, current = total + (current or 1) * 10, 0
        else:
            current = _SINO_DIGITS[char]
    return total + current


def parse_native(text: str) -> int | None:
    """고유어 수사를 정수로 바꿉니다. 형식이 틀리면 None ('하나둘')."""
    match = _NATIVE_FULL.fullmatch(text.strip()) if text else None
    if match is None:
        return None
    if match["twenty"]:
        return 20
    if match["only"]:
        return _NATIVE_UNITS[match["only"]]
    return _NATIVE_TENS[match["tens"]] + (_NATIVE_UNITS[match["unit"]] if match["unit"] else 0)


def parse_korean_number(text: str) -> int | None:
    """아라비아 숫자, 한자어 수사, 고유어 수사 중 무엇이든 정수로 바꿉니다."""
    stripped = text.strip()
    if stripped.isdecimal():
        return int(stripped)
    sino = parse_sino(stripped)
    return sino if sino is not None else parse_native(stripped)


def syllable_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace())
