"""Forager Bee: Guard Bee連携レポーター

ForagerReportを生成し、Guard Beeに渡すEvidence形式に変換する。
"""

from __future__ import annotations

from typing import Any

from .anomaly_detector import AnomalyDetector
from .models import (
    ChangeImpactGraph,
    ForagerReport,
    ScenarioResult,
)


class ForagerReporter:
    """Guard Bee連携レポーター

    シナリオ結果からForagerReportを生成し、
    Guard BeeのEvidence形式に変換する。
    """

    def __init__(self) -> None:
        self._detector = AnomalyDetector()

    def create_report(
        self,
        run_id: str,
        colony_id: str,
        graph: ChangeImpactGraph,
        scenario_results: list[ScenarioResult],
    ) -> ForagerReport:
        """シナリオ結果からForagerReportを生成

        Args:
            run_id: Run ID
            colony_id: Colony ID
            graph: 変更影響グラフ
            scenario_results: シナリオ実行結果

        Returns:
            ForagerReport
        """
        # 異常検知
        verdict, anomalies = self._detector.analyze(scenario_results)

        return ForagerReport(
            run_id=run_id,
            colony_id=colony_id,
            changed_files=graph.changed_files,
            scenario_results=scenario_results,
            anomalies=anomalies,
            verdict=verdict,
        )

    def to_guard_bee_evidence(self, report: ForagerReport) -> dict[str, Any]:
        """ForagerReportをGuard BeeのEvidence形式に変換

        Guard Beeが理解できる辞書形式に変換する。
        """
        passed = sum(1 for r in report.scenario_results if r.passed)
        failed = len(report.scenario_results) - passed

        return {
            "evidence_type": "forager_report",
            "verdict": report.verdict.value,
            "total_scenarios": len(report.scenario_results),
            "passed_scenarios": passed,
            "failed_scenarios": failed,
            "anomaly_count": len(report.anomalies),
            "changed_files": report.changed_files,
        }
