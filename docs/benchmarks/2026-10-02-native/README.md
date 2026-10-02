# 2026-10-02 native 비교 실험

[비교 결과](../../comparison.md)는 `default`, `nearest`, Duckling, dateparser를 모두 다시 측정한 결과입니다. 앞서 실행한 default 전용 실험을 대체합니다.

- [summary.json](summary.json): 전체·유형별 점수, 자체 정답셋, 회차별/통합 시간.
- [manifest.json](manifest.json): 소스 버전, 설정, 환경, 측정 범위, 입력 SHA-256.
- [benchmark-evidence.zip](benchmark-evidence.zip): 입력 ID·회차·타이밍만 남긴 기록, 실행 코드, 설치 패키지 목록. AIHub 원문·정답·파서 응답은 제외했습니다.
- [실행 스크립트](../../../scripts/native_benchmark): 입력 준비, Python·HTTP 측정, Haskell 직접 호출, 채점과 기록 내보내기.

## 환경과 측정 범위

Apple M4 Pro 위 Docker Debian bookworm Linux aarch64, 12 vCPU·8GB RAM을 사용했습니다. native 아키텍처지만 Docker 가상화 환경이며 전용 벤치마크 머신은 아닙니다.
기반 이미지는 `debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251`입니다.

Duckling 소스는 `59a13ff87b1aa8be6b93d387244f8636b26185c5`, korean-datetime 소스는 `2715ec49c287234cea63f0d60e068fde8d43ebdb` (1.0.0)입니다. 파서 규칙은 수정하지 않았습니다. Python 3.11.2, dateparser 1.4.3, GHC 9.0.2를 사용했습니다. Haskell 의존성은 압축 파일의 `haskell-packages.txt`에 기록했으며, timezone-series 0.1.13과 timezone-olson 0.2.0은 소스로 빌드했습니다.

`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, 시간대 `Asia/Seoul`을 사용합니다. POSIX 로케일에서는 한국어 해석이 달라져 같은 실험이 되지 않습니다.

외부 표본 527건을 전체 예열 1회(`round=0`), 측정 5회(`round=1..5`) 실행합니다. 회차마다 `20261002 + round` 시드로 순서를 섞으며 모든 항목에 같은 요청 목록을 사용합니다. 실행 순서는 Duckling 직접 호출 → default → nearest → dateparser → Duckling HTTP이며 동시 실행하지 않았습니다.
자체 정답셋 607건은 각 실행 마지막에 `round=-1`로 한 번씩 채점하고 속도 통계에서 제외합니다.

`parse_ns`는 파싱과 JSON으로 변환 가능한 결과 객체 생성을 포함합니다. Python의 `to_dict`/날짜 문자열 생성, Duckling의 `force . toJSON`까지 측정합니다. `ns`는 JSON 바이트 생성까지 포함합니다. 요청 디코딩·기준 시각 준비·출력 I/O는 직접 호출 시간에서 제외합니다. HTTP의 `ns`는 urllib 요청부터 응답 JSON 디코딩까지이며 요청 본문 인코딩은 제외합니다.

## 재실행

AIHub 데이터는 별도로 준비해야 합니다. 아래 `/repo`는 이 저장소, `/work`는 Duckling 소스와 빌드 산출물, `/work/run`은 공개하지 않을 실험 입력·출력 디렉터리입니다. 비교할 Python과 Duckling을 같은 Linux arm64 컨테이너에 설치합니다. `/work/venv`에는 위 버전의 korean-datetime·dateparser와 압축 파일의 Python 패키지 버전을 설치합니다.

입력을 준비합니다. 데이터 읽기와 채점은 저장소가 있는 호스트에서 실행해도 되며, 시간 측정은 모두 같은 컨테이너에서 실행합니다.

```bash
cd /repo
uv run python scripts/native_benchmark/prepare.py \
  --aihub /data/01-1.정식개방데이터 --out /work/run
```

유형별 최대 50개(총 327개), 비시간 문장 200개를 추출 시드 `20261001`로 고릅니다. 원본 표본 SHA-256은 `c839ef13e678085320432faf421c16bf4d3fa54ae2c9737df74187e86f68365d`입니다. 원본 데이터에서 다시 추출한 `corpus.jsonl`, `curated.jsonl`, `requests.jsonl`이 측정 입력과 바이트 단위로 동일함을 확인했습니다.

위 버전의 GHC 의존성과 `/usr/share/zoneinfo`를 제공하는 tzdata를 설치하고, Duckling 소스를 지정 커밋으로 체크아웃합니다. `/work`에 timezone-series·timezone-olson 소스를 각각 디렉터리 이름 그대로 풉니다. 사용한 빌드 명령은 다음과 같습니다.

```bash
cd /work
ghc --make -O2 -threaded -rtsopts -XOverloadedStrings \
  -i/work -i/work/exe -i/work/timezone-series-0.1.13 -i/work/timezone-olson-0.2.0 \
  exe/ExampleMain.hs -main-is ExampleMain \
  -outputdir /work/native-build -o /work/duckling-native-http
ghc --make -O2 -threaded -rtsopts -XOverloadedStrings \
  -i/work -i/work/exe -i/work/timezone-series-0.1.13 -i/work/timezone-olson-0.2.0 \
  /repo/scripts/native_benchmark/NativeBench.hs \
  -outputdir /work/native-build -o /work/duckling-native-bench
```

Haskell 측정 코드는 결과의 지연 평가가 측정 구간 밖으로 빠지지 않도록 강제 평가하며, 측정 래퍼에 `-fno-full-laziness -fno-cse`를 사용합니다. HTTP 서버는 같은 컨테이너의 별도 셸에서 다음과 같이 실행합니다.

```bash
export LANG=C.UTF-8 LC_ALL=C.UTF-8
/work/duckling-native-http -p 8000 --no-access-log --no-error-log +RTS -N1 -RTS
```

빌드 완료 후 아래 명령을 순차 실행합니다. Python 3.11.2를 사용하는 `/work/venv`의 환경은 모든 Python 항목에서 같습니다.

```bash
export LANG=C.UTF-8 LC_ALL=C.UTF-8
/work/duckling-native-bench +RTS -N1 -RTS \
  < /work/run/requests.jsonl > /work/run/duckling-direct.jsonl
/work/venv/bin/python /repo/scripts/native_benchmark/bench_python.py korean-datetime /work/run
/work/venv/bin/python /repo/scripts/native_benchmark/bench_python.py korean-datetime-nearest /work/run
/work/venv/bin/python /repo/scripts/native_benchmark/bench_python.py dateparser /work/run
/work/venv/bin/python /repo/scripts/native_benchmark/bench_http.py /work/run
```

채점과 타이밍 집계를 실행합니다.

```bash
cd /repo
uv run python scripts/native_benchmark/analyze.py /work/run --out /work/results
```

분석기는 응답 누락·중복, 반복 실행의 값 변화, Duckling 직접/HTTP JSON 불일치가 있으면 실패합니다. 기존 `_score_aihub`, `_score_false_alarms`, `_score_curated`로 채점하고 예열·자체 정답셋을 제외한 2,635건의 시간만 집계합니다. p95는 정렬한 관측값의 `ceil(n × 0.95)`번째 값이며 처리량은 건수/누적 시간입니다.
이번 실행은 Duckling 직접/HTTP **3,769건 모두 동일**했고 모든 반복 예측이 일치했습니다.

`/work/results`의 집계·타이밍 파일만 공개할 수 있습니다. `/work/run`에는 AIHub 원문과 응답이 있으므로 이 저장소에 추가하지 않습니다. 기존 `compare_libraries.py`는 HTTP 기반 별도 리포트용이며 이 native 측정 문서를 자동 생성하는 명령이 아닙니다.
