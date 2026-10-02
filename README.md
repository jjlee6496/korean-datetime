# korean-datetime

[![CI](https://github.com/jjlee6496/korean-datetime/actions/workflows/ci.yml/badge.svg)](https://github.com/jjlee6496/korean-datetime/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/korean-datetime)](https://pypi.org/project/korean-datetime/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Korean natural-language date & time parser** — extracts temporal expressions from Korean text
("다음주 월요일 저녁 7시", "추석 연휴", "3시부터 5시까지") and resolves them to datetime ranges with granularity and ambiguity flags.
Zero dependencies, Python 3.10+.

한국어 문장에서 **날짜·시간·기간 표현**을 찾아 `[start, end)` datetime 구간으로 바꾸는 파서입니다. 상대 날짜, 오전/오후 추정, 음력 명절, 범위를 다루고, 추정한 부분은 모호성으로 표시합니다. **표준 라이브러리만 사용합니다** (Python 3.10+).

## 왜 만들었나요?

에이전트에서 정확한 날짜·시간 처리는 생각보다 중요합니다. “다음주 화요일 3시”나 “이번 주말”을 어떻게 해석하느냐에 따라 도구에 전달하는 값과 실행 결과가 달라집니다.

하지만 기존 도구만으로는 한국어 표현과 생략된 날짜·시간을 원하는 방식으로 다루기 어려웠고, 프로젝트마다 비슷한 보정 로직을 작성하게 됐습니다. `korean-datetime`은 이 처리를 재사용 가능한 코드로 만들기 위해 시작했습니다.

## 설치

PyPI에서 uv 또는 pip로 설치할 수 있습니다.

```bash
uv add korean-datetime
# 또는
pip install korean-datetime
```

- "다음주 월요일 저녁 7시 반", "추석 연휴", "3시부터 5시까지", "2시간 30분 후", "지난 3일간"
- 모호하게 추정한 부분은 값과 함께 표시 (오전/오후, 연도 넘김 등)
- 기준 시각에 상관없이 돌아가는 식 기반 정답셋으로 정량 평가

### 외부 데이터에서의 성능

AIHub Training의 유형별 표본 **327개 시간 표현**과 **시간 표현이 없는 200개 문장**을 같은 기준 시각으로 비교했습니다. 2026-10-02 같은 Linux arm64 환경에서 네 항목을 재측정한 결과이며, 전체 한국어 문장에 대한 정확도 보장은 아닙니다.

| 지표 | korean-datetime default | korean-datetime nearest | Duckling | dateparser |
|---|---:|---:|---:|---:|
| 값까지 정답 (미검출 포함) | 76.5% | 82.3% | 72.2% | 7.6% |
| 위치 검출률 | 94.5% | 94.5% | 98.2% | 19.3% |
| 비시간 문장 오탐률 ↓ | 2.5% | 2.5% | 12.5% | 5.5% |

네 항목을 같은 조건으로 재측정했습니다. `nearest`는 뉴스처럼 생략된 날짜를 가까운 과거로 해석할 수 있는 별도 설정이며 기본값과 분리했습니다. Duckling은 더 많이 검출하고 korean-datetime은 이 표본에서 오탐이 더 적었습니다. **검출 범위와 오탐 사이의 선택**으로 봐 주세요. [유형별 결과·비교 방법·실패 사례](docs/comparison.md)

전체 Training의 기본 설정 결과는 다음과 같습니다. 여기서 값 정확도는 **인식한 표현 중 값이 맞은 비율**로, 위 표의 미검출까지 포함한 비율과 분모가 다릅니다.

| 분야 | 재현율 | 정밀도 | 값 정확도 |
|---|---:|---:|---:|
| 뉴스 | 0.765 | 0.938 | 0.841 |
| 대화 | 0.679 | 0.961 | 0.918 |
| 역사 | 0.662 | 0.968 | 0.864 |

[Training/Validation 전체 결과와 옵션별 차이](docs/benchmark.md). 내부 정답셋의 회귀 성적과 외부 데이터 성능은 구분합니다.

처음이라면 **[튜토리얼](docs/tutorial.md)**부터 보세요. 상황별 문제와 해결, 실제 결과값을 예시로 정리했습니다.

```python
from datetime import datetime
from korean_datetime import parse, parse_all

now = datetime(2026, 9, 28, 14, 30)  # 월요일

r = parse("다음주 월요일 저녁 7시 반에 보자", now=now)
r.start, r.kind, r.grain, r.text
# (datetime(2026, 10, 5, 19, 30), Kind.DATETIME, Grain.MINUTE, '다음주 월요일 저녁 7시 반')

[x.text for x in parse_all("내일 3시에 보고 모레 5시에 또 보자", now=now)]
# ['내일 3시', '모레 5시']
```

## 설치 / 개발

개발 버전은 `pip install git+https://github.com/jjlee6496/korean-datetime`으로 설치합니다. [버전 정책과 배포 절차](docs/releasing.md)를 참고하세요.

```bash
uv sync                          # 개발 의존성(pytest, ruff, mypy) 포함
uv run python scripts/check.py   # 커밋 전 전체 검사 (ruff, mypy, 정답셋, pytest)
uv run pytest                    # 테스트 + 정량 평가 리포트만
```

## 스크립트 (`scripts/`)

모든 스크립트는 `--help`를 지원하고 `tests/test_scripts.py`에서 실제로 실행해 검증합니다.

| 스크립트 | 용도 | 예 |
|---|---|---|
| `check.py` | ruff → ruff format → mypy(strict) → 정답셋 검사 → pytest. 끝까지 실행하고 요약 | `check.py --full` (전체 스윕 포함) |
| `gold.py check` | 정답셋 형식·중복·식 오류·문서 누락 검사 | `gold.py check` |
| `gold.py add` | 식을 여러 기준 시각에서 계산해 파서와 비교한 뒤 추가. 다르면 거부 (TDD로 먼저 넣을 땐 `--allow-mismatch`) | `gold.py add --category weekday --text "다음 금요일" --expect "next(FRI)"` |
| `gold.py show` | 한 문장의 파서 값과 식 값을 기준 시각별로 비교 | `gold.py show "3시" --now 2026-09-28T23:50` |
| `evaluate.py` | 원하는 기준 시각·기간으로 정답셋 리포트 (실패 재현) | `evaluate.py --from 2026-12-25 --to 2027-01-05 --at 23:50` |
| `vendor.py` | 설치 없이 복사 + 매니페스트, 복사본 수정 여부 검사 | `vendor.py myapp/_vendor`, `vendor.py --check myapp/_vendor/korean_datetime` |
| `aihub_eval.py` | AI허브 시간 표현 탐지 데이터(TIMEX3)로 실제 문장 평가. 데이터는 저장소에 넣지 않음 | `aihub_eval.py <라벨링데이터 폴더> --samples 20` |
| `aihub_benchmark.py` | 옵션별 × Training/Validation 전체 표를 마크다운으로 (`docs/benchmark.md`) | `aihub_benchmark.py <데이터 루트> > docs/benchmark.md` |
| `compare_libraries.py` | default·nearest·Duckling·dateparser의 HTTP 기반 비교 리포트. native 측정은 [재현 절차](docs/benchmarks/2026-10-02-native/README.md) 참고 | `uv run --with dateparser python scripts/compare_libraries.py --aihub <데이터 루트>` |

일회성 작업(데이터 한 번 변환 등)은 저장소에 넣지 않고, 반복해서 쓰는 작업만 `scripts/`에 둡니다.

## 결과 모델

모든 결과는 반열린 구간 `[start, end)`와 정밀도(`grain`)로 표현합니다.

| 입력 | kind | grain | start ~ end |
|---|---|---|---|
| 내일 | date | day | 09-29 00:00 ~ 09-30 00:00 |
| 이번 주말 | date | day | 10-03 ~ 10-05 |
| 다음달 | date | month | 10-01 ~ 11-01 |
| 저녁 7시 | time | hour | 19:00 ~ 20:00 |
| 저녁 | time | hour | 18:00 ~ 21:00 |
| 내일 3시 | datetime | hour | 09-29 15:00 ~ 16:00 |
| 1시간 후 | datetime | minute | 15:30 ~ 15:31 |
| 3시부터 5시까지 | time | hour | 15:00 ~ 17:00 (`is_range=True`) |

- `value`: kind에 맞는 대표값 (`date` / `time` / `datetime`)
- `span`, `text`: 원문 위치와 문자열
- `ambiguities`: 추정이 들어간 부분 (값은 그대로). 호출하는 쪽이 보고 되물을지 정합니다
  ```python
  parse("6월 3일", now=now).ambiguities   # (Ambiguity.CYCLE_SHIFTED,)  올해는 지나서 내년으로 정함
  parse("다음 주말", now=now).ambiguities  # (Ambiguity.NEXT_WEEKEND,)
  parse("내일", now=now).ambiguities       # ()
  ```
  종류: `meridiem`, `noon_or_midnight`, `cycle_shifted`, `same_weekday`, `day_attribution`, `multi_day_time`, `calendar_row_spill`, `next_weekend`, `two_digit_year` ([자세히](docs/expectation-dsl.md#56-모호성-표시)). 오전/오후 표시는 기준 시각과 상관없이 문장만 보고 정해짐
- `to_dict()`: JSON 직렬화용 dict
- 편의 함수: `parse_date`, `parse_time`, `parse_datetime`

## 기준 시각 (`now`)

"내일", "3시", "1시간 후"는 기준 시각에서 계산합니다. 기준 시각은 다음 순서로 정해집니다.

| 순위 | 방법 | 쓰는 곳 |
|---|---|---|
| 1 | `parse(text, now=...)` | 특정 시각 기준으로 계산할 때 (테스트, 재처리) |
| 2 | `with reference_time(...):` | **요청 단위**: 미들웨어에서 한 번 정하면 그 요청 안의 모든 호출이 같은 기준을 씀 |
| 3 | `ParseOptions(timezone=...)` | 둘 다 없을 때 서버 시각을 그 시간대로 읽음 |
| 4 | (없음) | 서버 로컬 시각 `datetime.now()` |

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from korean_datetime import ParseOptions, TemporalParser, parse_time, reference_time

KST = ZoneInfo("Asia/Seoul")  # Windows에서는 pip install tzdata 필요

# 웹 서버: 요청마다 기준 시각을 한 번 정함 (ContextVar라 스레드·비동기 요청끼리 섞이지 않음)
@app.middleware("http")
async def set_request_time(request, call_next):
    with reference_time(datetime.now(KST)):
        return await call_next(request)

# 핸들러 안에서는 now 없이 호출해도 요청 시각 기준
parse_time("3시")

# 기준 시각을 따로 정하지 않는 곳(배치 등)에서는 시간대만 고정
parser = TemporalParser(ParseOptions(timezone=KST))
```

서버가 UTC라면 시간대를 꼭 정해야 합니다. 정하지 않으면 한국 시각 00:00~09:00에는 "오늘", "내일"이 하루 어긋납니다.
요청 단위로 정해 두면 한 요청 안에서 여러 번 호출해도 자정이나 분이 넘어갈 때 결과가 흔들리지 않습니다.

## 해석 규칙과 옵션

```python
from korean_datetime import AmbiguousHour, Cycle, ParseOptions, TemporalParser

parser = TemporalParser(ParseOptions(cycle=Cycle.NEAREST, ambiguous_hour=AmbiguousHour.PM))
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `cycle` | `FUTURE` | 연/월/날짜가 생략된 표현("15일", "6월 3일", "금요일", "추석")의 주기. `FUTURE`: 지났으면 다음 주기("15일"@20일 → 다음 달, "오전 10시"@14시 → 내일) / `PAST`: 오늘 포함 가장 최근 / `NEAREST`: 이전·이번·다음 중 가장 가까운 것 / `CURRENT`: 넘기지 않음. "올해", "이번달"처럼 명시하거나 "지난", "오는"이 붙으면 그쪽을 따름 |
| `ambiguous_hour` | `NEAREST_FUTURE` | 오전/오후 없는 1~12시. 날짜가 없거나 오늘이면 기준 시각 이후 가장 가까운 시각("3시"@14:30 → 15:00, "2시"@14:30 → 내일 02:00), 다른 날이면 `DAYTIME` 규칙. 그 외 `DAYTIME`, `PM`, `AS_IS`, `CONTEXT`(같은 텍스트의 앞 시각·시간대 말로 정함: "오후 6시에 끝나고 8시 영화" → 20시. AI허브 대화 오전/오후 일치율 0.753, `DAYTIME` 0.681, [벤치마크](docs/benchmark.md)) |
| `daytime_start` | `7` | `DAYTIME` 규칙에서 오전으로 볼 최소 시각 (7 → 7~11시 오전, 1~6시 오후) |
| `timezone` | `None` | 기준 시각이 없을 때 서버 시각을 읽을 시간대 |
| `compact_dates` | `False` | 구분자 없는 `1015`, `261015`를 날짜로 인식 (오탐이 많아 기본 꺼짐) |
| `vague` | `False` | "최근", "요즘", "향후" 같은 막연한 때를 `Kind.VAGUE`로 인식. 값은 기준일, 방향은 `direction`(recent/past/future). 어휘는 `temporal/lexicon.py`의 `VAGUE_WORDS` 표 하나에서 넣고 뺌. AI허브 뉴스 재현율 0.765 → 0.808, 정밀도 0.938 → 0.928 ([벤치마크](docs/benchmark.md)) |

### 용도별 권장 설정

생략된 연·월·날짜를 어느 쪽 주기로 볼지는 글의 성격에 따라 다릅니다. 기본값은 약속·예약처럼 **앞으로 할 일**을 말하는 대화에 맞춰져 있습니다.

| 용도 | 설정 | 이유 |
|---|---|---|
| 채팅·예약·일정 요청 (기본) | `ParseOptions()` (`cycle=FUTURE`) | "15일에 보자", "3시"는 대부분 앞으로의 일 |
| 뉴스·보도자료 | `ParseOptions(cycle=Cycle.NEAREST)` | 지난 일과 앞으로의 일정이 섞임. AI허브 뉴스 값 정확도 0.841 → **0.908** |
| 일지·회고·완료 보고 | `ParseOptions(cycle=Cycle.PAST)` | 거의 전부 지난 일일 때만 ("15일에 다녀왔다") |
| 옛 글 다시 처리 | 위 설정 + `now=작성 시각` | "오늘", "지난주"는 글을 쓴 시각 기준이어야 함 |

```python
from korean_datetime import Cycle, ParseOptions, TemporalParser

news = TemporalParser(ParseOptions(cycle=Cycle.NEAREST))
news.parse("29일 첫 신청을 받았다", now=datetime(2021, 11, 1)).start   # 2021-10-29 (3일 전이 28일 뒤보다 가까움)
news.parse("15일부터 접수한다", now=datetime(2021, 11, 1)).start       # 2021-11-15 (14일 뒤가 17일 전보다 가까움)
```

AI허브 뉴스(Training)에서 `cycle`별 값 정확도: `FUTURE` 0.841, `PAST` 0.860, `CURRENT` 0.904, `NEAREST` 0.908 ([벤치마크](docs/benchmark.md)).
뉴스를 "과거 우선"으로 처리하면 오히려 손해입니다. "3월부터 등교 권고", "19일부터 예약"처럼 앞으로의 일정 기사가 많기 때문입니다.

그 밖의 규칙:
- 시간대가 있으면 우선: "밤 1시" → 다음 날 01:00, "밤 12시" → 다음 날 00:00, "자정" → 그날 24:00
- 24시간제/시각 표기는 그대로: "13시", "05:00", "3pm"
- 요일만 있으면 오늘을 제외한 다음 그 요일 ("금요일"@금요일 → 다음 주)
- 주차는 **달력 줄 기준**: 1일이 든 월~일 줄이 첫째 주, 말일이 든 줄이 마지막 주 ("셋째 주 토요일" = 달력 셋째 줄의 토요일, 앞뒤 달 날짜일 수 있음. 첫 줄의 앞 달 칸이 이미 지난 날이면 +1주)
- "셋째 토요일", "마지막 금요일", "셋째 주말"처럼 **주 없이** 쓰면 그 달의 N번째 요일
- 존재하지 않는 날짜("2월 30일", "2026-02-30", "13월", "25시", "32일")는 인식하지 않음. 단 연/월이 생략됐으면 그 날짜가 있는 다음 주기로 ("31일"@9월 → 10월 31일, "2월 29일"@2026 → 2028년)
- "지난 금요일" → 오늘 이전 가장 가까운 금요일, "이번 금요일" → 이번 주 금요일, "지난 추석" → 가장 최근 추석, "지난 저녁" → 어제 저녁
- "지난 3일" → 오늘 이전 가장 최근의 3일 / "지난 3일간", "지난 3일 동안" → 3일 전부터 어제까지 (`is_range=True`, 주·개월·년도 같음)
- "17시 5분 전"처럼 시각 뒤 오프셋은 **적용한 결과**가 미래가 되도록 (16:57에 말하면 내일 16:55)
- "다가오는", "오는", "매월·매달·매년·매주"가 붙으면 오늘 날짜라도 **시각이 지났으면** 다음 주기 ("다가오는 31일 오전 9시"@1월 31일 09:01 → 3월 31일). 붙지 않으면 날짜 단위로만 판단 ("31일 오전 9시"@같은 시각 → 오늘 09:00). 반복(매월)은 다음 한 번만 돌려줌
- "오늘로부터 한 달 후", "내일부터 3일 뒤"의 `부터`는 범위가 아니라 기준점. 단 `까지`가 붙으면 범위이고 끝은 **시작 기준** ("3시부터 30분 뒤까지" = 15:00~15:30, "오후 5시 5분 전부터 두 시간 후까지" = 16:55~18:55)
- "A부터 그다음 월요일까지"의 월요일은 A 뒤에서 찾음
- 앞 날짜의 전날/다음 날: "다음 주 화요일의 전날", "추석 다음날", "이번 주말 전날"(= 금요일). "그다음 날"처럼 날짜 없이 쓰면 같은 문장의 바로 앞 표현을 이어받음 ("다음 주 화요일과 그다음 날 오전 9시" → 화요일, 수요일 9시). 이어받을 표현이 없으면 인식하지 않음
- 정정 "A가 아니라 B"는 B만 돌려주고, B에 빠진 정보는 A에서 이어받음 ("내일 3시가 아니라 5시" → 내일 5시)
- 연 + N번째 요일/주: 1~4번째는 1월, 끝에서 1~4번째는 12월 ("올해 마지막 금요일", "내년 첫 월요일", "내년 마지막 주 금요일"). "올해 다섯째 금요일"처럼 달을 정할 수 없으면 인식하지 않음
- 월 뒤의 "N일 이후/이전/전/후"는 날짜 ("11월 9일 이후" = 11월 9일, "9일 후"가 아님). "지난 12월", "오는 3월"은 가장 가까운 지난/다가올 12월·3월
- 목록 "A과 B", "A 및 B"도 선택지처럼 B가 A의 빠진 정보를 이어받음 ("지난해 11월과 12월" → 둘 다 지난해)
- 동형어는 인식하지 않음: "전달"(전달하다), "공시", "한시 지원"(한시적), "S22 시리즈", "임상 2/3상", "낼 수"(내다), "차주의"(借主)·"금주를"(禁酒). "곧", "당장", "즉시"는 시각 앞에서만 ("곧 3시")
- **문맥이 필요한 표현은 인식하지 않음**: "그날", "그다음 주", "그해", "거기서 세 시간", "그 전날"처럼 앞 문장·대화의 때를 가리키는 말, "영업일"처럼 회사·기관 달력이 필요한 단위. 틀린 값을 내는 것보다 비워 두는 쪽을 택함. 인용문 속 "내일"은 호출하는 쪽이 그 글의 작성 시각을 `now`로 넘겨야 함
- 선택지 "A 아니면/또는/이나 B"는 결과를 각각 돌려주고, B에 빠진 정보는 A에서 이어받음 ("다음주 월요일 아니면 화요일" → 다음주 화요일, "내일 오후 3시 아니면 5시" → 내일 17시)
- 시간대 이름("뉴욕 시간")은 해석하지 않고 기준 시각의 시간대로 계산함. 시간대 변환은 호출하는 쪽에서
- 기간으로 쓰인 숫자는 날짜로 보지 않음 ("3일간", "7일 이내", "30분 동안")
- 범위 "A부터 B까지"에서 B의 생략된 연/월은 A 기준으로 해석하고, 뒤집힌 범위("10월 5일부터 10월 3일까지")는 합치지 않음
- 설날·추석 등 음력 명절은 천문 계산으로 변환 (`lunar_to_solar`, 1900~2100년, KST 기준)

## 지원 표현

| 분류 | 예 |
|---|---|
| 상대 일 | 오늘, 내일, 모레, 글피, 그글피, 어제, 그저께, 그끄저께, 명일, 익일, 작일 |
| 기간 전후 | 3일 뒤, 이틀 후, 보름 뒤, 일주일 후, 2주 후, 한 달 뒤, 3개월 후, 1년 후, 크리스마스 3일 전 |
| 주/요일 | 지난 금요일, 이번주 금요일, 다음주 월요일, 다다음주, 저번주, 차주, 주말, 다음 주말, 주중, 다음주초, 목욜 |
| 월/일 | 10월 15일, 시월 십오일, 4월달 14일, 15일, 다음달 1일, 이번달 말일, 월말, 다음달 초, 중순 |
| 주차 | 다음달 첫째주 금요일, 마지막주 일요일, 12월 둘째주, 10월 셋째주 주말, 2주차 |
| 연 | 올해, 내년, 2027년, 상반기, 하반기, 연말, 내년 1분기 |
| 형식 | 2026-10-01, 2026.10.1, 20261101, 25.07.15, 10/15, 07-15, 2026-10-05T14:00, 10월 5일(월) 오후 2시 |
| 시각 | 3시, 세시 반, 열한시 십오분, 15:30, 오후 3시, 저녁 7시 반, 새벽 2시, 정오, 자정, 3pm |
| 시간대 | 새벽, 아침, 아침 일찍, 오전, 점심, 낮, 오후, 저녁, 퇴근하고, 해질녘, 밤, 심야 |
| 상대 시각 | 지금, 1시간 후, 30분 전, 2시간 30분 후, 한 시간 반 뒤, 10분 있다가, 17시 5분 전 |
| 기념일 | 신정, 설날, 설 연휴, 정월 대보름, 삼일절, 어린이날, 부처님 오신 날, 현충일, 광복절, 추석, 추석 연휴, 한글날, 크리스마스 이브 … |
| 범위 | 3시부터 5시까지, 오후 3시~5시, 3~5시, 내일부터 모레까지, 10월 3일부터 5일까지 |

### 반복형 상대 표현

반복되는 접두어는 표에 하나씩 적지 않고 규칙으로 선언합니다([`temporal/lexicon.py`](src/korean_datetime/temporal/lexicon.py)의 `RepeatRule`). 반복은 최대 4회까지 인식합니다.

| 규칙 | 예 |
|---|---|
| 다음·담 앞에 "다" | 다음주(+1), 다다음주(+2), 다다다음주(+3), 다담달(+2) |
| 저번·지난·전 앞에 같은 글자 | 저저번주(-2), 지지지난달(-3), 전전주(-2), 전전전주(-3) |
| 후년 앞에 "후", 작년 앞에 "재" | 후년(+2), 후후년(+3) / 재작년(-2), 재재작년(-3) |
| 제·저께 앞 "그·끄" 음절 수 | 그제(-2), 그끄제·그그제(-3), 그그그제(-4) |
| 글피 앞에 "그" | 글피(+3), 그글피(+4), 그그글피(+5) |

한자어 표현: 금일·당일·명일·익일·명후일·익익일·작일·전일, 금주·차주·내주·익주, 금월·당월·익월·전월·전전월·내달, 금년·명년·익년·작년·전년.
`전주`(지명), `거년`(옛말)은 넣지 않았습니다.

### 기념일·공휴일 데이터 주입

내장 기념일은 [`temporal/data/holidays.json`](src/korean_datetime/temporal/data/holidays.json)(양력/음력, 연휴 기간, 다른 기념일 기준 오프셋)에 항목을 추가하면 됩니다.
대체공휴일·임시공휴일처럼 정책으로 정해지는 날은 계산할 수 없으므로, **외부 데이터를 주입**합니다. 외부 라이브러리는 의존성이 아닙니다.

```python
import holidays  # 예: python-holidays. {date: 이름} 매핑이면 무엇이든 가능
from korean_datetime import BuiltinHolidays, ChainedHolidays, DateTableHolidays, ParseOptions, parse

external = DateTableHolidays(holidays.KR(years=range(2025, 2031), language="ko"),
                             aliases={"창립기념일": ["회사 생일"]})
options = ParseOptions(holidays=ChainedHolidays(external, BuiltinHolidays()))  # 주입 데이터 우선, 없으면 내장
parse("추석 대체 휴일", options=options)  # python-holidays의 이름 형식
```

- `DateTableHolidays`: `{date: name}` 매핑이나 `(date, name)` 목록을 받습니다. 연속된 날짜는 하나의 기간이 됩니다.
- `ChainedHolidays`: 앞 달력이 우선이고, 그해 데이터가 없으면 다음 달력을 봅니다.
- 직접 구현하려면 `HolidayCalendar` 프로토콜(`names`, `span_names`, `span`)만 만족하면 됩니다.
- "쉬는 날인지" 판단 같은 공휴일 정책 API는 보류 상태입니다.

어휘(상대 표현, 시간대, 방향어 등)는 `temporal/lexicon.py`의 표를 고치면 됩니다.

## 회귀 테스트 / 내부 정답셋

이 지표는 **지원하도록 정의한 표현의 회귀 검사**용입니다. `TOTAL = 1.000`은 내부 정답셋을 통과했다는 뜻이며, 한국어 문장 전반에서 정확도 100%라는 뜻이 아닙니다. 실제 문장 성능은 아래 [AIHub benchmark](#벤치마크-실제-문장)를 참고하세요.

정답은 **기준 시각에서 계산하는 식**으로 정의합니다. 그래서 같은 정답셋을 어떤 날짜·시각으로도 돌릴 수 있습니다.

```json
{"category": "weekday",   "text": "금요일",               "expect": "next(FRI)"}
{"category": "month_day", "text": "6월 3일",              "expect": "future(md(6, 3))"}
{"category": "datetime",  "text": "다음주 월요일 저녁 7시", "expect": "week(1).weekday(MON).at(19:00)"}
{"category": "range",     "text": "3시부터 5시까지",       "expect": "nearest(3:00).to_after(nearest(5:00))"}
{"category": "negative",  "text": "오일 교환하러 가",       "expect": "none"}
```

식의 **모든 타입·함수·메서드·규칙과 정답셋 관리 절차**는 [`docs/expectation-dsl.md`](docs/expectation-dsl.md)에 정리되어 있습니다.
식 평가기는 파서와 같은 실수를 하지 않도록 파서 코드를 쓰지 않고 표준 `calendar`만으로 구현했습니다(음력만 공유).

| 파일 | 내용 |
|---|---|
| `tests/data/temporal_gold.jsonl` | 기대값 식 정답셋 611건, 22개 카테고리 (인식하지 않아야 하는 케이스 100건 포함) |
| `tests/data/temporal_anchor.jsonl` | **손으로 계산한 절대값** 485건, 기준 시각 56개(평상시 2026-09-28 14:30, 연말 2027-12-31 23:10, 윤일 2028-02-29 08:05, 월말·주말·자정 직전·직후 경계 사례). 식 평가기 자체를 검증하는 용도 |

| 실행 | 기준 시각 | 검사 건수 |
|---|---|---|
| `uv run pytest` | **고정 목록 292개**: 5일 간격, 월초·월말·윤일, 하루 중 8개 시각, KST 시간대 12개 | 약 18만 |
| (위와 함께) | **실행 시점의 실제 현재 시각** 1개 — 별도 스모크 테스트 | 611 |
| `uv run pytest -m slow` | 2026~2027 매일, 주 1회 하루 중 8개 시각, 경계일, KST (1,584개) | 약 97만 |

테스트 요약에 두 가지 리포트가 나오고, 임계값(`tests/test_evaluation.py`)에 못 미치면 실패합니다.

```
category                n  precision  recall     f1  value_acc  accuracy
clock               13432      1.000   1.000  1.000      1.000     1.000
...
TOTAL              178412      1.000   1.000  1.000      1.000     1.000

ambiguity                tp    fp    fn  precision  recall
meridiem               5840     0     0      1.000   1.000
...
TOTAL                 31822     0     0      1.000   1.000
```

- **값 지표**: precision / recall(인식 여부), `value_acc`(인식한 것 중 값까지 맞은 비율), accuracy(전체)
- **모호성 지표**: 종류별로 모호성 표시가 기대와 같은지. 기대 모호성은 식이 기준 시각마다 계산한 것과 정답셋의 `ambiguous`를 합친 것

그 외 테스트:
- `test_invariants.py`: 기준일 730일 각각에서 "내일 = 기준+1", "지난 금요일은 기준 이전 7일 안의 금요일" 같은 규칙 위반이 0건인지 검증
- `test_holidays.py`: 음력 변환을 한국천문연구원 역서 날짜(2019~2026년 설날·추석·부처님 오신 날)로 검증
- `test_docs.py`: DSL 문서가 코드·정답셋과 맞는지 (모든 함수·메서드·카테고리가 문서에 있는지, 문서의 식 예시가 실행되는지)
- `test_vendoring.py`: 설치 없이 다른 이름으로 복사해도 동작하는지
- 전체: 테스트 493개(기본 492 + 전체 스윕 1), `ruff`·`mypy --strict` 통과

## 벤치마크 (실제 문장)

위 정답셋은 직접 만든 것이라 회귀 방지용입니다. 실제 성능은 외부 데이터로 잽니다.

데이터 출처: AI허브(한국지능정보사회진흥원) [「시간 표현 탐지 데이터」](https://aihub.or.kr). 데이터는 이 저장소에 포함하지 않습니다.

**전체 표: [docs/benchmark.md](docs/benchmark.md)** (옵션별 × Training/Validation × 뉴스/대화/역사)

### 다른 라이브러리와 비교

2026-10-02, 같은 Linux arm64 컨테이너에서 AIHub Training 표본 327개 시간 표현과 비시간 문장 200개로 비교했습니다. `default`와 `nearest`를 모두 정확도·검출률·오탐률·속도에서 별도 항목으로 측정했습니다.

| 지표 | korean-datetime default | korean-datetime nearest | Duckling | dateparser |
|---|---:|---:|---:|---:|
| 값까지 정답 (미검출 포함) | 76.5% | 82.3% | 72.2% | 7.6% |
| 위치 검출률 | 94.5% | 94.5% | 98.2% | 19.3% |
| 비시간 문장 오탐률 ↓ | 2.5% | 2.5% | 12.5% | 5.5% |
| 직접 파싱·결과 생성 중앙값 | 0.163ms | 0.173ms | 0.218ms | 0.199ms |

속도는 HTTP 없이 527건 전체 예열 후 5회 반복한 값입니다. Duckling의 HTTP 호출은 별도로 중앙값 **0.450ms**였습니다. 기존 3~7ms는 통신·빌드·아키텍처 조건이 달라 이 직접 호출 시간으로 대체했습니다. 라이브러리별 결과 구조와 미검출 비율도 달라 순수 핵심 알고리즘 비용으로 해석하지 않습니다.

`nearest`는 외부 표본에서 값 정답률이 높았지만, 기본 해석 정책을 기준으로 만든 자체 정답셋에서는 `default` 100%, `nearest` 93.2%였습니다. 용도에 맞는 설정을 선택해야 합니다. [유형별 결과·p95·설정·재현 방법](docs/comparison.md)

기본 설정, Training(뉴스 98,545 · 대화 91,876 · 역사 26,330개 표현):

| 분야 | 재현율 | 정밀도 | 값 정확도 |
|---|---:|---:|---:|
| 뉴스 | 0.765 | 0.938 | 0.841 |
| 대화 | 0.679 | 0.961 | 0.918 |
| 역사 | 0.662 | 0.968 | 0.864 |

옵션을 바꿨을 때 가장 크게 달라지는 것 (Training):

| 옵션 | 지표 | 기본값 | 바꾼 값 | 언제 |
|---|---|---:|---:|---|
| `cycle=NEAREST` | 뉴스 값 정확도 | 0.841 | **0.908** | 뉴스·보도자료 |
| `ambiguous_hour=CONTEXT` | 대화 오전/오후 일치율 (695건) | 0.485 | **0.753** | 대화 기록·로그 (실시간 아님) |
| `vague=True` | 대화 재현율 / 정밀도 | 0.679 / 0.961 | **0.747** / 0.955 | "최근", "향후"도 필요할 때 |

재현율이 낮은 건 대부분 이 라이브러리가 기본으로 다루지 않는 표현 때문입니다. "최근", "요즘"(대화 정답의 74%), "가을", "19세기", 문맥 지시("이날", "그때")가 그렇습니다.
날짜·시각이 정해진 표현만 보면 재현율은 0.86~0.92입니다.

```bash
uv run python scripts/aihub_benchmark.py "<…>/01-1.정식개방데이터" > docs/benchmark.md   # 전체 표 다시 만들기
uv run python scripts/aihub_eval.py "<…>/Validation/02.라벨링데이터" --cycle nearest --samples 20   # 한 설정, 실패 예시
```

## 명령행

```bash
uv run korean-datetime "내일 저녁 7시" --now 2026-09-28T14:30
{"text": "내일 저녁 7시", "span": [0, 8], "kind": "datetime", "grain": "hour", ...}

uv run korean-datetime "내일 3시에 보고 모레 5시" --all --ambiguous-hour pm
```

## 구조

```
docs/
├── tutorial.md          # 상황별 사용법 (예시 결과는 tests/test_tutorial.py가 실제로 실행해 확인)
├── benchmark.md         # AI허브 데이터 옵션별 벤치마크 (scripts/aihub_benchmark.py가 생성)
├── comparison.md        # default·nearest·Duckling·dateparser 비교
├── benchmarks/          # native 측정 환경·재현 절차·기록
└── expectation-dsl.md   # 기대값 식(DSL) 전체 정리, 정답셋 관리 절차
src/korean_datetime/
├── core/            # 날짜/시간이 쓰는 기반: scanner(경계·조사), numerals(한글 수사), clock(기준 시각), types, evaluation
├── temporal/        # 날짜/시간
│   ├── rules.py         # 정규식 토큰 규칙          (scan)
│   ├── postprocess.py   # 기간 + 방향 병합          ("1시간 30분 후")
│   ├── frame.py         # 토큰 → 표현 슬롯 조립      (순위가 커지는 방향으로만)
│   ├── resolve*.py      # 슬롯 → 구간 해석
│   ├── ranges.py        # "A부터 B까지"
│   ├── ambiguity.py     # 모호성 종류
│   ├── relative.py      # 반복형 상대 표현 문법
│   ├── holiday_calendar.py  # 기념일 달력 (외부 데이터 주입 지점)
│   ├── lunar.py         # 음력 변환 (천문 계산)
│   ├── expectation.py   # 기대값 식 (기준 시각 무관 정답셋)
│   ├── lexicon.py, data/holidays.json   # 어휘·기념일 데이터
│   └── parser.py        # 공개 API
└── __main__.py      # 명령행
```

## 설치 없이 복사해서 쓰기 (vendoring)

외부 의존성이 없고 모든 import가 상대 경로라서, **`src/korean_datetime` 폴더를 통째로 복사**하면 됩니다. 이름과 위치는 자유입니다.

```bash
uv run python scripts/vendor.py <내 프로젝트>/myapp/_vendor              # 복사 + VENDORED.json(버전·파일 해시)
uv run python scripts/vendor.py --check <내 프로젝트>/myapp/_vendor/korean_datetime   # 복사본이 수정됐는지
```
```python
from myapp._vendor.korean_datetime import parse, reference_time
```

- **필요한 것**: Python 3.10 이상. `temporal/data/holidays.json`을 반드시 같이 복사해야 합니다(폴더째 복사하면 포함됨).
- **보장**: `tests/test_vendoring.py`가 설치된 패키지 없이(`python -S`) 다른 이름으로 복사한 사본을 실행해서 확인합니다. 패키지 이름을 절대 경로로 쓰는 코드가 들어오면 이 테스트가 실패합니다.
- **복사본은 고치지 않기**: 수정은 이 저장소에서 하고 `vendor.py`로 다시 복사합니다. 복사본이 수정돼 있으면 `vendor.py`가 덮어쓰기를 거부합니다(`--force` 필요). `VENDORED.json`이 없는 폴더는 `--force`로도 덮어쓰지 않습니다.
- **주의**: 설치본과 복사본을 한 프로세스에서 같이 쓰면 서로 다른 모듈입니다. 예를 들어 설치본의 `reference_time()`은 복사본에 적용되지 않습니다. 한 가지만 쓰세요.
- **빼도 되는 것** (런타임에 안 씀): `__main__.py`(CLI), `temporal/expectation.py`·`temporal/evaluation.py`·`core/evaluation.py`(정답셋 평가 도구). 약 1,000줄이지만 `__init__.py`의 import도 함께 정리해야 해서, 보통은 통째로 복사하는 쪽이 간단합니다.

## 1.0.0 변경 사항 (0.1.0 대비)

API를 새로 설계했습니다. 기존 `DateNormalizer`/`TimeNormalizer`, `extract_and_normalize`, `time_range`/`reference_type`, `PatternNormalizer`/`Rule`, `fixed_now`는 제거되었습니다.
구 코드에 있던 주요 오류("12월25일" → 2월 25일, "다음달 15일" → 이번 달, "05:00" → 날짜 5일·17시, "열한시 십오분" → 23:10, "24시" 예외, 설날/추석 미지원)는 재설계로 해결되었습니다.

## 라이선스

[MIT](LICENSE). 벤치마크에 쓴 AI허브 데이터는 포함하지 않으며, 그 이용 조건은 AI허브를 따릅니다.
