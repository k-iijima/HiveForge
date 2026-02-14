"""Sentinel Hornet イベント生成

アラートから永続化可能なイベントオブジェクトを生成する。
"""

from __future__ import annotations

from typing import Any

from ..core.events import (
    ColonySuspendedEvent,
    SentinelAlertRaisedEvent,
    SentinelKpiDegradationEvent,
    SentinelQuarantineEvent,
    SentinelReportEvent,
    SentinelRollbackEvent,
)
from .alerts import SentinelAlert


class EventFactoryMixin:
    """イベント生成メソッドを提供するMixin

    SentinelHornet に mix-in される。
    """

    def create_alert_event(self, alert: SentinelAlert) -> SentinelAlertRaisedEvent:
        """SentinelAlertからsentinel.alert_raisedイベントを生成

        Args:
            alert: 発行するアラート

        Returns:
            ARに永続化可能なイベント
        """
        return SentinelAlertRaisedEvent(
            payload={
                "alert_type": alert.alert_type,
                "colony_id": alert.colony_id,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
            },
        )

    def create_suspension_event(self, alert: SentinelAlert) -> ColonySuspendedEvent:
        """SentinelAlertからcolony.suspendedイベントを生成

        Args:
            alert: 停止原因のアラート

        Returns:
            Colony一時停止イベント
        """
        return ColonySuspendedEvent(
            payload={
                "colony_id": alert.colony_id,
                "reason": alert.message,
                "alert_type": alert.alert_type,
            },
        )

    def create_report_event(
        self,
        *,
        colony_id: str,
        summary: str,
        alerts_count: int,
    ) -> SentinelReportEvent:
        """監視レポートイベントを生成

        Args:
            colony_id: 対象Colony ID
            summary: レポートサマリー
            alerts_count: 発行されたアラート数

        Returns:
            Sentinelレポートイベント
        """
        return SentinelReportEvent(
            payload={
                "colony_id": colony_id,
                "summary": summary,
                "alerts_count": alerts_count,
            },
        )

    def create_rollback_event(
        self,
        alert: SentinelAlert,
        rollback_to: str,
    ) -> SentinelRollbackEvent:
        """ロールバックイベントを生成

        Args:
            alert: ロールバック原因のアラート
            rollback_to: ロールバック先のRun ID等

        Returns:
            ロールバックイベント
        """
        return SentinelRollbackEvent(
            payload={
                "colony_id": alert.colony_id,
                "rollback_to": rollback_to,
                "reason": alert.message,
                "alert_type": alert.alert_type,
                "details": alert.details,
            },
        )

    def create_quarantine_event(
        self,
        alert: SentinelAlert,
        quarantine_scope: str,
        target_id: str | None = None,
    ) -> SentinelQuarantineEvent:
        """隔離イベントを生成

        Args:
            alert: 隔離原因のアラート
            quarantine_scope: 隔離スコープ（"colony" or "task"）
            target_id: 隔離対象ID（task scopeの場合）

        Returns:
            隔離イベント
        """
        payload: dict[str, Any] = {
            "colony_id": alert.colony_id,
            "scope": quarantine_scope,
            "reason": alert.message,
            "alert_type": alert.alert_type,
            "details": alert.details,
        }
        if target_id:
            payload["target_id"] = target_id

        return SentinelQuarantineEvent(
            payload=payload,
        )

    def create_kpi_degradation_event(self, alert: SentinelAlert) -> SentinelKpiDegradationEvent:
        """KPI劣化イベントを生成

        Args:
            alert: KPI劣化アラート

        Returns:
            KPI劣化イベント
        """
        return SentinelKpiDegradationEvent(
            payload={
                "colony_id": alert.colony_id,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
            },
        )
