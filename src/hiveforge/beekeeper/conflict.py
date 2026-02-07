"""Colony間衝突検出

複数ColonyのオペレーションがリソースやファイルでConflictする可能性を検出。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ulid import ULID


class ConflictType(str, Enum):
    """衝突タイプ"""

    FILE_CONFLICT = "file_conflict"  # 同一ファイルへの変更
    RESOURCE_LOCK = "resource_lock"  # リソースロック競合
    DEPENDENCY_CONFLICT = "dependency_conflict"  # 依存関係の競合
    STATE_CONFLICT = "state_conflict"  # 状態遷移の競合
    PRIORITY_CONFLICT = "priority_conflict"  # 優先度の競合
    SEMANTIC_CONFLICT = "semantic_conflict"  # 意味的な競合（同じ機能を別実装）


class ConflictSeverity(str, Enum):
    """衝突の深刻度"""

    LOW = "low"  # 自動解決可能
    MEDIUM = "medium"  # 確認推奨
    HIGH = "high"  # 人間の判断必要
    CRITICAL = "critical"  # 即時停止推奨


@dataclass
class ResourceClaim:
    """リソース要求"""

    colony_id: str
    resource_type: str  # "file", "api", "database", etc.
    resource_id: str  # ファイルパス、API名等
    operation: str  # "read", "write", "delete", etc.
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Conflict:
    """衝突情報"""

    conflict_id: str = field(default_factory=lambda: str(ULID()))
    conflict_type: ConflictType = ConflictType.FILE_CONFLICT
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    resource_id: str = ""
    colony_ids: list[str] = field(default_factory=list)
    claims: list[ResourceClaim] = field(default_factory=list)
    description: str = ""
    detected_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolution: str | None = None


class ConflictDetector:
    """衝突検出器

    複数Colonyからのリソース要求を監視し、衝突を検出。
    """

    def __init__(self):
        self._claims: dict[str, list[ResourceClaim]] = {}  # resource_id -> claims
        self._conflicts: dict[str, Conflict] = {}
        self._on_conflict_detected: list[callable] = []

    def add_conflict_listener(self, listener: callable) -> None:
        """衝突検出リスナー追加"""
        self._on_conflict_detected.append(listener)

    def register_claim(self, claim: ResourceClaim) -> Conflict | None:
        """リソース要求を登録し、衝突があれば返す"""
        resource_id = claim.resource_id

        if resource_id not in self._claims:
            self._claims[resource_id] = []

        # 既存の要求と衝突チェック
        existing_claims = self._claims[resource_id]
        conflicting_claims = self._find_conflicting_claims(claim, existing_claims)

        # 衝突有無に関わらずclaimは登録する
        self._claims[resource_id].append(claim)

        if conflicting_claims:
            conflict = self._create_conflict(claim, conflicting_claims)
            self._conflicts[conflict.conflict_id] = conflict
            self._notify_conflict(conflict)
            return conflict

        return None

    def _find_conflicting_claims(
        self,
        new_claim: ResourceClaim,
        existing: list[ResourceClaim],
    ) -> list[ResourceClaim]:
        """競合する要求を検出"""
        conflicts = []
        for claim in existing:
            if claim.colony_id == new_claim.colony_id:
                continue  # 同一Colonyは競合しない

            if self._is_conflicting(new_claim, claim):
                conflicts.append(claim)

        return conflicts

    def _is_conflicting(self, claim1: ResourceClaim, claim2: ResourceClaim) -> bool:
        """2つの要求が競合するか"""
        # 書き込み同士は競合
        if claim1.operation == "write" and claim2.operation == "write":
            return True

        # 書き込みと削除は競合
        if "delete" in (claim1.operation, claim2.operation):
            if "write" in (claim1.operation, claim2.operation):
                return True

        # 削除同士は競合
        if claim1.operation == "delete" and claim2.operation == "delete":
            return True

        return False

    def _create_conflict(
        self,
        new_claim: ResourceClaim,
        conflicting: list[ResourceClaim],
    ) -> Conflict:
        """衝突オブジェクト作成"""
        all_claims = [new_claim] + conflicting
        colony_ids = list({c.colony_id for c in all_claims})

        severity = self._determine_severity(all_claims)
        conflict_type = self._determine_type(all_claims)

        return Conflict(
            conflict_type=conflict_type,
            severity=severity,
            resource_id=new_claim.resource_id,
            colony_ids=colony_ids,
            claims=all_claims,
            description=f"{len(colony_ids)} colonies conflict on {new_claim.resource_id}",
        )

    def _determine_severity(self, claims: list[ResourceClaim]) -> ConflictSeverity:
        """深刻度を判定"""
        operations = {c.operation for c in claims}

        if "delete" in operations:
            return ConflictSeverity.CRITICAL

        if len(claims) > 2:
            return ConflictSeverity.HIGH

        return ConflictSeverity.MEDIUM

    def _determine_type(self, claims: list[ResourceClaim]) -> ConflictType:
        """衝突タイプを判定"""
        resource_types = {c.resource_type for c in claims}

        if "file" in resource_types:
            return ConflictType.FILE_CONFLICT

        if "lock" in resource_types:
            return ConflictType.RESOURCE_LOCK

        return ConflictType.STATE_CONFLICT

    def _notify_conflict(self, conflict: Conflict) -> None:
        """衝突を通知"""
        for listener in self._on_conflict_detected:
            try:
                listener(conflict)
            except Exception:
                pass  # リスナーエラーは無視

    def release_claim(self, colony_id: str, resource_id: str) -> bool:
        """リソース要求を解放"""
        if resource_id not in self._claims:
            return False

        original_len = len(self._claims[resource_id])
        self._claims[resource_id] = [
            c for c in self._claims[resource_id] if c.colony_id != colony_id
        ]

        return len(self._claims[resource_id]) < original_len

    def get_conflicts(self, include_resolved: bool = False) -> list[Conflict]:
        """衝突一覧"""
        conflicts = list(self._conflicts.values())
        if not include_resolved:
            conflicts = [c for c in conflicts if not c.resolved]
        return conflicts

    def get_conflict(self, conflict_id: str) -> Conflict | None:
        """衝突取得"""
        return self._conflicts.get(conflict_id)

    def get_claims_for_resource(self, resource_id: str) -> list[ResourceClaim]:
        """リソースへの要求一覧"""
        return self._claims.get(resource_id, [])

    def get_claims_by_colony(self, colony_id: str) -> list[ResourceClaim]:
        """Colony別の要求一覧"""
        claims = []
        for resource_claims in self._claims.values():
            claims.extend(c for c in resource_claims if c.colony_id == colony_id)
        return claims

    def mark_resolved(self, conflict_id: str, resolution: str) -> bool:
        """衝突を解決済みにマーク"""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False

        conflict.resolved = True
        conflict.resolution = resolution
        return True

    def clear_all(self) -> None:
        """全てクリア"""
        self._claims.clear()
        self._conflicts.clear()

    def get_stats(self) -> dict[str, Any]:
        """統計情報"""
        conflicts = list(self._conflicts.values())
        return {
            "total_resources": len(self._claims),
            "total_claims": sum(len(c) for c in self._claims.values()),
            "total_conflicts": len(conflicts),
            "unresolved_conflicts": len([c for c in conflicts if not c.resolved]),
            "critical_conflicts": len(
                [c for c in conflicts if c.severity == ConflictSeverity.CRITICAL]
            ),
        }
