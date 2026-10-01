# 기대값 식(Expectation DSL)과 정답셋 관리

날짜/시간 정답을 **기준 시각(ref)에서 계산하는 식**으로 적는 작은 언어입니다.
정답이 절대 날짜에 묶이지 않으므로, 같은 정답셋을 어떤 날짜·시각에서도 돌릴 수 있습니다.

```json
{"category": "weekday", "text": "금요일", "expect": "next(FRI)"}
```

"금요일"이라는 입력은 기준 시각이 언제든 `next(FRI)`, 즉 "오늘 이후 가장 가까운 금요일"로 해석되어야 한다는 뜻입니다.

- 구현: [`src/korean_datetime/temporal/expectation.py`](../src/korean_datetime/temporal/expectation.py)
- 정답셋: [`tests/data/temporal_gold.jsonl`](../tests/data/temporal_gold.jsonl)
- 이 문서가 코드와 맞는지 `tests/test_docs.py`가 검사합니다. 함수·메서드·카테고리를 추가하면 이 문서도 함께 고쳐야 테스트가 통과합니다.

---

## 1. 전체 구조

```
tests/data/temporal_gold.jsonl     기대값 식 정답셋 (기준 시각 무관)            ← 평소에 관리하는 파일
tests/data/temporal_anchor.jsonl   손으로 계산한 절대값 (2026-09-28 14:30, 2027-12-31 23:10, 2028-02-29 08:05) ← 식 평가기 자체 검증용
tests/references.py                정답셋을 돌릴 기준 시각 목록
tests/test_evaluation.py           평가 실행, 임계값 검사
tests/test_expectation_dsl.py      DSL 자체 단위 테스트
tests/test_docs.py                 이 문서와 코드 동기화 검사
```

평가 흐름:

```
temporal_gold.jsonl의 각 줄 × 기준 시각 목록
   ├─ 식 평가기: evaluate_expectation(expect, ref) → 정답 (start, end, kind) 또는 none
   └─ 파서:     parse(text, now=ref)                → 예측
        → 비교 → 카테고리별 precision / recall / F1 / accuracy → 임계값 검사
```

**식 평가기가 파서 코드를 쓰지 않는 이유**: 둘이 같은 코드를 공유하면 같은 버그를 함께 가져서 테스트가 통과해 버립니다.
식 평가기는 표준 라이브러리 `calendar`만으로 따로 구현했습니다. 예외로 음력은 `lunar_to_solar`를 같이 쓰며, 음력 변환은 `tests/test_holidays.py`에서 한국천문연구원 날짜로 따로 검증합니다.
식 평가기가 맞는지는 **앵커 대조**(앵커 행의 기준 시각에서 계산한 식 = 손계산 절대값)로 확인합니다. 앵커는 평상시·연말·윤일 세 시점입니다.

---

## 2. 정답셋 파일 형식 (JSONL)

첫 줄은 메타 정보(선택), 그다음 한 줄에 한 케이스입니다.

```json
{"_meta": {"note": "설명"}}
{"category": "datetime", "text": "다음주 월요일 저녁 7시", "expect": "week(1).weekday(MON).at(19:00)"}
{"category": "negative", "text": "오일 교환하러 가", "expect": "none"}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `category` | ○ | 리포트 집계 단위 ([6. 카테고리](#6-카테고리)) |
| `ambiguous` | | **문장만으로 정해지는** 모호성 목록 (예: `["next_weekend"]`). 기준 시각에 따라 생기는 모호성은 식이 계산하므로 적지 않습니다 ([5.6](#56-모호성-표시)) |
| `text` | ○ | 파서 입력. 정답셋 안에서 중복되면 안 됩니다 |
| `expect` | ○ | 기대값 식. `none`이면 "아무것도 인식하지 않아야 함" |

파서는 `parse()`의 **첫 번째 결과**를 비교합니다. 문장 안에 표현이 여러 개면 첫 표현이 정답입니다.
정답은 **기본 옵션**(`ParseOptions()`) 기준입니다. 옵션별 동작은 `tests/test_options.py`에서 따로 검사합니다.

---

## 3. 값의 타입 (Expect)

식을 계산하면 `Expect` 하나 또는 `none`(None)이 나옵니다.

| 필드 | 타입 | 뜻 |
|---|---|---|
| `start` | datetime | 시작 (포함) |
| `end` | datetime 또는 None | 끝 (미포함). **None이면 시작 시각만 비교** |
| `kind` | `date` / `time` / `datetime` | 파서 결과의 `kind`와 비교 |
| `grain` | 아래 표 | 식 내부 전용. 어떤 메서드를 붙일 수 있는지 결정 |

### 3.1 grain (구간 종류)

| grain | 뜻 | 만드는 것 | 붙일 수 있는 메서드 |
|---|---|---|---|
| `day` | 하루 (또는 며칠) | `today`, `day`, `md`, `ymd`, `next`, `prev`, `lunar`, 달·주 메서드 결과 | [날 메서드](#43-날-메서드-grain--day) |
| `week` | 월요일부터 7일 | `week`, `.row()` | [주 메서드](#44-주-메서드-grain--week) |
| `month` | 한 달 | `month`, `mon`, `.month()` | [달 메서드](#45-달-메서드-grain--month) |
| `year` | 한 해 | `year`, `yr` | [해 메서드](#46-해-메서드-grain--year) |
| `half` / `quarter` | 반기 / 분기 | `.half()`, `.quarter()` | 범위 메서드만 |
| `instant` | 한 시각 (end 없음) | `now`, `at`, `nearest`, `.at()`, `.hour()` | 범위 메서드, 오프셋 |
| `period` | 시간대 구간 | `period`, `.period()` | 범위 메서드, 오프셋 |
| `range` | 범위 ("A부터 B까지") | `.to()`, `.to_after()` | 범위 메서드, 오프셋 |

`.weekend()`, `.weekdays()`, `.early()`, `.part()`, `.nthweekend()`, `.around()`도 `day` grain(며칠짜리 구간)을 돌려줍니다.
grain이 맞지 않는 메서드를 쓰면 오류입니다. 예: `today.weekday(MON)` → "`.weekday()`은(는) week 구간에만 쓸 수 있습니다".

### 3.2 kind 규칙

| 식 | kind |
|---|---|
| 날짜 구간 (`today`, `week(1)`, `md(6, 3)` …) | `date` |
| 날짜 없는 시각 (`at`, `nearest`, `period`) | `time` |
| 날짜 + 시각 (`.at()`, `.hour()`, `.period()`), `now` | `datetime` |
| `A.to(B)` | A의 kind. A가 `date`이고 B가 아니면 `datetime` |
| 오프셋 (`+ 1d` 등) | 바뀌지 않음 |

### 3.3 인자 타입

| 타입 | 형식 | 예 |
|---|---|---|
| 정수 | `N`, `+N`, `-N` | `15`, `+1`, `-1` |
| 시각 | `H:MM` 또는 `HH:MM`. 0~47시, 0~59분. **24 이상은 다음 날**. `nearest`는 0~12시만 | `3:00`, `15:30`, `24:00`(다음 날 0시), `25:00`(다음 날 1시) |
| 요일 | `MON` `TUE` `WED` `THU` `FRI` `SAT` `SUN` (대문자) | `FRI` |
| 단어 | 메서드마다 정해진 값 | `early`, `mid`, `late` |
| 식 | 다른 식 | `future(md(1, 2))` |

시각 자리에 정수만 쓰면 정각으로 봅니다 (`.hour(3)` = `.hour(3:00)`).

---

## 4. 함수와 메서드 (전체 목록)

### 4.1 기본 값 (atom)

모든 기본 값은 **기준 시각 ref**에서 계산합니다. "주기"는 `future`/`past`가 넘기는 단위입니다([5.1](#51-future와-past)).

| 식 | 결과 | kind / grain | 주기 | 예 (ref = 2026-09-28 월 14:30) |
|---|---|---|---|---|
| `today` | 기준일 하루 | date / day | 일 | 09-28 |
| `now` | 기준 시각 (분 단위로 내림) | datetime / instant | 없음 | 09-28 14:30 |
| `none` | 인식하지 않아야 함 | — | — | — |
| `day(D)` | 이번 달 D일. 없으면 none | date / day | 월 | `day(15)` → 09-15, `day(31)` → none |
| `md(M, D)` | 올해 M월 D일. 없으면 none | date / day | 연 | `md(6, 3)` → 2026-06-03 |
| `ymd(Y, M, D)` | 절대 날짜. 없으면 none | date / day | 없음 | `ymd(2025, 4, 14)` |
| `week(K)` | K주 뒤의 주 (월~일, 이번 주 = 0) | date / week | 주 | `week(1)` → 10-05 ~ 10-12 |
| `month(K)` | K달 뒤의 달 (이번 달 = 0) | date / month | 월 | `month(-1)` → 8월 |
| `mon(M)` | 올해 M월 | date / month | 연 | `mon(10)` → 2026년 10월 |
| `year(K)` | K년 뒤의 해 (올해 = 0) | date / year | 연 | `year(1)` → 2027년 |
| `yr(Y)` | Y년 | date / year | 없음 | `yr(2028)` |
| `next(WD)` | 오늘을 **뺀** 다음 WD요일 | date / day | 주 | `next(MON)` → 10-05 |
| `prev(WD)` | 오늘을 **뺀** 이전 WD요일 | date / day | 주 | `prev(FRI)` → 09-25 |
| `at(T)` | 오늘 T시각 (24 이상은 다음 날) | time / instant | 일 | `at(25:00)` → 09-29 01:00 |
| `nearest(T)` | 오전/오후가 모호한 T: 기준 시각 이후 가장 가까운 후보 (오늘 T, 오늘 T+12, 내일 T, 내일 T+12 순) | time / instant | 없음 | `nearest(2:00)` → 09-29 02:00 |
| `period(A, B)` | 오늘 A시 ~ B시 | time / period | 일 | `period(18, 21)` |
| `lunar(M, D)` | 올해 음력 M월 D일 | date / day | 연 | `lunar(8, 15)` → 2026-09-25 |
| `future(X)` | [5.1](#51-future와-past) | X를 따름 | — | `future(md(6, 3))` → 2027-06-03 |
| `past(X)` | [5.1](#51-future와-past) | X를 따름 | — | `past(md(12, 25))` → 2025-12-25 |
| `latest(X)` | [5.1](#51-future와-past) — `Cycle.PAST` | X를 따름 | — | `latest(day(29))`@11-01 → 10-29 |
| `closest(X)` | [5.1](#51-future와-past) — `Cycle.NEAREST` | X를 따름 | — | `closest(day(29))`@11-01 → 10-29, `closest(day(15))`@11-01 → 11-15 |

### 4.2 오프셋

`식 + N단위`, `식 - N단위`. 시작을 옮기고 **구간 길이는 유지**합니다.

| 단위 | 뜻 | 예 |
|---|---|---|
| `d` | 일 | `today + 3d` |
| `w` | 주 (7일) | `today + 2w` |
| `mo` | 달. 말일 보정 (1/31 + 1mo → 2/28) | `today + 1mo` |
| `y` | 해 (= 12mo) | `today + 1y` |
| `h` | 시간 | `now + 1h` |
| `min` | 분 | `now - 30min`, `future(at(17:00) - 5min)` |
| `s` | 초 | `now + 30s` |

여러 번 이어 쓸 수 있습니다 (`now + 2h + 30min`).

> **주의: 달·해 오프셋은 한 번에 적습니다.** 오프셋은 하나씩 차례로 적용되고, 달·해 단위는 적용할 때마다 말일 보정을 합니다.
> "1년 2개월 뒤"@2028-02-29를 `today + 1y + 2mo`로 적으면 2029-02-28 → 2029-04-28이 됩니다.
> 하나의 기간 표현은 합쳐서 `today + 14mo`로 적어야 2029-04-29(파서와 같은 값)가 됩니다. 일·주·시·분 단위는 순서와 상관없습니다.

### 4.3 날 메서드 (grain = `day`)

| 메서드 | 결과 | kind / grain | 예 |
|---|---|---|---|
| `.at(T)` | 그날 T시각 | datetime / instant | `(today + 1d).at(15:00)` |
| `.hour(H)` | 그날 모호한 H시. **그날이 오늘이면** 기준 시각 이후 후보(H, H+12) 중 먼저 오는 것, 둘 다 지났거나 다른 날이면 **주간 규칙**(7~11시는 오전, 12시는 정오, 1~6시는 오후) | datetime / instant | `(today + 1d).hour(3)` → 15:00 |
| `.period(A, B)` | 그날 A시 ~ B시 | datetime / period | `(today + 1d).period(7, 10)` |
| `.around(앞, 뒤)` | 그날 앞 N일 ~ 뒤 N일 (포함, 0 이상) | date / day | `year(0).lunar(8, 15).around(1, 1)` → 추석 연휴 3일 |

### 4.4 주 메서드 (grain = `week`)

| 메서드 | 결과 | 예 |
|---|---|---|
| `.weekday(WD)` | 그 주의 WD요일 | `week(1).weekday(MON)` |
| `.weekend()` | 토~일 (2일) | `week(0).weekend()` |
| `.weekdays()` | 월~금 (5일) | `week(1).weekdays()` |
| `.early()` | 월~화 (2일, '주초') | `week(1).early()` |

### 4.5 달 메서드 (grain = `month`)

| 메서드 | 결과 | 없을 때 | 예 |
|---|---|---|---|
| `.day(D)` | D일 | none (예: 9월 31일) | `month(1).day(15)` |
| `.first()` | 1일 | — | `month(1).first()` |
| `.last()` | 말일 | — | `month(-1).last()` |
| `.part(early\|mid\|late)` | 초순 1~10일 / 중순 11~20일 / 하순 21일~말일 | — | `month(0).part(mid)` |
| `.nth(N, WD)` | N번째 WD요일 (N = -1이면 마지막) | none (예: 다섯째 금요일) | `month(1).nth(1, FRI)` |
| `.row(N)` | 달력 **N번째 줄**(월~일, week grain). 1일이 든 줄이 1, 말일이 든 줄이 -1. 앞뒤 달 날짜를 포함할 수 있음. 이 줄에 `.weekday()`를 붙였을 때 **1일 이전(앞 달) 칸이 이미 지난 날이면 +1주** | none (그 달에 없는 줄) | `month(1).row(3).weekday(SAT)`, `future(mon(12).row(2))` |
| `.nthweekend(N)` | N번째 **토요일**부터 2일 ("셋째 주말") | none | `month(1).nthweekend(3)` |

### 4.6 해 메서드 (grain = `year`)

| 메서드 | 결과 | 예 |
|---|---|---|
| `.month(M)` | 그해 M월 (month grain) | `year(1).month(3)`, `year(0).month(6).day(6)` |
| `.half(N)` | 상반기(1) / 하반기(2) | `future(year(0).half(1))` |
| `.quarter(N)` | N분기 | `year(1).quarter(1)` |
| `.lunar(M, D)` | 그해 음력 M월 D일 | `year(0).lunar(1, 1)` |

### 4.7 범위 메서드 (모든 grain)

| 메서드 | 끝(B)을 계산하는 기준 | 쓰는 곳 |
|---|---|---|
| `A.to(B)` | **원래 기준 시각** | B가 스스로 기준을 가질 때: `(today + 1d).to(today + 2d)` ("내일부터 모레까지"의 모레는 오늘 기준) |
| `A.to_after(B)` | **A의 시작 시각** | B에 생략된 정보를 A에서 이어받을 때: `nearest(3:00).to_after(nearest(5:00))`, `future(md(10, 3)).to_after(future(day(5)))` |

범위의 끝은 B가 날짜(`date`)면 **B의 끝**(B 포함), 시각이면 **B의 시작**입니다.

끝이 시작보다 앞서거나 같으면(뒤집힌·빈 범위) 식 오류(`ExpectationError`)입니다. 파서는 그런 범위를 만들지 않으므로, 이런 값이 나오는 기준 시각이 있다면 식을 고쳐야 합니다(보통 `.to()` → `.to_after()`).

- "10월 3일부터 5일까지" → 10-03 ~ 10-06 (5일 포함)
- "3시부터 5시까지" → 15:00 ~ 17:00

---

## 5. 동작 규칙

### 5.1 future와 past

연/월이 생략된 표현은 "주기가 정해지지 않은 것"입니다. 파서는 기본적으로 이미 지난 경우 다음 주기로 넘기며, 식에서는 이를 `future`로 표현합니다.

**`future(X)`**

1. 기준 시각에서 X를 계산합니다.
2. 결과가 없거나 **이미 끝났으면**, 기준 시각을 X의 주기만큼 옮겨 다시 계산합니다 (최대 4번).

"이미 끝났다"의 기준:

| X의 종류 | 끝난 조건 |
|---|---|
| 날짜 (`date`) | `end` ≤ 오늘 0시 (오늘을 포함하는 구간은 끝나지 않음) |
| 시각 (end 없음) | `start` < 기준 시각 (분 단위) |
| 시간대 | `end` ≤ 기준 시각 |

X의 주기는 **가장 안쪽 기본 값**이 정합니다([4.1](#41-기본-값-atom)의 "주기" 열).

| X | 주기 | 예 |
|---|---|---|
| `md(6, 3)` | 연 | 9월에 "6월 3일" → 내년 6월 3일 |
| `day(15)`, `month(0).nth(2, FRI)` | 월 | 20일에 "15일" → 다음 달 15일 |
| `week(0).weekdays()` | 주 | 토요일에 "주중" → 다음 주 월~금 |
| `at(10:00)`, `period(7, 10)` | 일 | 14시에 "오전 10시" → 내일 10시 |

없는 날짜도 다음 주기로 넘어갑니다: `future(day(31))`은 9월이면 10월 31일, `future(md(2, 29))`는 2026년이면 2028년 2월 29일입니다.
주기가 없는 식(`ymd`, `yr`, `now`, `nearest`)이나 future를 중첩하면 오류입니다.

**`latest(X)`** (`Cycle.PAST`): X가 오늘이나 그 전에 시작하는 가장 최근 주기. `past`와 달리 **오늘을 포함**합니다 ("1일"@1일 → 오늘).

**`closest(X)`** (`Cycle.NEAREST`): 이번 주기, X가 있는 이전 주기, X가 있는 다음 주기 중 오늘에서 가장 가까운 것(오늘을 포함하면 거리 0, 같으면 미래 쪽). 주기가 바뀌면 `cycle_shifted`.

파서의 `ParseOptions(cycle=...)`와의 대응: `FUTURE` → `future(X)`, `PAST` → `latest(X)`, `NEAREST` → `closest(X)`, `CURRENT` → `X`. 기본 정답셋은 `FUTURE` 기준이고, 나머지는 `tests/test_cycle.py`에서 같은 식을 감싸 검증합니다.

**`past(X)`** ("지난 X"): X가 오늘 0시 **이전에 시작**하면 그대로 쓰고, 아니면 이전 주기로 거슬러 올라가며 X가 있는 첫 주기를 씁니다(최대 4번). "지난 추석"은 `past(lunar(8, 15))`, "지난 크리스마스"는 `past(md(12, 25))`, "지난 2월 29일"은 `past(md(2, 29))`(2026-09-28 기준 2024-02-29)입니다.

### 5.2 파서 정책과의 대응

파서 규칙을 그대로 옮긴 것이 아니라, **"이 문장은 이렇게 해석되어야 한다"는 정의**입니다. 식이 파서와 다르면 둘 중 하나가 틀린 것입니다.

| 문장 유형 | 식 | 정책 |
|---|---|---|
| 연/월 생략 날짜 | `future(md(M, D))`, `future(day(D))` | 지났으면 다음 주기 (`cycle=FUTURE`, 기본) |
| 명시된 연/월 (올해, 이번달, 2027년) | `year(0).month(6).day(6)`, `month(0).day(15)` | 넘기지 않음 |
| 요일만 ("금요일") | `next(FRI)` | 오늘 제외 |
| "이번 금요일" | `week(0).weekday(FRI)` | 이번 주 (지났어도 이번 주) |
| "셋째 **주** 토요일", "마지막 **주**", "둘째 **주** 주말" | `month(1).row(3).weekday(SAT)`, `future(month(0).row(-1))` | **달력 줄 기준 주차**: 1일이 든 월~일 줄이 1주, 말일이 든 줄이 마지막 주. 앞뒤 달 날짜일 수 있음. 단 요일이 **1일 이전 칸이면서 이미 지난 날**이면 +1주 ("다음달 첫째 주 월요일"@2028-02-29 → 2/28이 아니라 3/6). 말일 이후 칸은 그대로 |
| "셋째 토요일", "마지막 금요일", "셋째 주말" (주 없음) | `month(1).nth(3, SAT)`, `month(1).nthweekend(3)` | 그 달 안의 **N번째 요일** |
| "지난 금요일" | `prev(FRI)` | 오늘 제외 |
| "지난 3일" | `past(day(3))` | 오늘 이전 가장 최근의 3일 |
| "지난 3일간", "지난 2주간" | `(today - 3d).to(today - 1d)` | N 전부터 어제까지 (범위) |
| "지난 저녁" | `past(period(18, 21))` | 어제 저녁 |
| 오전/오후 없는 시각, 날짜 없음 | `nearest(H:MM)` | 가장 가까운 미래 (`AmbiguousHour.NEAREST_FUTURE`) |
| 오전/오후 없는 시각 + 날짜 | `날짜.hour(H)` | 오늘이면 가까운 미래, 아니면 주간 규칙 |
| 오전/오후·24시간제·시간대 있음, 날짜 없음 | `future(at(T))` | 지났으면 내일 |
| 시간대만 ("저녁") | `future(period(A, B))` | 끝났으면 내일 |
| 상대 시각 ("1시간 후") | `now + 1h` | 기준 시각 기준 (초는 버림) |
| 특정 시각 기준 오프셋 ("17시 5분 전") | `future(at(17:00) - 5min)`, 모호한 시각은 `nearest(4:50)` ("다섯시 십분 전") | **오프셋을 적용한 결과**가 미래가 되도록 (16:57에 "17시 5분 전" → 내일 16:55) |
| 범위, B가 생략형 | `A.to_after(B)` | B를 A 이후로 해석 |
| 뒤집힌 범위 ("10월 5일부터 10월 3일까지") | `future(md(10, 5))` | 범위로 합치지 않고 첫 표현만 |
| 없는 날짜, 기간 표현, 오탐 | `none` | 인식하지 않음 |

### 5.3 비교 규칙

`src/korean_datetime/temporal/evaluation.py`의 `temporal_matches`가 비교합니다. 식 결과는 아래 필드로 바뀌어 비교됩니다(`Expect.as_expected()`).

| 필드 | 비교 방법 |
|---|---|
| `start` | 항상. 정답에 시간대가 있으면(기준 시각이 시간대를 가질 때) **시간대까지** 비교, 없으면 벽시계 시각만 |
| `end` | 식 결과에 end가 있을 때 (구간) |
| `kind` | 항상 |
| `shape` | `instant`(시각)이면 예측도 **한 시각**이어야 함: 범위가 아니고 길이 1시간 이하. `span`이면 end로 비교 |
| `is_range` | 항상. `.to()`/`.to_after()`로 만든 식만 true, 예측의 `is_range`와 같아야 함 |

- `expect`가 `none`이면 파서도 아무것도 인식하지 않아야 합니다(음성 케이스).

검출과 값을 나눠 집계합니다.

| 정답 | 파서 | 분류 |
|---|---|---|
| 있음 | 있음 | TP (값까지 맞으면 정확) |
| 있음 | 없음 | FN |
| none | 있음 | FP |
| none | 없음 | TN |

| 지표 | 식 | 뜻 |
|---|---|---|
| precision | TP / (TP+FP) | 인식한 것 중 인식해야 했던 것 |
| recall | TP / (TP+FN) | 인식해야 했던 것 중 인식한 것 |
| **value_acc** | 값까지 맞은 TP / TP | 인식한 것 중 **정규화 값이 맞은 비율** (정규화 품질) |
| accuracy | (값까지 맞은 TP + TN) / 전체 | 전체 정답률 |

### 5.4 기준 시각 목록 (`tests/references.py`)

| 함수 | 쓰는 곳 | 내용 |
|---|---|---|
| `sampled_references()` | `uv run pytest` (기본) | **항상 같은 고정 목록**. 2026~2027 5일 간격 14:30, 월초·월말·윤일(2028-02-29), 2026년 매월 1일의 8개 시각(00:10, 06:00, 08:05, 11:59, 12:00, 16:57, 18:30, 23:50), 시간대가 있는 KST 23:50 12개 |
| `full_references()` | `uv run pytest -m slow` | 2026~2027 매일 14:30, 주 1회 7개 시각, 경계일, KST 12개 |
| `real_now()` | `test_expression_gold_at_real_now` (기본) | **실행 시점의 실제 현재 시각** 하나. 고정 목록과 분리한 스모크 테스트이며, 실행 시 그 시각을 출력 |

고정 목록은 실패를 그대로 재현할 수 있고, 실제 현재 시각 테스트는 "오늘" 기준 동작을 확인합니다.
실패 리포트에는 문장과 함께 어떤 기준 시각에서 틀렸는지(`'3시' @ 2026-03-01 23:50`)가 나옵니다.

### 5.6 모호성 표시

파서는 값을 정책대로 하나로 정하고, 추정이 들어간 부분을 `TemporalExpression.ambiguities`로 알립니다(값은 바뀌지 않음).
정답의 기대 모호성은 **식이 계산한 것 ∪ 정답셋의 `ambiguous`**이며, 둘이 파서 표시와 정확히 같아야 합니다.

| 종류 | 뜻 | 누가 정함 | 식에서 생기는 곳 |
|---|---|---|---|
| `meridiem` | 오전/오후 없는 1~11시 → 가까운 미래로 정함. **문장만 보고 항상** (기준 시각 무관) | 식 | `nearest(H:MM)`, `.hour(H)` |
| `noon_or_midnight` | 오전/오후 없는 12시 → 정오/자정 중 가까운 미래 | 식 | `nearest(12:00)`, `.hour(12)` |
| `cycle_shifted` | 생략된 연/월/일(시각은 날짜)이 지나 다음 주기로 넘김 | 식 | `future(X)`가 실제로 넘겼을 때, `nearest`가 내일 후보를 골랐을 때 |
| `same_weekday` | 오늘과 같은 요일이라 다음 주로 정함 | 식 | `next(WD)`가 7일 뒤를 골랐을 때 |
| `day_attribution` | 24시 이상(자정, 밤 1시, 심야) — 어느 날에 속하는지 모호 | 식 | `at`/`.at`의 시각이 24시 이상, `period`/`.period`의 시작이 24시 이상 |
| `multi_day_time` | 여러 날 구간에 시각이 붙어 첫날로 정함 | 식 | 이틀 이상 구간(`week(1)`, `.weekend()`)에 `.at`/`.hour`/`.period` |
| `calendar_row_spill` | 달력 줄 주차의 요일이 앞뒤 달 칸 | 식 | `.row(N).weekday(WD)`가 그 달 밖이면 (+1주로 옮긴 경우 포함) |
| `next_weekend` | '다음 주말'을 '다음 주의 주말'로 정함 | 정답셋 | `"ambiguous": ["next_weekend"]` |
| `two_digit_year` | 두 자리 연도를 19xx/20xx로 정함 | 정답셋 | `"ambiguous": ["two_digit_year"]` |

모호성은 합쳐집니다: 메서드·오프셋은 앞 식의 모호성을 이어받고, 범위(`.to`, `.to_after`)는 양쪽을 합칩니다.
범위의 시작에 오전/오후가 정해져 있으면("오후 3시부터 5시까지") 끝의 `meridiem`은 붙이지 않습니다. 식으로는 끝을 `at(17:00)`처럼 적습니다.

리포트에는 값 지표와 별도로 종류별 모호성 tp/fp/fn이 나옵니다. 값이 틀린 케이스는 값 지표에서 이미 실패하므로 모호성 집계에서 뺍니다.

### 5.5 아직 표현할 수 없는 것 (확장 후보)

| 한계 | 예 | 필요한 계약 |
|---|---|---|
| 첫 번째 결과 하나만 비교 | "내일 3시에 보고 모레 5시에" | 결과 목록 비교 (`expect_all`) |
| 기준이 항상 ref 하나 | "지난주에 … 그다음 주 토요일" (사건 기준) | 문맥 기준(`anchor`) |
| 모호성 대안값 | "12시"의 정오/자정 두 값 | 1단계(검출)는 [5.6](#56-모호성-표시)으로 완료. 대안값(`alternatives`)은 다음 단계 |
| 첫 결과만 비교 (선택지) | "다음주 월요일 아니면 화요일" | 파서는 두 결과를 돌려주고 B가 A의 문맥(다음주)을 이어받음. 정답셋은 첫 결과만 비교하므로 두 번째는 `tests/test_api.py`에서 검사 |

---

## 6. 카테고리

| category | 대상 | 대표 식 |
|---|---|---|
| `relative_day` | 오늘, 내일, 모레, 글피, 어제, 그제 | `today + 1d` |
| `relative_word` | 반복형(다다다음주, 저저저번달, 그그제, 후후년)과 한자어(명일, 익주, 익월, 익년) | `week(3)`, `year(3)` |
| `day_offset` | N일/주/개월/년 후·전, 이틀, 보름 | `today + 3d`, `today + 1mo` |
| `weekday` | 요일, 이번주/다음주 + 요일 | `next(FRI)`, `week(1).weekday(MON)` |
| `weekday_modifier` | 지난/이번/다음 + 요일·기념일, 마지막 금요일 | `prev(FRI)`, `past(lunar(8, 15))` |
| `week_range` | 주말, 주중, 주초, 이번주 | `week(0).weekend()`, `future(week(0).weekdays())` |
| `month_day` | M월 D일, D일 (한글 수사 포함) | `future(md(10, 15))`, `future(day(15))` |
| `invalid_date` | 없는 날짜 (2월 30일, 9월 31일) | `none`, `future(day(31))` |
| `formatted` | 2026-10-01, 10/15, 25.07.15, 99년 | `ymd(2026, 10, 1)` |
| `month_relative` | 다음달 15일, N째 주 X요일(달력 줄), N째 X요일, 말일, 첫날 | `month(1).row(1).weekday(FRI)`, `month(1).nth(3, SAT)` |
| `month_year_range` | 다음달, 10월, 초·중순, N째주(달력 줄), 올해, 상반기, 분기 | `month(1)`, `future(mon(12).row(2))` |
| `holiday` | 양력·음력 기념일, 연휴 | `future(md(12, 25))`, `future(lunar(8, 15))` |
| `clock` | 3시, 오후 3시, 15:30, 밤 1시, 자정, 17시 5분 전 | `nearest(3:00)`, `future(at(25:00))` |
| `period` | 저녁, 밤, 아침, 새벽, 점심 | `future(period(18, 21))` |
| `relative_time` | 지금, 1시간 후, 30분 전 | `now + 1h` |
| `datetime` | 날짜 + 시각/시간대 | `(today + 1d).at(15:00)` |
| `separator` | 10월 5일(월) 오후 2시, ISO `T` | `future(md(10, 5)).at(14:00)` |
| `range` | A부터 B까지, A~B | `nearest(3:00).to_after(nearest(5:00))` |
| `range_rejected` | 뒤집힌 범위, 빈 범위 | `future(md(10, 5))` |
| `duration_not_date` | 3일간, 7일 이내, 30분 동안 | `none` |
| `ambiguity` | 모호성 표시 검증용 (여러 날 + 시각, 자정 넘김, 다음 주말) | `week(0).weekend().at(15:00)` |
| `negative` | 날짜/시간이 아닌 문장, 잘못된 값 | `none` |

새 카테고리를 만들면 이 표에도 추가해야 합니다(`tests/test_docs.py`가 검사).

---

## 7. 케이스 추가·수정 절차

1. **식을 먼저 정합니다.** "기준 시각이 언제든 이 문장은 무엇이어야 하는가"를 식으로 씁니다. 파서 출력을 보고 베끼지 않습니다.
2. 추가 전에 식과 파서를 비교해 봅니다.
   ```bash
   uv run python scripts/gold.py show "다음 금요일" --expect "next(FRI)" --now 2026-10-02T09:00
   ```
3. 추가합니다. `gold.py add`는 식을 대표 기준 시각 4개(평상시, 월말 밤, 연말, 윤일)에서 계산해 파서와 비교하고, 다르면 거부합니다. 파서를 고치기 전에 실패 케이스부터 넣을 때(TDD)는 `--allow-mismatch`를 붙입니다.
   ```bash
   uv run python scripts/gold.py add --category weekday_modifier --text "다음 금요일" --expect "next(FRI)"
   ```
4. `uv run python scripts/check.py`를 실행합니다. 실패하면 리포트의 기준 시각에서 파서와 식 중 어느 쪽이 틀렸는지 판단하고, `scripts/evaluate.py --now <그 시각>`으로 재현합니다.
   - 파서가 틀렸으면 파서를 고칩니다 (TDD: 케이스가 먼저 실패해야 합니다).
   - 정책을 바꾸기로 했으면 식을 바꾸고 [5.2](#52-파서-정책과의-대응)도 고칩니다.
5. 달력 경계가 걸린 변경이면 `scripts/check.py --full`(전체 스윕 포함)을 실행합니다.
6. 식 평가기(`expectation.py`)를 고쳤다면, 앵커 대조 테스트(`test_expressions_agree_with_hand_computed_anchor`)가 통과하는지 확인합니다.

앵커 파일(`temporal_anchor.jsonl`)은 식 평가기를 검증하는 손계산 값이라 자주 바꾸지 않습니다. 새 식 함수를 추가할 때만 해당 문장의 손계산 값을 함께 넣습니다.

---

## 8. 자주 하는 실수

| 실수 | 증상 | 올바른 식 |
|---|---|---|
| 생략형 날짜에 `future` 빠뜨림 | 기준일이 그 날짜 이후면 실패 | `md(6, 3)` → `future(md(6, 3))` |
| 명시형에 `future` 붙임 | "이번달 15일"이 다음 달로 감 | `month(0).day(15)` |
| 모호한 시각에 `at` | 오전 기준 시각에서 실패 | "3시"는 `nearest(3:00)`, "오후 3시"는 `future(at(15:00))` |
| 범위 끝을 `.to()`로 | 끝이 시작보다 앞섬 | 생략형 끝은 `.to_after()` |
| `.to_after()`에 상대 표현 | "내일부터 모레까지"가 사흘 뒤까지로 늘어남 | 상대 표현 끝은 `.to()` |
| 요일을 소문자로 | `ExpectationError` | `FRI` |
| 오프셋에 단위 빠뜨림 (`today + 1`) | `ExpectationError` | `today + 1d` (공백은 선택) |
| grain이 안 맞는 메서드 | `.weekday()은(는) week 구간에만…` | `week(0).weekday(MON)` |

---

## 9. 문법 (참고)

```
expr     := chain (("+" | "-") OFFSET)*
chain    := atom ("." IDENT "(" args ")")*
atom     := "(" expr ")" | IDENT [ "(" args ")" ]
args     := [ arg ("," arg)* ]
arg      := TIME | ["+" | "-"] INT | WORD | expr
OFFSET   := INT ("d" | "w" | "mo" | "y" | "h" | "min" | "s")      예: 3d, 90min
TIME     := H:MM | HH:MM                                           예: 3:00, 25:00
WORD     := MON..SUN | early | mid | late                          (기본 값 이름이 아닌 식별자)
```

오류는 모두 `ExpectationError`(ValueError 하위)로 알리며, 정답셋을 읽을 때는 `파일:줄번호`가 붙습니다.
