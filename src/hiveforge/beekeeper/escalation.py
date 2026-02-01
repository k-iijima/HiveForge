"""Escalation（直訴）機能

Queen BeeがBeekeeperをバイパスしてユーザーに直接報告する機能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ulid import ULID


class EscalationType(str, Enum):
    """直訴のタイプ"""

    BEEKEEPER_CONFUSION = "beekeeper_confusion"  # Beekeeperが混乱している
    BEEKEEPER_TIMEOUT = "beekeeper_timeout"  # Beekeeperが応答しない
    CONTEXT_LOSS = "context_loss"  # コンテキストが失われた
    INSTRUCTION_CONFLICT = "instruction_conflict"  # 指示が矛盾している
    RESOURCE_CONCERN = "resource_concern"  # リソース（コスト/時間）の懸念
    CRITICAL_DECISION = "critical_decision"  # 重要な判断が必要
    BLOCKED = "blocked"  # 進行不能
    SECURITY_CONCERN = "security_concern"  # セキュリティ上の懸念


class EscalationSeverity(str, Enum):
    """直訴の重要度"""

    INFO = "info"  # 情報提供
    WARNING = "warning"  # 警告
    CRITICAL = "critical"  # 緊急


class EscalationStatus(str, Enum):
    """直訴のステータス"""

    PENDING = "pending"  # 未対応
    ACKNOWLEDGED = "acknowledged"  # 確認済み
    RESOLVED = "resolved"  # 解決済み
    DISMISSED = "dismissed"  # 却下


@dataclass
class Escalation:
    """直訴"""

    escalation_id: str = field(default_factory=lambda: str(ULID()))
    colony_id: str = ""
    queen_bee_id: str = ""
    escalation_type: EscalationType = EscalationType.BLOCKED
    severity: EscalationSeverity = EscalationSeverity.WARNING
    status: EscalationStatus = EscalationStatus.PENDING
    title: str = ""
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    suggested_actions: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None


@dataclass
class EscalationResponse:
    """直訴への応答"""

    escalation_id: str
    action: str  # acknowledge, resolve, dismiss
    comment: str = ""
    responded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EscalationManager:
    """直訴マネージャー

    Queen Beeからの直訴を管理し、ユーザーへの通知を調整する。
    """

    def __init__(self) -> None:
        self._escalations: dict[str, Escalation] = {}
        self._history: list[Escalation] = []
        self._notification_callback: Any = None

    def set_notification_callback(self, callback: Any) -> None:
        """通知コールバックを設定"""
        self._notification_callback = callback

    def create_escalation(
        self,
        colony_id: str,
        queen_bee_id: str,
        escalation_type: EscalationType,
        title: str,
        description: str,
        severity: EscalationSeverity = EscalationSeverity.WARNING,
        context: dict[str, Any] | None = None,
        suggested_actions: list[str] | None = None,
    ) -> Escalation:
        """直訴を作成

        Args:
            colony_id: 発信元Colony
            queen_bee_id: 発信元Queen Bee
            escalation_type: 直訴タイプ
            title: タイトル
            description: 詳細説明
            severity: 重要度
            context: コンテキスト情報
            suggested_actions: 推奨アクション

        Returns:
            作成された直訴
        """
        escalation = Escalation(
            colony_id=colony_id,
            queen_bee_id=queen_bee_id,
            escalation_type=escalation_type,
            severity=severity,
            title=title,
            description=description,
            context=context or {},
            suggested_actions=suggested_actions or [],
        )

        self._escalations[escalation.escalation_id] = escalation

        # 通知コールバックがあれば呼び出し
        if self._notification_callback:
            self._notification_callback(escalation)

        return escalation

    def acknowledge(self, escalation_id: str, comment: str = "") -> bool:
        """直訴を確認済みにする"""
        if escalation_id not in self._escalations:
            return False

        escalation = self._escalations[escalation_id]
        escalation.status = EscalationStatus.ACKNOWLEDGED
        escalation.acknowledged_at = datetime.now(timezone.utc)

        return True

    def resolve(self, escalation_id: str, resolution: str) -> bool:
        """直訴を解決済みにする"""
        if escalation_id not in self._escalations:
            return False

        escalation = self._escalations[escalation_id]
        escalation.status = EscalationStatus.RESOLVED
        escalation.resolved_at = datetime.now(timezone.utc)
        escalation.resolution = resolution

        # 履歴に移動
        self._history.append(escalation)
        del self._escalations[escalation_id]

        return True

    def dismiss(self, escalation_id: str, reason: str = "") -> bool:
        """直訴を却下する"""
        if escalation_id not in self._escalations:
            return False

        escalation = self._escalations[escalation_id]
        escalation.status = EscalationStatus.DISMISSED
        escalation.resolved_at = datetime.now(timezone.utc)
        escalation.resolution = f"Dismissed: {reason}" if reason else "Dismissed"

        # 履歴に移動
        self._history.append(escalation)
        del self._escalations[escalation_id]

        return True

    def get_escalation(self, escalation_id: str) -> Escalation | None:
        """直訴を取得"""
        return self._escalations.get(escalation_id)

    def get_pending_escalations(self) -> list[Escalation]:
        """未対応の直訴一覧"""
        return [e for e in self._escalations.values() if e.status == EscalationStatus.PENDING]

    def get_escalations_by_colony(self, colony_id: str) -> list[Escalation]:
        """Colony別の直訴一覧"""
        return [e for e in self._escalations.values() if e.colony_id == colony_id]

    def get_escalations_by_severity(self, severity: EscalationSeverity) -> list[Escalation]:
        """重要度別の直訴一覧"""
        return [e for e in self._escalations.values() if e.severity == severity]

    def get_history(self, limit: int = 100, colony_id: str | None = None) -> list[Escalation]:
        """直訴履歴を取得"""
        history = self._history
        if colony_id:
            history = [e for e in history if e.colony_id == colony_id]
        return history[-limit:]

    def get_critical_count(self) -> int:
        """未対応のCRITICAL直訴数"""
        return sum(
            1
            for e in self._escalations.values()
            if e.severity == EscalationSeverity.CRITICAL and e.status == EscalationStatus.PENDING
        )
