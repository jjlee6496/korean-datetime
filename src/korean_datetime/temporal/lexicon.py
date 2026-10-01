"""날짜/시간 어휘 사전

어휘를 추가하려면 이 파일의 표만 고치면 됩니다. 키의 공백은 "공백 0개 이상"으로 매칭됩니다
('다음 주' → '다음주', '다음  주').
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class RepeatRule:
    """
    반복 접두 규칙: stem 앞에 repeat를 0~MAX_REPEAT번 붙인 말. 값 = sign × (base + 반복 횟수)

        RepeatRule("다음", "다", 1, +1)  →  다음 +1, 다다음 +2, 다다다음 +3 …
        RepeatRule("작년", "재", 1, -1)  →  작년 -1, 재작년 -2, 재재작년 -3 …
    """

    stem: str
    repeat: str
    base: int
    sign: int


MAX_REPEAT = 4  # 반복 한도. 넘으면 인식하지 않음 ('다다다다다다음주')

# ---- 일: 고정 표현 + 반복 규칙
DAY_REL: dict[str, int] = {
    "오늘": 0, "금일": 0, "당일": 0,
    "내일": 1, "낼": 1, "명일": 1, "익일": 1,
    "모레": 2, "모래": 2, "내일 모레": 2, "낼 모레": 2, "명후일": 2, "익익일": 2,
    "어제": -1, "어저께": -1, "작일": -1, "전일": -1,
}  # fmt: skip
DAY_REPEAT: tuple[RepeatRule, ...] = (RepeatRule("글피", "그", 3, 1),)  # 글피 +3, 그글피 +4, 그그글피 +5
# 과거: '제/저께' 앞의 '그·끄' 음절 수 n → -(1 + n). 그제 -2, 그끄제·그그제 -3, 그그그제 -4
DAY_PAST_SYLLABLES: tuple[str, ...] = ("그", "끄")
DAY_PAST_STEMS: tuple[str, ...] = ("저께", "저게", "제")

# ---- 주/달/해 앞 상대 수식어: 공통 반복 규칙 + 단위별 고정 표현
REL_PREFIX_REPEAT: tuple[RepeatRule, ...] = (
    RepeatRule("다음", "다", 1, 1),  # 다음·다다음·다다다음
    RepeatRule("다음", "다음", 1, 1),  # 다음다음 (국립국어원: 다다음 = 다음다음)
    RepeatRule("담", "다", 1, 1),  # 담·다담·다다담
    RepeatRule("저번", "저", 1, -1),  # 저번·저저번·저저저번
    RepeatRule("지난", "지", 1, -1),  # 지난·지지난·지지지난
    RepeatRule("전", "전", 1, -1),  # 전·전전·전전전 ('전주'는 지명과 겹쳐 주 단위에서 제외)
)
REL_PREFIX_FIXED: dict[str, int] = {"이번": 0}
WEEK_PREFIX_FIXED: dict[str, int] = {"금": 0, "차": 1, "내": 1, "익": 1}  # 금주, 차주, 내주, 익주
WEEK_PREFIX_EXCLUDED: tuple[str, ...] = ("전",)  # 전주(全州)
MONTH_PREFIX_FIXED: dict[str, int] = {"이": 0, "내": 1}  # 이달, 내달
MONTH_PREFIX_EXCLUDED: tuple[str, ...] = ("전",)  # '전달'은 대부분 전달(傳達)하다 (지난달은 전월)
MONTH_WORDS: dict[str, int] = {"금월": 0, "당월": 0, "익월": 1, "전월": -1, "전전월": -2}
YEAR_PREFIX_EXCLUDED: tuple[str, ...] = ("전", "담")  # '전해'(동사), '담해'는 쓰지 않음

# ---- 연: 고정 표현 + 반복 규칙
YEAR_REL: dict[str, int] = {
    "올해": 0, "금년": 0, "이번 해": 0,
    "내년": 1, "명년": 1, "익년": 1, "이듬해": 1,
    "내후년": 2,
    "지난해": -1, "전년": -1,
}  # fmt: skip
YEAR_REPEAT: tuple[RepeatRule, ...] = (
    RepeatRule("후년", "후", 2, 1),  # 후년 +2, 후후년 +3
    RepeatRule("작년", "재", 1, -1),  # 작년 -1, 재작년 -2, 재재작년 -3
)

# '오는 주말', '돌아오는 주말'은 '다음 주의 주말'이 아니라 '다가오는 주말'
UPCOMING_PREFIX: tuple[str, ...] = ("다가오는", "돌아오는", "오는")

WEEKDAYS: dict[str, int] = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

WEEK_NTH: dict[str, int] = {
    "첫째": 1,
    "첫 번째": 1,
    "첫": 1,
    "둘째": 2,
    "두 번째": 2,
    "셋째": 3,
    "세 번째": 3,
    "넷째": 4,
    "네 번째": 4,
    "다섯째": 5,
    "다섯 번째": 5,
    "마지막": -1,
    "막": -1,
    "끝": -1,
}

WEEK_PART: dict[str, str] = {"주말": "weekend", "주중": "weekdays", "평일": "weekdays", "주초": "early"}
WEEK_PART_SUFFIX: dict[str, str] = {
    "말": "weekend",
    "중": "weekdays",
    "초": "early",
}  # '다음주말', '이번주초'

KOREAN_MONTHS: dict[str, int] = {
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "오": 5,
    "유": 6,
    "육": 6,
    "칠": 7,
    "팔": 8,
    "구": 9,
    "시": 10,
    "십": 10,
    "십일": 11,
    "십이": 12,
}

# 월 없이도 이번 달을 뜻하는 표현 / 월 뒤에만 오는 표현
MONTH_PART_STRONG: dict[str, str] = {"말일": "last_day", "월초": "early", "월말": "late", "월중": "mid"}
MONTH_PART_WEAK: dict[str, str] = {
    "초": "early",
    "초순": "early",
    "상순": "early",
    "중순": "mid",
    "하순": "late",
    "말": "late",
    "첫날": "first_day",
    "첫 날": "first_day",
    "초하루": "first_day",
    "마지막 날": "last_day",
    "끝날": "last_day",
    "그믐": "last_day",
}

YEAR_PART: dict[str, str] = {
    "상반기": "h1",
    "하반기": "h2",
    "연초": "early",
    "년초": "early",
    "연말": "late",
    "년말": "late",
}


class HourMode(str, Enum):
    """시간대가 붙은 1~12시를 24시간제로 바꾸는 규칙 (24 이상은 다음 날)"""

    AM = "am"  # 12시 → 0시
    PM = "pm"  # 1~11시 → +12
    NOON = "noon"  # 1~6시 → +12 (점심/낮)
    EVENING = "evening"  # 1~11시 → +12, 12시 → 24시
    NIGHT = "night"  # 6~11시 → +12, 12시 → 24시, 1~5시 → 다음 날 새벽
    LATE_NIGHT = "late_night"  # 0/12시 → 24시, 1~5시 → 다음 날 새벽


@dataclass(frozen=True, slots=True)
class Period:
    mode: HourMode
    start: int | None  # 시간대만 말했을 때의 구간 [start, end) 시. None이면 시각과 함께만 쓰임 (am/pm)
    end: int | None


_EARLY_MORNING = Period(HourMode.AM, 6, 8)
_DUSK = Period(HourMode.PM, 17, 19)
_DAWN_SUN = Period(HourMode.AM, 5, 7)
_EVENING = Period(HourMode.EVENING, 18, 21)
_LATE_NIGHT = Period(HourMode.LATE_NIGHT, 24, 27)

PERIODS: dict[str, Period] = {
    "새벽녘": Period(HourMode.AM, 4, 6),
    "새벽": Period(HourMode.AM, 3, 6),
    "해 뜰 녘": _DAWN_SUN,
    "해 뜰 무렵": _DAWN_SUN,
    "동틀 녘": _DAWN_SUN,
    "동틀 무렵": _DAWN_SUN,
    "이른 아침": _EARLY_MORNING,
    "아침 일찍": _EARLY_MORNING,
    "아침": Period(HourMode.AM, 7, 10),
    "오전": Period(HourMode.AM, 9, 12),
    "점심 시간": Period(HourMode.NOON, 12, 13),
    "점심 때": Period(HourMode.NOON, 12, 13),
    "점심": Period(HourMode.NOON, 12, 13),
    "한낮": Period(HourMode.NOON, 12, 15),
    "오후": Period(HourMode.PM, 12, 18),
    "늦은 오후": Period(HourMode.PM, 15, 18),
    "해 질 녘": _DUSK,
    "해 질 무렵": _DUSK,
    "저녁 때": _EVENING,
    "저녁 무렵": _EVENING,
    "저녁": _EVENING,
    "퇴근하고": _EVENING,
    "퇴근 후에": _EVENING,
    "퇴근 후": _EVENING,
    "퇴근길": _EVENING,
    "밤 늦게": Period(HourMode.NIGHT, 22, 24),
    "늦은 밤": Period(HourMode.NIGHT, 22, 24),
    "밤": Period(HourMode.NIGHT, 21, 24),
    "심야": _LATE_NIGHT,
    "한밤중": _LATE_NIGHT,
    "am": Period(HourMode.AM, None, None),
    "a.m.": Period(HourMode.AM, None, None),
    "pm": Period(HourMode.PM, None, None),
    "p.m.": Period(HourMode.PM, None, None),
}
# 뒤에 특정 글자가 오면 시간대가 아님 ('낮은', '밤새')
PERIOD_SINGLE_SYLLABLE: dict[str, Period] = {"낮": Period(HourMode.NOON, 12, 15)}

FIXED_TIMES: dict[str, int] = {"정오": 12, "자정": 24}

NOW_WORDS: tuple[str, ...] = (
    "지금 바로",
    "지금 당장",
    "지금",
    "현재",
    "방금",
)
# 곧·당장: 대개 '곧 출시', '당장 해야'처럼 부사라 혼자서는 인식하지 않고, 시각 앞에서만 꾸밈 ('곧 3시')
IMMEDIATE_WORDS: tuple[str, ...] = ("곧바로", "곧", "즉시", "당장")
# 이따: 혼자 쓰면 지금, 뒤에 시각이 오면 그 시각을 꾸밈 ('이따 5시' = 5시, '이따 저녁' = 저녁)
SOON_WORDS: tuple[str, ...] = (
    "좀 이따가",
    "조금 이따가",
    "이따가",
    "좀 이따",
    "이따",
    "잠시 후",
    "잠시 뒤",
    "조금 후",
    "조금 뒤",
    "조금 있다가",
    "좀 있다가",
)

DIRECTIONS: dict[str, int] = {
    "이후": 1,
    "후": 1,
    "뒤": 1,
    "지나서": 1,
    "지나고": 1,
    "지나면": 1,
    "있다가": 1,
    "있으면": 1,
    "이전": -1,
    "전": -1,
    "앞": -1,
}

# 기간 단위 → (개월, 일, 초)
DURATION_UNITS: dict[str, tuple[int, int, int]] = {
    "년": (12, 0, 0),
    "해": (12, 0, 0),
    "개월": (1, 0, 0),
    "달": (1, 0, 0),
    "주일": (0, 7, 0),
    "주": (0, 7, 0),
    "일": (0, 1, 0),
    "시간": (0, 0, 3600),
    "분": (0, 0, 60),
    "초": (0, 0, 1),
}
DAY_TERMS: dict[str, int] = {
    "하루": 1,
    "이틀": 2,
    "사흘": 3,
    "나흘": 4,
    "닷새": 5,
    "엿새": 6,
    "이레": 7,
    "여드레": 8,
    "아흐레": 9,
    "열흘": 10,
    "보름": 15,
}
HALF_OF_UNIT: dict[str, tuple[int, int, int]] = {"시간": (0, 0, 1800), "년": (6, 0, 0), "해": (6, 0, 0)}

# 문맥(앞 문장·대화)의 때를 가리키는 말. 기준 시각으로 계산하면 틀리므로 든 표현을 통째로 인식하지 않음
# ('그다음 주 토요일', '그날 오전 9시', '거기서 세 시간 지나면'). 해석은 문맥을 아는 호출하는 쪽에서
ANAPHORA: tuple[str, ...] = (
    "그날", "그 날", "그때", "그 때", "그주", "그 주", "그다음 주", "그 다음 주", "그다음주",
    "그달", "그 달", "그다음 달", "그 다음 달", "그다음달", "그해", "그 해", "그다음 해", "그 이듬해",
    "거기서", "그로부터", "그때부터", "이때부터",
)  # fmt: skip
# 달력 밖 정보가 필요한 단위 (회사·기관 휴무일). 계산할 수 없으므로 표현 전체를 인식하지 않음
CALENDAR_DEPENDENT: tuple[str, ...] = ("영업일", "근무일", "업무일", "휴무일")

# 막연한 때 (ParseOptions(vague=True)일 때만 인식). 넣고 빼기는 이 표만 고치면 됨.
# AI허브 시간 표현 데이터에서 시간 표현으로 레이블된 비율이 높은 것만 (최근 86~91%, 요즘 92% 등).
# 넣지 않은 것: '곧·당장·즉시'(레이블 2~32%, 대개 부사), '당시'(문맥 지시), '미래'('미래 기술' 같은 관형어),
# '앞으로'(뉴스 오탐 108 > 레이블 56, '앞으로 나아가다'), '요새'(역사 문서의 요새(要塞))
VAGUE_WORDS: dict[str, str] = {
    "최근": "recent", "요즘": "recent", "근래": "recent", "요즈음": "recent",
    "과거": "past", "예전": "past", "옛날": "past",
    "향후": "future", "조만간": "future", "나중": "future",
}  # fmt: skip

# 앞 날짜 기준 하루 전후 ('화요일의 전날', '말일 다음 날'). 단독으로는 문맥 의존이라 인식하지 않음
DAY_SHIFT: dict[str, int] = {
    "전날": -1, "그 전날": -1, "그전날": -1, "하루 전날": -1,
    "다음 날": 1, "다음날": 1, "그다음 날": 1, "그 다음 날": 1, "그다음날": 1, "이튿날": 1, "이튿 날": 1,
}  # fmt: skip

# 요일·기념일 앞의 수식어 ('지난 금요일', '다음 추석')
MODIFIERS: dict[str, int] = {
    "지난": -1,
    "저번": -1,
    "이번": 0,
    "다음": 1,
    "오는": 1,
    "돌아오는": 1,
    "다가오는": 1,
}
# 어떤 날짜·시각 앞에도 오는 '다가오는', 반복 '매월' 등: 다음에 올 때 (반복 자체는 표현하지 않고 다음 한 번)
# 시각까지 지났는지 보고 다음 주기로 넘김 ('매달 말일 자정 10분 전'@말일 23:51 → 다음 달 말일)
UPCOMING_ANY: tuple[str, ...] = ("다가오는", "매월", "매달", "매년", "매주")
# 기간으로 쓰였음을 나타내는 뒤따르는 말 ('3일간', '7일 이내', '1일 1식')
DURATION_SUFFIX = (
    r"\s*(?:간|동안|째|연속|이내|이상|이하|내로|내에|안에|만에|마다|씩)|\s+\d+\s*(?:식|회|번|끼)"
)

# 기준 시각과 같은 시각 ('내일 이 시각' = 내일 지금 시각)
SAME_TIME_WORDS: tuple[str, ...] = (
    "지금 이 시각", "지금 이 시간", "이 시각", "이 시간", "같은 시각", "같은 시간",
)  # fmt: skip
# 기준일과 같은 날 ('작년 이맘때' = 1년 전 오늘). 시각까지는 가리키지 않음
SAME_DAY_WORDS: tuple[str, ...] = ("이맘때", "이맘 때", "이때쯤", "요맘때")
