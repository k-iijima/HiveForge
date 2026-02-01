"""
Direct Intervention イベントテスト

ユーザー直接介入、Queen直訴、Beekeeperフィードバックのイベントテスト。
"""


from hiveforge.core.events import (
    BeekeeperFeedbackEvent,
    EscalationType,
    EventType,
    QueenEscalationEvent,
    UserDirectInterventionEvent,
    parse_event,
)


class TestUserDirectInterventionEvent:
    """ユーザー直接介入イベントのテスト"""

    def test_create_event(self):
        """イベントを作成できる

        Arrange: 必要なペイロード
        Act: イベント作成
        Assert: 正しいタイプとフィールド
        """
        # Arrange & Act
        event = UserDirectInterventionEvent(
            actor="user",
            payload={
                "colony_id": "col-001",
                "instruction": "このアプローチで進めて",
                "reason": "Beekeeperの指示が不明確だったため",
                "bypass_beekeeper": True,
                "share_with_beekeeper": True,
            },
        )

        # Assert
        assert event.type == EventType.USER_DIRECT_INTERVENTION
        assert event.payload["colony_id"] == "col-001"
        assert event.payload["instruction"] == "このアプローチで進めて"
        assert event.payload["bypass_beekeeper"] is True

    def test_parse_event(self):
        """JSONからパースできる

        Arrange: イベント辞書
        Act: parse_event
        Assert: 正しいイベントクラス
        """
        # Arrange
        event = UserDirectInterventionEvent(
            actor="user",
            payload={
                "colony_id": "col-001",
                "instruction": "テスト指示",
                "reason": "テスト理由",
            },
        )
        event_json = event.model_dump()

        # Act
        parsed = parse_event(event_json)

        # Assert
        assert isinstance(parsed, UserDirectInterventionEvent)
        assert parsed.id == event.id


class TestQueenEscalationEvent:
    """Queen直訴イベントのテスト"""

    def test_create_event(self):
        """イベントを作成できる

        Arrange: 直訴ペイロード
        Act: イベント作成
        Assert: 正しいタイプとフィールド
        """
        # Arrange & Act
        event = QueenEscalationEvent(
            actor="queen-bee-001",
            payload={
                "colony_id": "col-001",
                "escalation_type": EscalationType.BEEKEEPER_CONFLICT.value,
                "summary": "設計方針について見解の相違",
                "details": "BeekeeperはパターンAを推奨するが、技術的にパターンBが適切",
                "suggested_actions": ["パターンBで進める", "両方試してベンチマーク"],
                "beekeeper_context": "3回の議論で合意に至らず",
            },
        )

        # Assert
        assert event.type == EventType.QUEEN_ESCALATION
        assert event.payload["escalation_type"] == "beekeeper_conflict"
        assert len(event.payload["suggested_actions"]) == 2

    def test_all_escalation_types(self):
        """全てのエスカレーションタイプで作成できる

        Arrange: 全EscalationType
        Act: 各タイプでイベント作成
        Assert: 全て成功
        """
        for esc_type in EscalationType:
            # Act
            event = QueenEscalationEvent(
                actor="queen",
                payload={
                    "colony_id": "col-001",
                    "escalation_type": esc_type.value,
                    "summary": f"テスト: {esc_type.name}",
                    "details": "詳細",
                    "suggested_actions": [],
                },
            )

            # Assert
            assert event.payload["escalation_type"] == esc_type.value

    def test_parse_event(self):
        """JSONからパースできる

        Arrange: イベント辞書
        Act: parse_event
        Assert: 正しいイベントクラス
        """
        # Arrange
        event = QueenEscalationEvent(
            actor="queen",
            payload={
                "colony_id": "col-001",
                "escalation_type": EscalationType.TECHNICAL_BLOCKER.value,
                "summary": "技術的問題",
                "details": "ライブラリの制限",
                "suggested_actions": ["代替案を検討"],
            },
        )
        event_json = event.model_dump()

        # Act
        parsed = parse_event(event_json)

        # Assert
        assert isinstance(parsed, QueenEscalationEvent)


class TestBeekeeperFeedbackEvent:
    """Beekeeperフィードバックイベントのテスト"""

    def test_create_event(self):
        """イベントを作成できる

        Arrange: フィードバックペイロード
        Act: イベント作成
        Assert: 正しいタイプとフィールド
        """
        # Arrange & Act
        event = BeekeeperFeedbackEvent(
            actor="user",
            payload={
                "escalation_id": "evt-123",
                "resolution": "パターンBで進めることに決定",
                "beekeeper_adjustment": {
                    "prefer_pattern": "B",
                    "consider_performance": True,
                },
                "lesson_learned": "初期段階で技術調査を推奨すべき",
            },
        )

        # Assert
        assert event.type == EventType.BEEKEEPER_FEEDBACK
        assert event.payload["escalation_id"] == "evt-123"
        assert event.payload["beekeeper_adjustment"]["prefer_pattern"] == "B"

    def test_parse_event(self):
        """JSONからパースできる

        Arrange: イベント辞書
        Act: parse_event
        Assert: 正しいイベントクラス
        """
        # Arrange
        event = BeekeeperFeedbackEvent(
            actor="user",
            payload={
                "escalation_id": "evt-456",
                "resolution": "解決済み",
                "beekeeper_adjustment": {},
            },
        )
        event_json = event.model_dump()

        # Act
        parsed = parse_event(event_json)

        # Assert
        assert isinstance(parsed, BeekeeperFeedbackEvent)


class TestEscalationType:
    """EscalationType列挙型のテスト"""

    def test_all_types_have_values(self):
        """全タイプに値がある

        Arrange: EscalationType
        Act: 全タイプを確認
        Assert: 値が設定されている
        """
        expected_types = [
            "beekeeper_conflict",
            "resource_shortage",
            "technical_blocker",
            "scope_clarification",
            "priority_dispute",
            "external_dependency",
        ]

        actual_types = [t.value for t in EscalationType]

        assert set(actual_types) == set(expected_types)

    def test_type_count(self):
        """タイプ数が正しい

        Arrange: EscalationType
        Act: カウント
        Assert: 6種類
        """
        assert len(EscalationType) == 6
