"""Sentinel Hornet 異常検出ロジック

イベントストリームを分析し、ループ・暴走・コスト超過・セキュリティ違反を検出する。
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from ..core.events import BaseEvent, EventType
from ..core.models.action_class import ActionClass, TrustLevel, classify_action
from .alerts import SentinelAlert


class DetectionMixin:
    """異常検出メソッドを提供するMixin

    SentinelHornet に mix-in される。
    属性 max_event_rate, rate_window_seconds, max_loop_count,
    max_cost, kpi_drop_threshold を利用する。
    """

    max_event_rate: int
    rate_window_seconds: int
    max_loop_count: int
    max_cost: float
    kpi_drop_threshold: float

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
    # 無限ループ検出
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
            type_sequence: list[EventType] = [e.type for e in events]  # type: ignore[misc]
            alerts.extend(self._detect_type_cycle(type_sequence, colony_id))

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
    # 暴走検出
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
        recent_count = sum(1 for e in events if e.timestamp >= window_start)

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
    # コスト超過検出
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
    # セキュリティ違反検出
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
    # KPI劣化検出
    # ------------------------------------------------------------------

    def check_kpi_degradation(
        self,
        *,
        colony_id: str,
        previous_kpi: dict[str, float],
        current_kpi: dict[str, float],
    ) -> list[SentinelAlert]:
        """KPI劣化を検出

        前回と現在のKPIを比較し、閾値を超える劣化があればアラートを発行。

        下降が悪化を意味する指標 (correctness等):
            drop_ratio = (previous - current) / previous > threshold

        上昇が悪化を意味する指標 (incident_rate等):
            rise_ratio = (current - previous) / (1 - previous) > threshold
            ※ previous が小さいほど上昇の影響が大きい

        Args:
            colony_id: 対象Colony ID
            previous_kpi: 前回のKPI値
            current_kpi: 現在のKPI値

        Returns:
            検出されたアラート
        """
        alerts: list[SentinelAlert] = []

        # 下降 = 悪化の指標
        drop_metrics = {"correctness", "repeatability"}
        # 上昇 = 悪化の指標
        rise_metrics = {"incident_rate", "recurrence_rate"}

        for metric in drop_metrics:
            prev = previous_kpi.get(metric)
            curr = current_kpi.get(metric)
            if prev is None or curr is None or prev <= 0:
                continue

            drop_ratio = (prev - curr) / prev
            if drop_ratio > self.kpi_drop_threshold:
                alerts.append(
                    SentinelAlert(
                        alert_type="kpi_degradation",
                        colony_id=colony_id,
                        severity="warning" if drop_ratio < 0.5 else "critical",
                        details={
                            "metric": metric,
                            "previous": prev,
                            "current": curr,
                            "drop_ratio": round(drop_ratio, 4),
                        },
                        message=(
                            f"KPI '{metric}' dropped from {prev:.2f} to {curr:.2f} "
                            f"({drop_ratio:.0%} degradation)"
                        ),
                    )
                )

        for metric in rise_metrics:
            prev = previous_kpi.get(metric)
            curr = current_kpi.get(metric)
            if prev is None or curr is None:
                continue

            # absolute changeでの判定
            change = curr - prev
            if change > self.kpi_drop_threshold:
                alerts.append(
                    SentinelAlert(
                        alert_type="kpi_degradation",
                        colony_id=colony_id,
                        severity="warning" if change < 0.5 else "critical",
                        details={
                            "metric": metric,
                            "previous": prev,
                            "current": curr,
                            "change": round(change, 4),
                        },
                        message=(
                            f"KPI '{metric}' spiked from {prev:.2f} to {curr:.2f} "
                            f"(+{change:.2f} increase)"
                        ),
                    )
                )

        return alerts
