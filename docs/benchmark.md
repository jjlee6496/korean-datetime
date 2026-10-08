# 벤치마크: 옵션별 실제 문장 평가

데이터 출처: AI허브(한국지능정보사회진흥원) [「시간 표현 탐지 데이터」](https://aihub.or.kr).
데이터는 이 저장소에 포함하지 않습니다.

korean-datetime 1.0.0, 2026-10-08 측정. `uv run python scripts/aihub_benchmark.py <데이터 루트> > docs/benchmark.md`로 다시 만듭니다.
옵션은 하나씩만 바꾸고 나머지는 기본값입니다.
평가 방식은 `scripts/aihub_eval.py` 머리말에 있습니다.
Validation은 규칙을 다듬을 때 오류를 본 데이터라,
처음 보는 데이터인 **Training 수치가 실제 성능에 가깝습니다**.

라이브러리 간 표본 비교와 속도는 [별도 비교 문서](comparison.md)에 있습니다.

## 데이터 규모 (DATE·TIME 정답 표현 수)

| 분야 | Training 정답 수 | Validation 정답 수 |
|---|---:|---:|
| 뉴스 | 98,545 | 12,245 |
| 대화 | 91,876 | 11,717 |
| 역사 | 26,330 | 3,203 |

## 기본 설정

검출(재현율·정밀도)은 위치가 겹치면 맞은 것.
값 정확도는 문서 작성 시각을 기준 시각으로 놓고 정답 값의 정해진 부분을 비교.

재현율

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `default` | 0.781 | 0.780 | 0.699 | 0.696 | 0.721 | 0.736 |

정밀도

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `default` | 0.938 | 0.938 | 0.968 | 0.962 | 0.969 | 0.974 |

값 정확도

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `default` | 0.839 | 0.842 | 0.916 | 0.903 | 0.864 | 0.868 |

각 표에서 가장 좋은 값은 굵게 표시합니다.

## `cycle`: 생략된 연·월·날짜의 주기 → 값 정확도

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `cycle=future` | 0.839 | 0.842 | **0.916** | **0.903** | **0.864** | 0.868 |
| `cycle=past` | 0.857 | 0.858 | 0.910 | 0.898 | 0.861 | **0.882** |
| `cycle=nearest` | **0.905** | **0.906** | **0.916** | **0.903** | 0.861 | **0.882** |
| `cycle=current` | 0.901 | 0.902 | **0.916** | **0.903** | 0.862 | 0.868 |

## `ambiguous_hour`: 오전/오후 없는 시각 → 오전/오후 일치율

정답에 시각이 있고 문장에 오전/오후가 없는 경우만 셉니다 (Training 뉴스 64건, 대화 695건 / Validation 뉴스 14건, 대화 107건).
건수가 적은 칸은 참고만 하세요.
데이터의 기준 시각은 발화 시각이 아니라 수집 시각이라,
실시간 대화용 기본값(`nearest_future`)에는 불리합니다.

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation |
|---|---:|---:|---:|---:|
| `ambiguous_hour=nearest_future` | 0.444 | **0.500** | 0.485 | 0.472 |
| `ambiguous_hour=daytime` | 0.469 | 0.143 | 0.681 | 0.636 |
| `ambiguous_hour=pm` | 0.537 | **0.500** | 0.631 | **0.745** |
| `ambiguous_hour=as_is` | 0.343 | 0.400 | 0.329 | 0.200 |
| `ambiguous_hour=context` | **0.703** | **0.500** | **0.753** | 0.720 |

## `vague`: '최근', '향후' 같은 막연한 때

재현율

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `default` | 0.781 | 0.780 | 0.699 | 0.696 | 0.721 | 0.736 |
| `vague=True` | **0.821** | **0.822** | **0.767** | **0.763** | **0.731** | **0.745** |

정밀도

| 설정 | 뉴스 Training | 뉴스 Validation | 대화 Training | 대화 Validation | 역사 Training | 역사 Validation |
|---|---:|---:|---:|---:|---:|---:|
| `default` | **0.938** | **0.938** | **0.968** | **0.962** | **0.969** | **0.974** |
| `vague=True` | 0.931 | 0.929 | 0.963 | 0.956 | 0.960 | 0.971 |

