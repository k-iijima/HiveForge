"""Conflict イベントのカテゴリ・深刻度テスト

外部フィードバック対応: 衝突の優先順位付けのためのcategory/severityを追加。
"""

import pytest

from hiveforge.core.events import (
    ConflictCategory,
    ConflictDetectedEvent,
    ConflictResolvedEvent,
    ConflictSeverity,
    EventType,
    parse_event,
)


class TestConflictCategoryEnum:
    """ConflictCategory 列挙型のテスト"""

    def test_conflict_category_enum_exists(self):
        """ConflictCategory列挙型が存在する"""
        # Assert
        assert ConflictCategory is not None

    def test_conflict_category_has_assumption(self):
        """ASSUMPTION: 前提条件の不一致"""
        assert ConflictCategory.ASSUMPTION == "assumption"

    def test_conflict_category_has_priority(self):
        """PRIORITY: 優先順位の衝突"""
        assert ConflictCategory.PRIORITY == "priority"

    def test_conflict_category_has_dependency(self):
        """DEPENDENCY: 依存関係の矛盾"""
        assert ConflictCategory.DEPENDENCY == "dependency"

    def test_conflict_category_has_constraint(self):
        """CONSTRAINT: 制約条件の対立"""
        assert ConflictCategory.CONSTRAINT == "constraint"


class TestConflictSeverityEnum:
    """ConflictSeverity 列挙型のテスト"""

    def test_conflict_severity_enum_exists(self):
        """ConflictSeverity列挙型が存在する"""
        # Assert
        assert ConflictSeverity is not None

    def test_conflict_severity_has_low(self):
        """LOW: 軽微（後で調整可能）"""
        assert ConflictSeverity.LOW == "low"

    def test_conflict_severity_has_medium(self):
        """MEDIUM: 中程度（1-2日以内に解決必要）"""
        assert ConflictSeverity.MEDIUM == "medium"

    def test_conflict_severity_has_high(self):
        """HIGH: 重大（即座に解決必要）"""
        assert ConflictSeverity.HIGH == "high"

    def test_conflict_severity_has_blocker(self):
        """BLOCKER: 阻害（解決するまで作業停止）"""
        assert ConflictSeverity.BLOCKER == "blocker"


class TestConflictDetectedEventPayload:
    """ConflictDetectedEvent のペイロード拡張テスト"""

    def test_create_conflict_with_category_and_severity(self):
        """category/severityを含むConflictDetectedEventを作成できる"""
        # Arrange & Act
        event = ConflictDetectedEvent(
            actor="beekeeper",
            payload={
                "conflict_id": "conflict-001",
                "topic": "認証方式の選定",
                "category": ConflictCategory.PRIORITY.value,
                "severity": ConflictSeverity.HIGH.value,
                "parties": ["ui-colony", "api-colony"],
                "evidence_event_ids": ["event-001", "event-002"],
            },
        )

        # Assert
        assert event.payload["category"] == "priority"
        assert event.payload["severity"] == "high"
        assert event.payload["conflict_id"] == "conflict-001"

    def test_parse_conflict_with_category_severity(self):
        """category/severityを含むConflictDetectedEventをパースできる"""
        # Arrange
        data = {
            "type": "conflict.detected",
            "actor": "beekeeper",
            "payload": {
                "conflict_id": "conflict-002",
                "topic": "API設計方針",
                "category": "dependency",
                "severity": "blocker",
                "parties": ["backend-colony", "frontend-colony"],
                "evidence_event_ids": ["ev-001"],
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConflictDetectedEvent)
        assert event.payload["category"] == "dependency"
        assert event.payload["severity"] == "blocker"

    def test_conflict_event_with_suggested_resolutions(self):
        """suggested_resolutionsを含むConflictDetectedEvent"""
        # Arrange
        event = ConflictDetectedEvent(
            actor="beekeeper",
            payload={
                "conflict_id": "conflict-003",
                "topic": "データモデル設計",
                "category": ConflictCategory.ASSUMPTION.value,
                "severity": ConflictSeverity.MEDIUM.value,
                "parties": ["data-colony"],
                "evidence_event_ids": [],
                "suggested_resolutions": [
                    "Option A: 正規化を優先",
                    "Option B: パフォーマンスを優先",
                ],
            },
        )

        # Assert
        assert len(event.payload["suggested_resolutions"]) == 2


class TestConflictSeverityOrdering:
    """深刻度の順序付けテスト"""

    def test_severity_ordering_low_to_blocker(self):
        """深刻度はLOW < MEDIUM < HIGH < BLOCKERの順"""
        # Arrange
        severities = [
            ConflictSeverity.BLOCKER,
            ConflictSeverity.LOW,
            ConflictSeverity.HIGH,
            ConflictSeverity.MEDIUM,
        ]

        # Act: 定義順でソート（Enumのメンバー定義順）
        expected_order = [
            ConflictSeverity.LOW,
            ConflictSeverity.MEDIUM,
            ConflictSeverity.HIGH,
            ConflictSeverity.BLOCKER,
        ]

        # Assert: 全メンバーを確認
        all_members = list(ConflictSeverity)
        assert all_members == expected_order


class TestConflictResolvedWithCategory:
    """ConflictResolvedEvent がカテゴリ情報を保持できることのテスト"""

    def test_resolved_event_references_original_category(self):
        """ConflictResolvedEventは元の衝突のカテゴリを参照できる"""
        # Arrange
        resolved_event = ConflictResolvedEvent(
            actor="user",
            payload={
                "conflict_id": "conflict-001",
                "resolution": "Option Aを採用",
                "original_category": ConflictCategory.PRIORITY.value,
                "original_severity": ConflictSeverity.HIGH.value,
            },
        )

        # Assert
        assert resolved_event.payload["original_category"] == "priority"
        assert resolved_event.payload["original_severity"] == "high"
