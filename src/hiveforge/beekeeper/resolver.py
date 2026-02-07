"""衝突解決プロトコル

検出された衝突を解決するためのストラテジーとリゾルバー。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ulid import ULID

from .conflict import Conflict, ConflictType


class ResolutionStrategy(str, Enum):
    """解決戦略"""

    FIRST_COME = "first_come"  # 先着優先
    PRIORITY_BASED = "priority_based"  # 優先度ベース
    MERGE = "merge"  # マージ
    MANUAL = "manual"  # 手動解決
    ABORT_ALL = "abort_all"  # 全キャンセル
    RETRY_LATER = "retry_later"  # 後でリトライ
    LOCK_AND_QUEUE = "lock_and_queue"  # ロック＆キュー


class ResolutionStatus(str, Enum):
    """解決ステータス"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    FAILED = "failed"
    ESCALATED = "escalated"  # 上位に委譲


@dataclass
class ResolutionResult:
    """解決結果"""

    resolution_id: str = field(default_factory=lambda: str(ULID()))
    conflict_id: str = ""
    strategy: ResolutionStrategy = ResolutionStrategy.MANUAL
    status: ResolutionStatus = ResolutionStatus.PENDING
    winner_colony_id: str | None = None
    message: str = ""
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MergeRule:
    """マージルール"""

    rule_id: str = field(default_factory=lambda: str(ULID()))
    resource_type: str = ""  # "file", "config", etc.
    merge_function: str = ""  # "append", "union", "custom"
    priority_field: str | None = None  # 優先度判定に使うフィールド
    description: str = ""


class ConflictResolver:
    """衝突解決器

    衝突を解決するための戦略を適用。
    """

    def __init__(self):
        self._strategies: dict[ConflictType, ResolutionStrategy] = {
            ConflictType.FILE_CONFLICT: ResolutionStrategy.FIRST_COME,
            ConflictType.RESOURCE_LOCK: ResolutionStrategy.LOCK_AND_QUEUE,
            ConflictType.DEPENDENCY_CONFLICT: ResolutionStrategy.PRIORITY_BASED,
            ConflictType.STATE_CONFLICT: ResolutionStrategy.ABORT_ALL,
            ConflictType.PRIORITY_CONFLICT: ResolutionStrategy.PRIORITY_BASED,
            ConflictType.SEMANTIC_CONFLICT: ResolutionStrategy.MANUAL,
        }
        self._merge_rules: dict[str, MergeRule] = {}
        self._colony_priorities: dict[str, int] = {}  # colony_id -> priority
        self._resolutions: dict[str, ResolutionResult] = {}
        self._on_resolved: list[Callable[[ResolutionResult], None]] = []

    def set_strategy(self, conflict_type: ConflictType, strategy: ResolutionStrategy) -> None:
        """衝突タイプ別のデフォルト戦略を設定"""
        self._strategies[conflict_type] = strategy

    def set_colony_priority(self, colony_id: str, priority: int) -> None:
        """Colony優先度を設定（大きいほど高優先）"""
        self._colony_priorities[colony_id] = priority

    def add_merge_rule(self, rule: MergeRule) -> None:
        """マージルール追加"""
        self._merge_rules[rule.resource_type] = rule

    def add_resolution_listener(self, listener: Callable[[ResolutionResult], None]) -> None:
        """解決リスナー追加"""
        self._on_resolved.append(listener)

    def resolve(
        self,
        conflict: Conflict,
        strategy: ResolutionStrategy | None = None,
    ) -> ResolutionResult:
        """衝突を解決"""
        if strategy is None:
            strategy = self._strategies.get(conflict.conflict_type, ResolutionStrategy.MANUAL)

        result = ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy=strategy,
            status=ResolutionStatus.IN_PROGRESS,
        )

        try:
            if strategy == ResolutionStrategy.FIRST_COME:
                result = self._resolve_first_come(conflict, result)
            elif strategy == ResolutionStrategy.PRIORITY_BASED:
                result = self._resolve_priority_based(conflict, result)
            elif strategy == ResolutionStrategy.MERGE:
                result = self._resolve_merge(conflict, result)
            elif strategy == ResolutionStrategy.ABORT_ALL:
                result = self._resolve_abort_all(conflict, result)
            elif strategy == ResolutionStrategy.LOCK_AND_QUEUE:
                result = self._resolve_lock_and_queue(conflict, result)
            elif strategy == ResolutionStrategy.RETRY_LATER:
                result = self._resolve_retry_later(conflict, result)
            else:
                result = self._resolve_manual(conflict, result)

        except Exception as e:
            result.status = ResolutionStatus.FAILED
            result.message = str(e)

        self._resolutions[result.resolution_id] = result
        self._notify_resolved(result)

        return result

    def _resolve_first_come(self, conflict: Conflict, result: ResolutionResult) -> ResolutionResult:
        """先着優先で解決"""
        if not conflict.claims:
            result.status = ResolutionStatus.FAILED
            result.message = "No claims to resolve"
            return result

        # タイムスタンプで最初のclaimを勝者に
        sorted_claims = sorted(conflict.claims, key=lambda c: c.timestamp)
        winner = sorted_claims[0]

        result.winner_colony_id = winner.colony_id
        result.status = ResolutionStatus.RESOLVED
        result.message = f"First claim by {winner.colony_id} wins"
        result.resolved_at = datetime.now()

        return result

    def _resolve_priority_based(
        self, conflict: Conflict, result: ResolutionResult
    ) -> ResolutionResult:
        """優先度ベースで解決"""
        if not conflict.claims:
            result.status = ResolutionStatus.FAILED
            result.message = "No claims to resolve"
            return result

        # 優先度で勝者決定（優先度が高い=数値が大きい方が勝ち）
        winner = max(
            conflict.claims,
            key=lambda c: self._colony_priorities.get(c.colony_id, 0),
        )

        result.winner_colony_id = winner.colony_id
        result.status = ResolutionStatus.RESOLVED
        result.message = f"Priority winner: {winner.colony_id}"
        result.resolved_at = datetime.now()

        return result

    def _resolve_merge(self, conflict: Conflict, result: ResolutionResult) -> ResolutionResult:
        """マージで解決"""
        resource_type = conflict.claims[0].resource_type if conflict.claims else ""
        rule = self._merge_rules.get(resource_type)

        if not rule:
            result.status = ResolutionStatus.ESCALATED
            result.message = f"No merge rule for {resource_type}"
            return result

        result.status = ResolutionStatus.RESOLVED
        result.message = f"Merged using rule: {rule.merge_function}"
        result.resolved_at = datetime.now()
        result.metadata["merge_rule"] = rule.rule_id

        return result

    def _resolve_abort_all(self, conflict: Conflict, result: ResolutionResult) -> ResolutionResult:
        """全キャンセルで解決"""
        result.status = ResolutionStatus.RESOLVED
        result.message = "All operations aborted"
        result.resolved_at = datetime.now()
        result.metadata["aborted_colonies"] = conflict.colony_ids

        return result

    def _resolve_lock_and_queue(
        self, conflict: Conflict, result: ResolutionResult
    ) -> ResolutionResult:
        """ロック＆キューで解決"""
        if not conflict.claims:
            result.status = ResolutionStatus.FAILED
            result.message = "No claims to resolve"
            return result

        # 最初のclaimにロックを与え、残りはキューに
        sorted_claims = sorted(conflict.claims, key=lambda c: c.timestamp)
        winner = sorted_claims[0]
        queued = sorted_claims[1:]

        result.winner_colony_id = winner.colony_id
        result.status = ResolutionStatus.RESOLVED
        result.message = f"Lock granted to {winner.colony_id}, {len(queued)} queued"
        result.resolved_at = datetime.now()
        result.metadata["queued_colonies"] = [c.colony_id for c in queued]

        return result

    def _resolve_retry_later(
        self, conflict: Conflict, result: ResolutionResult
    ) -> ResolutionResult:
        """リトライで解決"""
        result.status = ResolutionStatus.PENDING
        result.message = "Scheduled for retry"
        result.metadata["retry_at"] = datetime.now()

        return result

    def _resolve_manual(self, conflict: Conflict, result: ResolutionResult) -> ResolutionResult:
        """手動解決にエスカレート"""
        result.status = ResolutionStatus.ESCALATED
        result.message = "Manual resolution required"

        return result

    def _notify_resolved(self, result: ResolutionResult) -> None:
        """解決を通知"""
        for listener in self._on_resolved:
            try:
                listener(result)
            except Exception:
                pass

    def get_resolution(self, resolution_id: str) -> ResolutionResult | None:
        """解決結果取得"""
        return self._resolutions.get(resolution_id)

    def get_resolutions_by_status(self, status: ResolutionStatus) -> list[ResolutionResult]:
        """ステータス別の解決結果一覧"""
        return [r for r in self._resolutions.values() if r.status == status]

    def get_pending_resolutions(self) -> list[ResolutionResult]:
        """未解決の一覧"""
        return self.get_resolutions_by_status(
            ResolutionStatus.PENDING
        ) + self.get_resolutions_by_status(ResolutionStatus.ESCALATED)

    def get_stats(self) -> dict[str, Any]:
        """統計情報"""
        resolutions = list(self._resolutions.values())
        return {
            "total": len(resolutions),
            "resolved": len([r for r in resolutions if r.status == ResolutionStatus.RESOLVED]),
            "failed": len([r for r in resolutions if r.status == ResolutionStatus.FAILED]),
            "escalated": len([r for r in resolutions if r.status == ResolutionStatus.ESCALATED]),
            "pending": len([r for r in resolutions if r.status == ResolutionStatus.PENDING]),
        }
