"""테스트 실행 요약에 정량 평가 리포트(기대값 식 정답셋 × 표본 기준 시각)를 붙인다."""

from __future__ import annotations

import pytest


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    try:
        from references import sampled_ambiguity_report, sampled_references, sampled_report

        report = sampled_report()
        ambiguity = sampled_ambiguity_report()
        references = sampled_references()
    except Exception as error:  # 리포트 실패가 테스트 결과를 가리지 않도록 경고만 출력
        terminalreporter.write_line(f"[정량 평가] 리포트 생성 실패: {error!r}")
        return
    period = "2026-01-01 ~ 2028-02-29 고정 목록, KST 포함"
    terminalreporter.section(f"정량 평가: temporal_gold.jsonl × 기준 시각 {len(references)}개 ({period})")
    for line in report.format().splitlines():
        terminalreporter.write_line(line)
    terminalreporter.write_line("")
    for line in ambiguity.format().splitlines():
        terminalreporter.write_line(line)
