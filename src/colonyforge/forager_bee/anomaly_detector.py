"""Forager Bee: 違和感検知

シナリオ実行結果を分析し、異常パターンを検出する。
Guard Beeに渡すverdictを判定する。
"""

from __future__ import annotations

from typing import Any

from .models import (
    AnomalyType,
    ForagerVerdict,
    ScenarioResult,
)

# 重大な異常タイプ（ANOMALY_DETECTEDに分類）
_CRITICAL_ANOMALY_TYPES = {
    AnomalyType.RESPONSE_DIFF,
    AnomalyType.SIDE_EFFECT,
    AnomalyType.PERFORMANCE_REGRESSION,
    AnomalyType.PAST_RUN_DIFF,
}

# 軽微な異常タイプ（SUSPICIOUSに分類）
_WARNING_ANOMALY_TYPES = {
    AnomalyType.LOG_ANOMALY,
}


class AnomalyDetector:
    """違和感検知器

    ScenarioResultのリストを分析し、ForagerVerdictと
    異常リストを返す。
    """

    def analyze(self, results: list[ScenarioResult]) -> tuple[ForagerVerdict, list[dict[str, Any]]]:
        """シナリオ結果を分析して判定

        Args:
            results: シナリオ実行結果のリスト

        Returns:
            (verdict, anomalies) のタプル
        """
        all_anomalies: list[dict[str, Any]] = []
        has_critical = False
        has_warning = False

        for result in results:
            # テスト失敗は即異常
            if not result.passed:
                has_critical = True

            # 個別のanomalyを収集
            for anomaly in result.anomalies:
                all_anomalies.append(anomaly)
                anomaly_type = anomaly.get("type")

                if isinstance(anomaly_type, AnomalyType):
                    if anomaly_type in _CRITICAL_ANOMALY_TYPES:
                        has_critical = True
                    elif anomaly_type in _WARNING_ANOMALY_TYPES:
                        has_warning = True
                else:
                    # 不明な異常タイプは警告扱い
                    has_warning = True

        if has_critical:
            return ForagerVerdict.ANOMALY_DETECTED, all_anomalies
        elif has_warning:
            return ForagerVerdict.SUSPICIOUS, all_anomalies
        else:
            return ForagerVerdict.CLEAR, all_anomalies
