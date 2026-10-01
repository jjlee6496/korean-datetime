# 튜토리얼: 문장 속 날짜·시간을 값으로 바꾸기

사용자는 "다음주 화요일 저녁 7시에 회의 잡아줘"라고 씁니다. 캘린더 API는 `2026-10-06T19:00`을 원합니다.
이 사이를 메우는 게 이 라이브러리가 하는 일입니다. 외부 의존성 없이 표준 라이브러리만 씁니다.

정규식 몇 줄로 시작하면 곧 이런 문제를 만납니다.

| 문제 | 예 | 이 라이브러리 |
|---|---|---|
| 상대 표현 | "다음주 화요일", "모레", "3일 뒤" | 기준 시각에서 계산 |
| 오전/오후가 없음 | "3시에 보자" | 가장 가까운 미래로 정하고 **모호하다고 표시** |
| 연도가 없음 | 9월에 "6월 3일" | 내년으로 넘기고 표시 (뉴스라면 다르게, [5절](#5-지난-날짜인데-내년이-나와요)) |
| 음력 명절 | "추석 연휴" | 천문 계산으로 양력 변환 |
| 비슷하게 생긴 말 | "메시지를 **전달**했다", "임상 **2/3**상" | 날짜로 보지 않음 |
| 앞 문장이 필요한 말 | "그날 3시", "그다음 주" | 틀린 값 대신 **빈 결과** |

모든 예시는 **2026년 10월 1일(목) 14:30**에 말했다고 가정합니다. 아래 코드 블록의 `# →` 오른쪽 값은
테스트(`tests/test_tutorial.py`)가 실제로 실행해서 확인하는 값입니다.

```python
from datetime import datetime
from korean_datetime import parse, parse_all

NOW = datetime(2026, 10, 1, 14, 30)
```

---

## 1. 첫 걸음: 문장 하나에서 값 하나

**상황**: 회의 요청 메시지에서 일시를 뽑아 캘린더에 넣고 싶습니다.

```python
r = parse("다음주 화요일 저녁 7시에 회의 잡아줘", now=NOW)
r.text    # → 다음주 화요일 저녁 7시
r.start   # → 2026-10-06 19:00:00
r.end     # → 2026-10-06 20:00:00
r.kind    # → Kind.DATETIME
r.grain   # → Grain.HOUR
```

결과는 항상 **구간 `[start, end)`**입니다. "7시"는 7시 정각 한 점이 아니라 7시대(19:00~20:00)이고, `grain`이 그 정밀도입니다.
날짜만 있으면 `kind`가 `DATE`, 시각만 있으면 `TIME`입니다.

```python
parse("내일", now=NOW).end                 # → 2026-10-03 00:00:00
parse("이번 주말", now=NOW).start          # → 2026-10-03 00:00:00
parse("이번 주말", now=NOW).end            # → 2026-10-05 00:00:00
parse("1시간 반 뒤에 알려줘", now=NOW).start  # → 2026-10-01 16:00:00
```

JSON으로 보내려면 `r.to_dict()`를 쓰면 됩니다.

## 2. 문장 안의 표현을 모두 찾기

**상황**: 긴 메시지에서 일시를 전부 찾아 하이라이트하고 싶습니다.

```python
found = parse_all("내일 3시에 보고 모레 5시에 또 보자", now=NOW)
[x.text for x in found]   # → ['내일 3시', '모레 5시']
found[1].span             # → (10, 15)
```

`span`은 원문에서의 위치(시작, 끝)입니다. `text[span[0]:span[1]]`이 `x.text`입니다.

## 3. "3시"는 오전일까 오후일까

**문제**: 14:30에 "3시에 보자"라고 했습니다. 새벽 3시일 리는 없지만, 시스템은 확신할 수 없습니다.

```python
r = parse("3시에 보자", now=NOW)
r.start          # → 2026-10-01 15:00:00
r.ambiguities    # → (<Ambiguity.MERIDIEM: 'meridiem'>,)
```

- **값**: 기준 시각 이후 가장 가까운 3시 = 오늘 15:00
- **표시**: `meridiem`, 즉 "오전/오후를 문장에서 알 수 없었다"

값을 그대로 쓸지, 사용자에게 되물을지는 서비스가 정합니다.

```python
if r.ambiguities:
    reply = f"{r.start:%H시} 맞나요?"   # "15시 맞나요?" 같은 확인 질문
```

이미 지난 시각이면 다음 날로 넘어가고, 넘어갔다는 표시(`cycle_shifted`)도 붙습니다.

```python
r = parse("2시에 보자", now=NOW)
r.start                                       # → 2026-10-02 02:00:00
[a.value for a in r.ambiguities]              # → ['meridiem', 'cycle_shifted']
parse("오후 3시에 보자", now=NOW).ambiguities  # → ()
```

다른 규칙이 맞는 서비스라면 바꿀 수 있습니다. 예를 들어 영화 예매처럼 항상 오후인 경우입니다.

```python
from korean_datetime import AmbiguousHour, ParseOptions

pm = ParseOptions(ambiguous_hour=AmbiguousHour.PM)
parse("내일 9시", now=NOW, options=pm).start   # → 2026-10-02 21:00:00
```

**대화 기록**처럼 실시간이 아닌 글이라면 "가장 가까운 미래"가 의미가 없습니다. 이때는 `CONTEXT`로 **같은 텍스트 안의 단서**를 씁니다.

```python
ctx = ParseOptions(ambiguous_hour=AmbiguousHour.CONTEXT)
[x.start.hour for x in parse_all("오후 6시에 끝나고 8시 영화 보자", now=NOW, options=ctx)]   # → [18, 20]
parse_all("어제 저녁 먹으러 8시쯤 갔어요", now=NOW, options=ctx)[-1].start                # → 2026-10-01 20:00:00
parse("8시에 보자", now=NOW, options=ctx).start                                         # → 2026-10-02 08:00:00
```

1. 앞에 오전/오후가 정해진 시각이 있으면 그 뒤로 이어지는 쪽 (오후 6시 다음의 8시 → 20시)
2. 없으면 가장 가까운 시간대 말 ("저녁" 근처의 8시 → 20시)
3. 둘 다 없으면 낮 시간 규칙 (7~11시 오전, 1~6시 오후)

AI허브 대화 데이터에서 오전/오후 일치율은 `CONTEXT` 0.753, `DAYTIME` 0.681, `PM` 0.631이었습니다(Training 695건, [벤치마크](benchmark.md)).
앞 대화의 시각은 쓰지 않습니다. 같은 입력이면 항상 같은 결과가 나오게 하려는 것입니다. 앞 턴까지 쓰고 싶다면 대화를 이어 붙여 한 번에 넘기세요.
값을 정해도 `meridiem` 표시는 남습니다.

## 4. 기준 시각: "내일"은 언제 기준인가

**문제 1: 서버가 UTC입니다.** 한국 시각 10월 1일 01:00(UTC 9월 30일 16:00)에 "내일"이라고 하면 10월 2일이어야 합니다.

```python
from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))
utc_now = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
parse("내일", now=utc_now).start                   # → 2026-10-01 00:00:00+00:00
parse("내일", now=utc_now.astimezone(KST)).start   # → 2026-10-02 00:00:00+09:00
```

첫 번째는 UTC 날짜 기준이라 하루가 어긋납니다. 기준 시각을 사용자 시간대로 넘기거나 `ParseOptions(timezone=KST)`를 쓰세요.

**문제 2: 요청마다 `now=`를 넘기기 번거롭습니다.** 웹 서버라면 미들웨어에서 한 번만 정합니다.

```python
from korean_datetime import reference_time

with reference_time(datetime(2026, 10, 1, 14, 30)):
    parse("내일").start        # → 2026-10-02 00:00:00
```

요청 단위(ContextVar)라 동시 요청끼리 섞이지 않고, 한 요청 안에서 자정이 넘어가도 결과가 흔들리지 않습니다.

**문제 3: 옛 메시지를 다시 처리합니다.** 사흘 전 메시지의 "내일"은 오늘 기준이 아니라 **메시지를 쓴 시각** 기준입니다.

```python
sent_at = datetime(2026, 9, 28, 23, 59)
parse("내일 오전 3시에 도착", now=sent_at).start   # → 2026-09-29 03:00:00
```

## 5. 지난 날짜인데 내년이 나와요

**문제**: 10월에 "6월 3일"이라고 하면 내년 6월 3일이 나옵니다.

```python
r = parse("6월 3일에 만나", now=NOW)
r.start                                # → 2027-06-03 00:00:00
[a.value for a in r.ambiguities]       # → ['cycle_shifted']
parse("올해 6월 3일", now=NOW).start    # → 2026-06-03 00:00:00
```

기본값은 **약속·예약**에 맞춰져 있어서, 연·월이 생략된 날짜가 이미 지났으면 다음 주기로 넘깁니다("만나자"는 앞으로의 일).
"올해"처럼 적혀 있으면 넘기지 않습니다. 하지만 **뉴스나 일지**는 대부분 이미 일어난 일이나 가까운 일정을 적습니다.
이때 `cycle`을 바꿉니다.

| `cycle` | 뜻 | 2021-11-01 기사의 "29일" | 맞는 곳 |
|---|---|---|---|
| `FUTURE` (기본) | 지났으면 다음 주기 | 11월 29일 | 채팅·예약 |
| `PAST` | 오늘 포함 가장 최근 | 10월 29일 | 일지·회고 |
| `NEAREST` | 이전·이번·다음 중 가장 가까운 것 | 10월 29일 | **뉴스** |
| `CURRENT` | 넘기지 않음 | 11월 29일 | 이번 주기로 고정 |

```python
from korean_datetime import Cycle

news = ParseOptions(cycle=Cycle.NEAREST)
article = datetime(2021, 11, 1)
parse("29일 첫 신청을 받았다", now=article, options=news).start   # → 2021-10-29 00:00:00
parse("15일부터 접수한다", now=article, options=news).start       # → 2021-11-15 00:00:00
```

AI허브 뉴스 데이터에서 값 정확도는 `FUTURE` 0.841, `PAST` 0.860, `NEAREST` **0.908**이었습니다([벤치마크](benchmark.md)).
뉴스에는 "15일부터 접수"처럼 앞으로의 일정도 많아서 무조건 과거로 보는 것보다 가까운 쪽이 낫습니다.
"지난 15일", "오는 15일"처럼 문장에 방향이 있으면 `cycle`과 상관없이 그쪽을 따릅니다.

## 6. 범위: "부터 ~ 까지"

```python
r = parse("3시부터 5시까지 회의", now=NOW)
(r.start, r.end, r.is_range)   # → (datetime.datetime(2026, 10, 1, 15, 0), datetime.datetime(2026, 10, 1, 17, 0), True)

r = parse("내일부터 3일 뒤까지 휴가", now=NOW)
(r.start.date(), r.end.date())   # → (datetime.date(2026, 10, 2), datetime.date(2026, 10, 6))
```

- 끝이 날짜면 **그날 포함**: "3일 뒤까지"는 10월 5일까지라서 `end`가 10월 6일 0시입니다.
- "부터 30분 뒤까지"의 30분은 지금이 아니라 **시작부터** 셉니다.
- "지난 3일간"은 3일 전부터 어제까지의 범위이고, "지난 3일"은 가장 최근의 3일(날짜)입니다.

```python
parse("지난 3일간 매출", now=NOW).is_range   # → True
parse("지난 3일 매출", now=NOW).start        # → 2026-09-03 00:00:00
```

## 7. 정정과 선택지

**상황**: 사용자가 말을 바꾸거나 후보를 여러 개 말합니다.

```python
[x.text for x in parse_all("내일 3시가 아니라 5시로 바꿔줘", now=NOW)]   # → ['5시']
parse("내일 3시가 아니라 5시로 바꿔줘", now=NOW).start                   # → 2026-10-02 17:00:00

pick = parse_all("다음주 월요일 아니면 화요일", now=NOW)
[x.start.date() for x in pick]   # → [datetime.date(2026, 10, 5), datetime.date(2026, 10, 6)]
```

- "A가 아니라 B"는 **B만** 돌려줍니다. 날짜(내일)는 A에서 이어받습니다.
- "A 아니면 B", "A과 B"는 둘 다 돌려주고, B에 빠진 정보(다음주)는 A에서 이어받습니다.

## 8. 앞 문장이 필요한 말은 비워 둡니다

**문제**: "그날 오후 3시에 보자"의 "그날"은 앞 대화에 있습니다. 오늘 15시로 계산하면 **그럴듯하게 틀린 값**이 됩니다.

```python
parse_all("그날 오후 3시에 보자", now=NOW)    # → []
parse_all("그다음 주 토요일에 마쳐", now=NOW)  # → []
parse_all("메시지를 전달했다", now=NOW)        # → []
parse_all("갤럭시 S22 시리즈", now=NOW)        # → []
```

빈 결과는 "시간 표현이 없다"가 아니라 "이 문장만으로는 계산하지 않았다"일 수 있습니다.
대화형 서비스라면 앞 턴에서 찾은 날짜를 기억해 두었다가, 빈 결과일 때 그 날짜로 해석하는 식으로 처리하세요.
같은 문장 안에서 이어지는 것은 라이브러리가 처리합니다.

```python
[x.start for x in parse_all("다음 주 화요일과 그다음 날 오전 9시에 만나자", now=NOW)]   # → [datetime.datetime(2026, 10, 6, 0, 0), datetime.datetime(2026, 10, 7, 9, 0)]
```

## 9. "최근", "향후" 같은 막연한 말 (선택)

검색 필터나 분석에서 "최근 매출"의 "최근"도 시간 정보로 쓰고 싶을 때 켭니다. 기본은 꺼져 있습니다.

```python
vague = ParseOptions(vague=True)
found = parse_all("최근 매출이 늘었고 향후 전망도 밝다", now=NOW, options=vague)
[(x.text, x.kind.value, x.direction.value) for x in found]   # → [('최근', 'vague', 'recent'), ('향후', 'vague', 'future')]
found[0].value   # → 2026-10-01
```

값은 기준일이고, 뜻은 `direction`(recent/past/future)에 있습니다. `kind`가 `VAGUE`이므로 정확한 날짜와 섞이지 않게 거를 수 있습니다.
어떤 말을 넣을지는 `temporal/lexicon.py`의 `VAGUE_WORDS` 표 하나에서 정합니다.
"곧", "당장", "앞으로"는 실제 문장에서 시간이 아닌 경우가 많아 빠져 있습니다.

## 10. 명절과 공휴일

```python
parse("추석 연휴에 고향 가요", now=NOW).start   # → 2027-09-14 00:00:00
parse("추석 연휴에 고향 가요", now=NOW).end     # → 2027-09-17 00:00:00
parse("설날", now=NOW).start                    # → 2027-02-07 00:00:00
```

올해 추석(9월 25일)은 지났으므로 내년 추석 연휴가 나옵니다. 음력은 천문 계산(1900~2100년)으로 바꿉니다.
대체공휴일이나 회사 창립기념일처럼 계산할 수 없는 날은 외부 달력을 넣습니다([README](../README.md#기념일공휴일-데이터-주입)).

## 11. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| "내일"이 하루 어긋남 | 서버 시각이 UTC | `now`를 사용자 시간대로, 또는 `ParseOptions(timezone=...)` ([4절](#4-기준-시각-내일은-언제-기준인가)) |
| 뉴스의 "29일"이 다음 달로 감 | 기본 `cycle=FUTURE` | `cycle=Cycle.NEAREST` ([5절](#5-지난-날짜인데-내년이-나와요)) |
| "3시"가 15시인데 03시였음 | 오전/오후 모호 | `ambiguities`의 `meridiem`을 보고 되묻기 ([3절](#3-3시는-오전일까-오후일까)) |
| "그날 3시"가 안 잡힘 | 앞 문맥 필요 | 앞 턴의 날짜로 직접 해석 ([8절](#8-앞-문장이-필요한-말은-비워-둡니다)) |
| "2월 30일"이 안 잡힘 | 없는 날짜 | 의도된 동작 (잘못된 날짜를 고쳐서 만들지 않음) |
| "최근"이 안 잡힘 | 기본 꺼짐 | `ParseOptions(vague=True)` ([9절](#9-최근-향후-같은-막연한-말-선택)) |
| 결과가 왜 이렇게 나왔는지 모르겠음 | — | `ambiguities`를 확인: 무엇을 추정했는지 들어 있음 |

추정이 들어간 경우를 정리하면 다음과 같습니다.

| 표시 | 뜻 | 예 |
|---|---|---|
| `meridiem` | 오전/오후를 문장에서 알 수 없음 | "3시" |
| `cycle_shifted` | 생략된 연/월/날짜를 다른 주기로 옮김 | 10월의 "6월 3일" → 내년 |
| `day_attribution` | 자정 근처라 어느 날에 속하는지 모호 | "내일 밤 12시" |
| `next_weekend` | "다음 주말"이 이번 주말일 수도 있음 | "다음 주말" |
| 그 밖 | `noon_or_midnight`, `same_weekday`, `multi_day_time`, `calendar_row_spill`, `two_digit_year` | [DSL 문서](expectation-dsl.md#56-모호성-표시) |
