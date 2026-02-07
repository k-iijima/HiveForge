"""Sentinel Hornet 監視モジュール

Hive内のColonyを監視し、以下の異常を検出する:
- 無限ループ（タスク完了/失敗パターンの周期性）
- 暴走（イベント発行レート閾値超過）
- コスト超過（トークン/APIコール累積超過）
- セキュリティ違反（ActionClass×TrustLevelポリシーチェック）

検出時はsentinel.alert_raisedイベントを発行し、
criticalな場合はcolony.suspendedイベントでColonyを強制停止する。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.events import BaseEvent, EventType
from ..core.models.action_class import ActionClass, TrustLevel, classify_action


@dataclass
class SentinelAlert:
    """Sentinel Hornetが発行するアラート"""

    alert_type: str  # loop_detected, runaway_detected, cost_exceeded, security_violation
    colony_id: str
    severity: str  # warning, critical
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class SentinelHornet:
    """Hive内監視エージェント

    Colonyのイベントストリームを分析し、異常パターンを検出する。
    ステートレス設計: check_events()にイベント列を渡して結果を得る。

    Attributes:
        max_event_rate: レートウィンドウ内の最大イベント数
        rate_window_seconds: レートを計測するウィンドウ（秒）
        max_loop_count: ループと判定する最小繰り返し回数
        max_cost: 最大コスト（ドル）
    """

    def __init__(
        self,
        *,
        max_event_rate: int = 50,
        rate_window_seconds: int = 60,
        max_loop_count: int = 5,
        max_cost: float = 100.0,
    ):
        self.max_event_rate = max_event_rate
        self.rate_window_seconds = rate_window_seconds
        self.max_loop_count = max_loop_count
        self.max_cost = max_cost

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SentinelHornet:
        """設定辞書からSentinelHornetを構築

        Args:
            config: 設定辞書。未指定キーはデフォルト値を使用。

        Returns:
            構築されたSentinelHornetインスタンス
        """
        return cls(
            max_event_rate=config.get("max_event_rate", 50),
            rate_window_seconds=config.get("rate_window_seconds", 60),
            max_loop_count=config.get("max_loop_count", 5),
            max_cost=config.get("max_cost", 100.0),
        )

    def check_events(
        self,
        events: list[BaseEvent],
        *,
        colony_id: str,
    ) -> list[SentinelAlert]:
        """イベント列を分析し、異常パターンを検出

        Args:
            events: 分析対象のイベント列
            colony_id: 対象ColonyのID

        Returns:
            検出されたアラートのリスト（空の場合は異常なし）
        """
        alerts: list[SentinelAlert] = []

        alerts.extend(self._check_loops(events, colony_id))
        alerts.extend(self._check_runaway(events, colony_id))
        alerts.extend(self._check_cost(events, colony_id))
        alerts.extend(self._check_security(events, colony_id))

        return alerts

    # ------------------------------------------------------------------
    # 無限ループ検出 (M2-0-b)
    # ------------------------------------------------------------------

    def _check_loops(
        self,
        events: list[BaseEvent],
        colony_id: str,
    ) -> list[SentinelAlert]:
        """タスク単位のループパターンを検出

        同一task_idで同じイベント型パターンが繰り返されていないかチェック。
        また、イベント型列の周期性もチェックする。
        """
        alerts: list[SentinelAlert] = []

        # 1. タスク単位のリトライループ検出
        task_fail_counts: Counter[str] = Counter()
        for event in events:
            task_id = event.payload.get("task_id", "")
            if not task_id:
                continue
            if event.type in (EventType.TASK_FAILED, EventType.COLONY_FAILED):
                task_fail_counts[task_id] += 1

        for task_id, count in task_fail_counts.items():
            if count >= self.max_loop_count:
                alerts.append(
                    SentinelAlert(
                        alert_type="loop_detected",
                        colony_id=colony_id,
                        severity="critical",
                        details={"task_id": task_id, "fail_count": count},
                        message=f"Task {task_id} failed {count} times (threshold: {self.max_loop_count})",
                    )
                )

        # 2. イベント型パターンの周期性検出（A→B→A→B...）
        if len(events) >= self.max_loop_count * 2:
            type_sequence = [e.type for e in events]
            alerts.extend(
                self._detect_type_cycle(type_sequence, colony_id)
            )

        return alerts

    def _detect_type_cycle(
        self,
        type_sequence: list[EventType],
        colony_id: str,
    ) -> list[SentinelAlert]:
        """イベント型列の2-element周期パターンを検出"""
        alerts: list[SentinelAlert] = []

        # 直近 max_loop_count*2 個のイベント型を取得
        window_size = self.max_loop_count * 2
        if len(type_sequence) < window_size:
            return alerts

        recent = type_sequence[-window_size:]

        # 2つの状態が交互に出現するパターン検出
        unique_types = set(recent)
        if len(unique_types) == 2:
            even_types = set(recent[0::2])
            odd_types = set(recent[1::2])
            if len(even_types) == 1 and len(odd_types) == 1:
                alerts.append(
                    SentinelAlert(
                        alert_type="loop_detected",
                        colony_id=colony_id,
                        severity="critical",
                        details={
                            "pattern": [t.value for t in list(unique_types)],
                            "cycle_length": 2,
                            "repetitions": self.max_loop_count,
                        },
                        message=f"Cyclic event pattern detected: {[t.value for t in list(unique_types)]}",
                    )
                )

        return alerts

    # ------------------------------------------------------------------
    # 暴走検出 (M2-0-c)
    # ------------------------------------------------------------------

    def _check_runaway(
        self,
        events: list[BaseEvent],
        colony_id: str,
    ) -> list[SentinelAlert]:
        """イベント発行レートが閾値を超えていないかチェック"""
        alerts: list[SentinelAlert] = []

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=self.rate_window_seconds)

        # ウィンドウ内のイベントをカウント
        recent_count = sum(
            1 for e in events if e.timestamp >= window_start
        )

        if recent_count > self.max_event_rate:
            alerts.append(
                SentinelAlert(
                    alert_type="runaway_detected",
                    colony_id=colony_id,
                    severity="critical",
                    details={
                        "event_rate": recent_count,
                        "threshold": self.max_event_rate,
                        "window_seconds": self.rate_window_seconds,
                    },
                    message=(
                        f"Event rate {recent_count} exceeds threshold "
                        f"{self.max_event_rate} in {self.rate_window_seconds}s window"
                    ),
                )
            )

        return alerts

    # ------------------------------------------------------------------
    # コスト超過検出 (M2-0-d)
    # ------------------------------------------------------------------

    def _check_cost(
        self,
        events: list[BaseEvent],
        colony_id: str,
    ) -> list[SentinelAlert]:
        """LLM使用コストが閾値を超えていないかチェック"""
        alerts: list[SentinelAlert] = []

        total_cost = 0.0
        total_tokens = 0

        for event in events:
            if event.type == EventType.LLM_RESPONSE:
                total_cost += event.payload.get("cost", 0.0)
                total_tokens += event.payload.get("tokens_used", 0)

        if total_cost > self.max_cost:
            alerts.append(
                SentinelAlert(
                    alert_type="cost_exceeded",
                    colony_id=colony_id,
                    severity="critical",
                    details={
                        "total_cost": total_cost,
                        "total_tokens": total_tokens,
                        "threshold": self.max_cost,
                    },
                    message=f"Total cost ${total_cost:.2f} exceeds threshold ${self.max_cost:.2f}",
                )
            )

        return alerts

    # ------------------------------------------------------------------
    # セキュリティ違反検出 (M2-0-e)
    # ------------------------------------------------------------------

    def _check_security(
        self,
        events: list[BaseEvent],
        colony_id: str,
    ) -> list[SentinelAlert]:
        """ActionClass×TrustLevelポリシー違反を検出"""
        alerts: list[SentinelAlert] = []

        for event in events:
            if event.type != EventType.WORKER_STARTED:
                continue

            tool_name = event.payload.get("tool_name", "")
            if not tool_name:
                continue

            # ペイロードからActionClassを取得（明示されていなければclassifyで判定）
            action_class_str = event.payload.get("action_class", "")
            if action_class_str:
                try:
                    action_class = ActionClass(action_class_str)
                except ValueError:
                    action_class = classify_action(tool_name, event.payload)
            else:
                action_class = classify_action(tool_name, event.payload)

            # READ_ONLYは常に安全
            if action_class == ActionClass.READ_ONLY:
                continue

            # 確認なしのIRREVERSIBLE操作は違反
            trust_level_val = event.payload.get("trust_level", 1)
            confirmed = event.payload.get("confirmed", False)

            if action_class == ActionClass.IRREVERSIBLE and not confirmed:
                try:
                    trust_level = TrustLevel(trust_level_val)
                except ValueError:
                    trust_level = TrustLevel.REPORT_ONLY

                alerts.append(
                    SentinelAlert(
                        alert_type="security_violation",
                        colony_id=colony_id,
                        severity="critical",
                        details={
                            "tool_name": tool_name,
                            "action_class": action_class.value,
                            "trust_level": trust_level.value,
                            "confirmed": confirmed,
                        },
                        message=(
                            f"Unconfirmed irreversible action: {tool_name} "
                            f"(trust_level={trust_level.value})"
                        ),
                    )
                )

        return alerts

    # ------------------------------------------------------------------
    # イベント生成 (M2-0-f)
    # ------------------------------------------------------------------

    def create_alert_event(self, alert: SentinelAlert) -> BaseEvent:
        """SentinelAlertからsentinel.alert_raisedイベントを生成

        Args:
            alert: 発行するアラート

        Returns:
            ARに永続化可能なBaseEvent
        """
        return BaseEvent(
            type=EventType.SENTINEL_ALERT_RAISED,
            payload={
                "alert_type": alert.alert_type,
                "colony_id": alert.colony_id,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
            },
        )

    def create_suspension_event(self, alert: SentinelAlert) -> BaseEvent:
        """SentinelAlertからcolony.suspendedイベントを生成

        Args:
            alert: 停止原因のアラート

        Returns:
            Colony一時停止イベント
        """
        return BaseEvent(
            type=EventType.COLONY_SUSPENDED,
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
    ) -> BaseEvent:
        """監視レポートイベントを生成

        Args:
            colony_id: 対象Colony ID
            summary: レポートサマリー
            alerts_count: 発行されたアラート数

        Returns:
            Sentinelレポートイベント
        """
        return BaseEvent(
            type=EventType.SENTINEL_REPORT,
            payload={
                "colony_id": colony_id,
                "summary": summary,
                "alerts_count": alerts_count,
            },
        )
