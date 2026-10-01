"""상대 표현 문법: 고정 표현 + 반복 접두 규칙 → 정규식과 값

lexicon의 선언(RepeatRule, 고정 표)만으로 '다다다음주', '저저저번달', '그그제', '재재작년' 같은
반복형을 표 추가 없이 인식합니다. 반복 횟수는 lexicon.MAX_REPEAT까지만 허용합니다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from . import lexicon as lx


def _words(keys: Iterable[str]) -> str:
    ordered = sorted(set(keys), key=len, reverse=True)
    return "|".join(r"\s*".join(re.escape(part) for part in key.split(" ")) for key in ordered)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def repeat_pattern(rules: Sequence[lx.RepeatRule]) -> str:
    return "|".join(
        f"(?:{re.escape(rule.repeat)}){{0,{lx.MAX_REPEAT}}}{re.escape(rule.stem)}"
        for rule in sorted(rules, key=lambda r: len(r.stem), reverse=True)
    )


def repeat_value(rules: Sequence[lx.RepeatRule], text: str) -> int | None:
    compact = _compact(text)
    for rule in rules:
        if not compact.endswith(rule.stem):
            continue
        head = compact[: len(compact) - len(rule.stem)]
        count, remainder = divmod(len(head), len(rule.repeat))
        if remainder == 0 and head == rule.repeat * count and count <= lx.MAX_REPEAT:
            return rule.sign * (rule.base + count)
    return None


def fixed_or_repeat(fixed: Mapping[str, int], rules: Sequence[lx.RepeatRule], text: str) -> int | None:
    compact = _compact(text)
    for key, value in fixed.items():
        if key.replace(" ", "") == compact:
            return value
    return repeat_value(rules, text)


# ---------------------------------------------------------------- 일

_PAST_SYLLABLES = "|".join(lx.DAY_PAST_SYLLABLES)
_PAST_STEMS = "|".join(sorted(lx.DAY_PAST_STEMS, key=len, reverse=True))
_PAST_DAY = re.compile(f"((?:{_PAST_SYLLABLES}){{1,{lx.MAX_REPEAT + 1}}})(?:{_PAST_STEMS})")

DAY_PATTERN = f"(?:{_words(lx.DAY_REL)}|{repeat_pattern(lx.DAY_REPEAT)}|{_PAST_DAY.pattern})"


def day_value(text: str) -> int | None:
    """오늘 0, 내일 1 … 그제 -2, 그끄제 -3 / 글피 3, 그글피 4"""
    past = _PAST_DAY.fullmatch(_compact(text))
    if past:
        return -(1 + len(past[1]))
    return fixed_or_repeat(lx.DAY_REL, lx.DAY_REPEAT, text)


# ---------------------------------------------------------------- 주 / 달 / 해 앞 수식어


def prefix_pattern(fixed: Mapping[str, int]) -> str:
    return f"(?:{_words({**lx.REL_PREFIX_FIXED, **fixed})}|{repeat_pattern(lx.REL_PREFIX_REPEAT)})"


def prefix_value(fixed: Mapping[str, int], text: str, excluded: Sequence[str] = ()) -> int | None:
    """'다다음' → 2, '저저번' → -2. excluded에 있는 단독형('전주'의 '전')은 None."""
    if _compact(text) in excluded:
        return None
    return fixed_or_repeat({**lx.REL_PREFIX_FIXED, **fixed}, lx.REL_PREFIX_REPEAT, text)


# ---------------------------------------------------------------- 연

YEAR_PATTERN = f"(?:{_words(lx.YEAR_REL)}|{repeat_pattern(lx.YEAR_REPEAT)}|{prefix_pattern({})}\\s*해)"


def year_value(text: str) -> int | None:
    compact = _compact(text)
    if compact.endswith("해") and compact not in {k.replace(" ", "") for k in lx.YEAR_REL}:
        return prefix_value({}, compact[:-1], lx.YEAR_PREFIX_EXCLUDED)
    return fixed_or_repeat(lx.YEAR_REL, lx.YEAR_REPEAT, text)
