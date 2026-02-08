"""Conflict Detection イベント型のテスト

外部フィードバック対応: Colony間の意見衝突を検出・解決するためのイベント。
"""

from hiveforge.core.events import (
    EVENT_TYPE_MAP,
    ConflictDetectedEvent,
    ConflictResolvedEvent,
    EventType,
    parse_event,
)


class TestConflictDetectionEventTypes:
    """Conflict Detection イベント型がEventTypeに定義されているかテスト"""

    def test_conflict_detected_event_type_exists(self):
        """CONFLICT_DETECTEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.CONFLICT_DETECTED

        # Assert
        assert event_type.value == "conflict.detected"

    def test_conflict_resolved_event_type_exists(self):
        """CONFLICT_RESOLVEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.CONFLICT_RESOLVED

        # Assert
        assert event_type.value == "conflict.resolved"


class TestConflictDetectedEvent:
    """ConflictDetectedEvent のテスト"""

    def test_create_conflict_detected_event(self):
        """衝突検出イベントを生成できる

        複数ColonyからのOpinionResponseが矛盾する場合に発行。
        """
        # Arrange
        payload = {
            "conflict_id": "conflict-001",
            "topic": "認証方式の選定",
            "colonies": ["api-colony", "security-colony"],
            "opinions": [
                {
                    "colony_id": "api-colony",
                    "position": "JWTトークン認証",
                    "rationale": "実装がシンプルでスケーラブル",
                },
                {
                    "colony_id": "security-colony",
                    "position": "セッションベース認証",
                    "rationale": "トークン漏洩リスクを低減",
                },
            ],
        }

        # Act
        event = ConflictDetectedEvent(
            actor="beekeeper",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.CONFLICT_DETECTED
        assert event.payload["conflict_id"] == "conflict-001"
        assert len(event.payload["colonies"]) == 2
        assert len(event.payload["opinions"]) == 2

    def test_conflict_detected_with_three_colonies(self):
        """3つ以上のColonyが衝突する場合"""
        # Arrange
        payload = {
            "conflict_id": "conflict-002",
            "topic": "デプロイ先の選定",
            "colonies": ["infra-colony", "cost-colony", "performance-colony"],
            "opinions": [
                {"colony_id": "infra-colony", "position": "AWS", "rationale": "既存インフラ"},
                {"colony_id": "cost-colony", "position": "GCP", "rationale": "コスト効率"},
                {"colony_id": "performance-colony", "position": "Azure", "rationale": "地域対応"},
            ],
        }

        # Act
        event = ConflictDetectedEvent(actor="beekeeper", payload=payload)

        # Assert
        assert len(event.payload["colonies"]) == 3
        assert len(event.payload["opinions"]) == 3


class TestConflictResolvedEvent:
    """ConflictResolvedEvent のテスト"""

    def test_create_conflict_resolved_event(self):
        """衝突解決イベントを生成できる"""
        # Arrange
        payload = {
            "conflict_id": "conflict-001",
            "resolved_by": "user",
            "resolution": "JWTトークン認証を採用。ただし短い有効期限とリフレッシュトークンを使用",
            "merge_rule": "security_first",
        }

        # Act
        event = ConflictResolvedEvent(
            actor="user",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.CONFLICT_RESOLVED
        assert event.payload["conflict_id"] == "conflict-001"
        assert event.payload["resolved_by"] == "user"
        assert "JWTトークン" in event.payload["resolution"]

    def test_conflict_resolved_by_beekeeper(self):
        """Beekeeperによる自動解決"""
        # Arrange
        payload = {
            "conflict_id": "conflict-002",
            "resolved_by": "beekeeper",
            "resolution": "コスト重視でGCPを採用",
            "merge_rule": "priority_weight",
        }

        # Act
        event = ConflictResolvedEvent(actor="beekeeper", payload=payload)

        # Assert
        assert event.payload["resolved_by"] == "beekeeper"

    def test_conflict_resolved_without_merge_rule(self):
        """マージルールなしで解決"""
        # Arrange
        payload = {
            "conflict_id": "conflict-003",
            "resolved_by": "user",
            "resolution": "手動で判断",
            "merge_rule": None,
        }

        # Act
        event = ConflictResolvedEvent(actor="user", payload=payload)

        # Assert
        assert event.payload["merge_rule"] is None


class TestConflictEventTypeMap:
    """EVENT_TYPE_MAP に Conflict イベントが登録されているかテスト"""

    def test_conflict_detected_in_event_type_map(self):
        """CONFLICT_DETECTEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.CONFLICT_DETECTED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.CONFLICT_DETECTED] == ConflictDetectedEvent

    def test_conflict_resolved_in_event_type_map(self):
        """CONFLICT_RESOLVEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.CONFLICT_RESOLVED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.CONFLICT_RESOLVED] == ConflictResolvedEvent


class TestConflictParseEvent:
    """parse_event で Conflict イベントが正しくパースされるかテスト"""

    def test_parse_conflict_detected_event(self):
        """CONFLICT_DETECTEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "conflict.detected",
            "actor": "beekeeper",
            "payload": {
                "conflict_id": "conflict-001",
                "topic": "test",
                "colonies": ["a", "b"],
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConflictDetectedEvent)
        assert event.type == EventType.CONFLICT_DETECTED

    def test_parse_conflict_resolved_event(self):
        """CONFLICT_RESOLVEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "conflict.resolved",
            "actor": "user",
            "payload": {
                "conflict_id": "conflict-001",
                "resolution": "resolved",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, ConflictResolvedEvent)
        assert event.type == EventType.CONFLICT_RESOLVED
