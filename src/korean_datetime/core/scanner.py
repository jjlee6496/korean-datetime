"""정규식 규칙 기반 토큰 스캐너 (한국어 단어 경계·조사 인식)

날짜·시간 규칙이 쓰는 저수준 엔진입니다. 규칙(TokenRule) 목록을 받아 텍스트를
왼쪽부터 훑으며, 각 위치에서 **가장 긴 매칭**(동률이면 먼저 등록된 규칙)을 토큰으로 채택합니다.

경계 규칙:
- 왼쪽: 한글로 시작하는 매칭은 앞 글자가 한글이면 거부합니다(단, 직전 토큰이 끝난 자리는 허용).
  "그내일"의 "내일"은 거부, "오늘저녁"의 "저녁"은 허용됩니다.
- 오른쪽(right_boundary=True인 규칙만): 뒤에 한글이 이어지면 조사이거나 다른 토큰의 시작이어야 합니다.
  "오일에"는 허용, "오일교환"은 거부됩니다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

PARTICLES: tuple[str, ...] = (
    "에서",
    "에게",
    "에는",
    "에도",
    "에",
    "엔",
    "의",
    "쯤",
    "경",
    "께",
    "즈음",
    "부터",
    "까지",
    "이나",
    "나",
    "은",
    "는",
    "이",
    "가",
    "도",
    "로",
    "으로",
    "만",
    "요",
    "이요",
    "야",
    "이야",
    "랑",
    "이랑",
    "하고",
    # 비교·한정·서술 ('어제만큼', '내일부턴', '오늘부터다')
    "만큼",
    "부턴",
    "까진",
    "보단",
    "처럼",
    "이다",
    "다",
    # 비교 기준으로 붙는 말 ('전년대비', '전년동기', '전월비')
    "대비",
    "동기",
    "동월",
    "동기간",
    "비",
    "과",
    "와",
    "인",
    "이서",
    "을",
    "를",
    "처럼",
    "보다",
    "마다",
    "씩",
    "이면",
    "면",
    "이라",
    "라",
    "이에요",
    "예요",
    "입니다",
)
_PARTICLE_RUN = re.compile("(?:" + "|".join(sorted(PARTICLES, key=len, reverse=True)) + ")*(?![가-힣])")


def is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def ends_word(text: str, end: int) -> bool:
    """end 위치가 단어의 끝인지: 문장 끝, 한글이 아님, 또는 조사만 이어짐 ('서울에서' ○, '서울시' ×)"""
    return end >= len(text) or not is_hangul(text[end]) or _PARTICLE_RUN.match(text, end) is not None


@dataclass(frozen=True, slots=True)
class Token:
    """스캐너가 만든 토큰. value는 규칙의 builder가 결정합니다."""

    kind: str
    value: Any
    start: int
    end: int
    text: str
    weak: bool = False


class Split(tuple[Token, ...]):
    """builder가 하나의 매칭을 여러 토큰으로 나눠 내보낼 때 반환합니다 (예: '다음주말' → 주 + 주말)."""

    __slots__ = ()


Builder = Callable[["re.Match[str]"], Any]


@dataclass(frozen=True, slots=True)
class TokenRule:
    """
    Attributes:
        kind: 토큰 종류
        pattern: 현재 위치에서 match()로 시도할 정규식
        build: 매칭 → 토큰 값. None을 반환하면 매칭을 거부하고, Split을 반환하면 그 토큰들을 그대로 사용
        right_boundary: True면 오른쪽 경계 규칙을 적용
        weak: 문맥이 있어야 의미가 있는 토큰 표시 (해석 단계에서 사용)
        attachable: True면 앞말에 붙어 있어도 매칭 (왼쪽 경계 예외). 패턴 자체가 충분히 구별될 때만
    """

    kind: str
    pattern: re.Pattern[str]
    build: Builder
    right_boundary: bool = False
    weak: bool = False
    attachable: bool = False


class Scanner:
    """TokenRule 목록으로 텍스트를 토큰화합니다. 규칙이 불변이므로 인스턴스를 재사용해도 안전합니다."""

    def __init__(self, rules: Iterable[TokenRule]) -> None:
        self._rules: tuple[TokenRule, ...] = tuple(rules)
        if not all(isinstance(rule, TokenRule) for rule in self._rules):
            raise TypeError("rules에는 TokenRule만 넣을 수 있습니다")
        self._has_attachable = any(rule.attachable for rule in self._rules)

    @property
    def rules(self) -> tuple[TokenRule, ...]:
        return self._rules

    def scan(self, text: str) -> list[Token]:
        tokens: list[Token] = []
        pos, last_end = 0, 0
        while pos < len(text):
            attached = not self._left_ok(text, pos, last_end)
            if attached and not self._has_attachable:
                pos += 1
                continue
            best = self._best_match(text, pos, attached)
            if best is None:
                pos += 1
                continue
            tokens.extend(best)
            pos = last_end = best[-1].end
        return tokens

    def _best_match(self, text: str, pos: int, attached: bool = False) -> Sequence[Token] | None:
        """attached: 앞말에 붙은 위치라 attachable 규칙만 시도"""
        best: Sequence[Token] | None = None
        best_end = pos
        for rule in self._rules:
            if attached and not rule.attachable:
                continue
            match = rule.pattern.match(text, pos)
            if match is None or match.end() <= best_end:
                continue
            if rule.right_boundary and not self._right_ok(text, match.end()):
                continue
            value = rule.build(match)
            if value is None:
                continue
            best = value if isinstance(value, Split) else (self._token(rule, match, value),)
            best_end = match.end()
        return best

    @staticmethod
    def _token(rule: TokenRule, match: re.Match[str], value: Any) -> Token:
        return Token(rule.kind, value, match.start(), match.end(), match.group(), rule.weak)

    @staticmethod
    def _left_ok(text: str, pos: int, last_end: int) -> bool:
        if pos == 0 or pos == last_end or not is_hangul(text[pos]):
            return True
        return not is_hangul(text[pos - 1])

    def _right_ok(self, text: str, end: int) -> bool:
        return ends_word(text, end) or any(rule.pattern.match(text, end) for rule in self._rules)
