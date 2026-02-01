"""Beekeeperテスト"""

import pytest
from hiveforge.beekeeper.session import (
    BeekeeperSession,
    BeekeeperSessionManager,
    SessionState,
    UserInstruction,
)
from hiveforge.beekeeper.projection import (
    BeekeeperProjection,
    build_beekeeper_projection,
    HiveOverview,
    build_hive_overview,
)
from hiveforge.beekeeper.handler import BeekeeperHandler, InstructionResult
from hiveforge.core.events import BaseEvent, EventType


class TestBeekeeperSession:
    """BeekeeperSessionの基本テスト"""

    def test_create_session(self):
        """セッション作成"""
        session = BeekeeperSession()
        assert session.session_id is not None
        assert session.state == SessionState.IDLE

    def test_activate_session(self):
        """セッションをアクティブ化"""
        session = BeekeeperSession()
        session.activate("hive-1")

        assert session.hive_id == "hive-1"
        assert session.state == SessionState.ACTIVE

    def test_add_colony(self):
        """Colonyを追加"""
        session = BeekeeperSession()
        session.add_colony("colony-1", "queen-1")

        assert "colony-1" in session.active_colonies
        assert session.active_colonies["colony-1"].queen_bee_id == "queen-1"

    def test_remove_colony(self):
        """Colonyを削除"""
        session = BeekeeperSession()
        session.add_colony("colony-1")
        session.remove_colony("colony-1")

        assert "colony-1" not in session.active_colonies

    def test_state_transitions(self):
        """状態遷移"""
        session = BeekeeperSession()

        session.set_busy()
        assert session.state == SessionState.BUSY

        session.set_waiting_user()
        assert session.state == SessionState.WAITING_USER

        session.set_active()
        assert session.state == SessionState.ACTIVE

        session.suspend()
        assert session.state == SessionState.SUSPENDED

        session.resume()
        assert session.state == SessionState.ACTIVE

    def test_context_management(self):
        """コンテキスト管理"""
        session = BeekeeperSession()
        session.update_context("key1", "value1")

        assert session.get_context("key1") == "value1"
        assert session.get_context("nonexistent", "default") == "default"

        session.clear_context()
        assert session.get_context("key1") is None


class TestBeekeeperSessionManager:
    """SessionManagerのテスト"""

    def test_create_and_get_session(self):
        """セッション作成と取得"""
        manager = BeekeeperSessionManager()
        session = manager.create_session("hive-1")

        retrieved = manager.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_close_session(self):
        """セッション終了"""
        manager = BeekeeperSessionManager()
        session = manager.create_session()

        result = manager.close_session(session.session_id)
        assert result is True
        assert manager.get_session(session.session_id) is None

    def test_close_nonexistent_session(self):
        """存在しないセッションの終了"""
        manager = BeekeeperSessionManager()
        result = manager.close_session("nonexistent")
        assert result is False

    def test_list_sessions(self):
        """セッション一覧"""
        manager = BeekeeperSessionManager()
        manager.create_session()
        manager.create_session()

        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_get_active_sessions(self):
        """アクティブセッション取得"""
        manager = BeekeeperSessionManager()
        session1 = manager.create_session("hive-1")
        session2 = manager.create_session()

        active = manager.get_active_sessions()
        assert len(active) == 1
        assert active[0].session_id == session1.session_id


class TestBeekeeperProjection:
    """BeekeeperProjectionのテスト"""

    def test_apply_hive_created(self):
        """HIVE_CREATEDイベントを適用"""
        projection = BeekeeperProjection()
        event = BaseEvent(type=EventType.HIVE_CREATED, payload={"hive_id": "hive-1"})

        projection.apply_event(event)

        assert projection.hive_id == "hive-1"
        assert projection.state == SessionState.ACTIVE

    def test_apply_colony_created(self):
        """COLONY_CREATEDイベントを適用"""
        projection = BeekeeperProjection()
        event = BaseEvent(type=EventType.COLONY_CREATED, colony_id="colony-1")

        projection.apply_event(event)

        assert "colony-1" in projection.active_colonies

    def test_apply_requirement_lifecycle(self):
        """要求ライフサイクル"""
        projection = BeekeeperProjection()

        # 要求作成
        created = BaseEvent(type=EventType.REQUIREMENT_CREATED, id="req-1")
        projection.apply_event(created)
        assert "req-1" in projection.pending_instructions

        # 要求承認
        approved = BaseEvent(type=EventType.REQUIREMENT_APPROVED, id="req-1")
        projection.apply_event(approved)
        assert "req-1" not in projection.pending_instructions
        assert projection.completed_instructions == 1

    def test_apply_emergency_stop(self):
        """緊急停止イベントを適用"""
        projection = BeekeeperProjection()
        event = BaseEvent(type=EventType.EMERGENCY_STOP)

        projection.apply_event(event)

        assert projection.state == SessionState.SUSPENDED

    def test_build_from_events(self):
        """イベントから構築"""
        events = [
            BaseEvent(type=EventType.HIVE_CREATED, payload={"hive_id": "hive-1"}),
            BaseEvent(type=EventType.COLONY_CREATED, colony_id="colony-1"),
            BaseEvent(type=EventType.REQUIREMENT_CREATED, id="req-1"),
        ]

        projection = build_beekeeper_projection(events)

        assert projection.hive_id == "hive-1"
        assert "colony-1" in projection.active_colonies
        assert "req-1" in projection.pending_instructions


class TestHiveOverview:
    """HiveOverviewのテスト"""

    def test_build_empty(self):
        """空のイベントリスト"""
        overview = build_hive_overview([])
        assert overview is None

    def test_build_hive_overview(self):
        """Hive概要構築"""
        events = [
            BaseEvent(
                type=EventType.HIVE_CREATED,
                payload={"hive_id": "hive-1", "name": "Test Hive"},
            ),
            BaseEvent(type=EventType.COLONY_CREATED, colony_id="colony-1"),
            BaseEvent(type=EventType.COLONY_CREATED, colony_id="colony-2"),
            BaseEvent(type=EventType.RUN_STARTED, run_id="run-1"),
            BaseEvent(type=EventType.TASK_CREATED, task_id="task-1"),
            BaseEvent(type=EventType.TASK_COMPLETED, task_id="task-1"),
        ]

        overview = build_hive_overview(events)

        assert overview is not None
        assert overview.hive_id == "hive-1"
        assert overview.name == "Test Hive"
        assert overview.colony_count == 2
        assert overview.active_run_count == 1
        assert overview.total_task_count == 1
        assert overview.completed_task_count == 1

    def test_build_with_emergency_stop(self):
        """緊急停止時のステータス"""
        events = [
            BaseEvent(type=EventType.HIVE_CREATED, payload={"hive_id": "hive-1"}),
            BaseEvent(type=EventType.EMERGENCY_STOP),
        ]

        overview = build_hive_overview(events)

        assert overview is not None
        assert overview.status == "stopped"


class TestBeekeeperHandler:
    """BeekeeperHandlerのテスト"""

    def test_start_session(self):
        """セッション開始"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")

        assert session.hive_id == "hive-1"
        assert session.state == SessionState.ACTIVE

    def test_end_session(self):
        """セッション終了"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")

        result = handler.end_session(session.session_id)
        assert result is True

    def test_send_instruction_no_session(self):
        """存在しないセッションへの指示"""
        handler = BeekeeperHandler()
        result = handler.send_instruction("nonexistent", "test instruction")

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_send_instruction_to_colony(self):
        """特定Colonyへの指示"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")

        result = handler.send_instruction(
            session.session_id, "test instruction", target_colony="colony-1"
        )

        assert result.success is True
        assert "colony-1" in result.message

    def test_send_instruction_broadcast(self):
        """ブロードキャスト指示"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")
        handler.add_colony_to_session(session.session_id, "colony-1")
        handler.add_colony_to_session(session.session_id, "colony-2")

        result = handler.send_instruction(session.session_id, "test instruction")

        assert result.success is True

    def test_add_colony_to_session(self):
        """セッションにColony追加"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")

        result = handler.add_colony_to_session(session.session_id, "colony-1", "queen-1")

        assert result.success is True
        assert "colony-1" in session.active_colonies

    def test_remove_colony_from_session(self):
        """セッションからColony削除"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")
        handler.add_colony_to_session(session.session_id, "colony-1")

        result = handler.remove_colony_from_session(session.session_id, "colony-1")

        assert result.success is True
        assert "colony-1" not in session.active_colonies

    def test_get_instruction_history(self):
        """指示履歴取得"""
        handler = BeekeeperHandler()
        session = handler.start_session("hive-1")
        handler.add_colony_to_session(session.session_id, "colony-1")
        handler.send_instruction(session.session_id, "instruction 1", "colony-1")
        handler.send_instruction(session.session_id, "instruction 2", "colony-1")

        history = handler.get_instruction_history(session.session_id)

        assert len(history) == 2

    def test_get_active_sessions(self):
        """アクティブセッション取得"""
        handler = BeekeeperHandler()
        handler.start_session("hive-1")

        active = handler.get_active_sessions()
        assert len(active) == 1


# Escalation テスト
from hiveforge.beekeeper.escalation import (
    Escalation,
    EscalationType,
    EscalationSeverity,
    EscalationStatus,
    EscalationManager,
)


class TestEscalation:
    """Escalationの基本テスト"""

    def test_create_escalation(self):
        """直訴を作成"""
        escalation = Escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="進行不能",
            description="外部APIが応答しない",
        )

        assert escalation.escalation_id is not None
        assert escalation.status == EscalationStatus.PENDING

    def test_escalation_with_suggested_actions(self):
        """推奨アクション付きの直訴"""
        escalation = Escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.CRITICAL_DECISION,
            title="重要な判断",
            description="2つの選択肢があります",
            suggested_actions=["オプションA", "オプションB"],
        )

        assert len(escalation.suggested_actions) == 2


class TestEscalationManager:
    """EscalationManagerのテスト"""

    def test_create_and_get(self):
        """直訴作成と取得"""
        manager = EscalationManager()

        escalation = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BEEKEEPER_TIMEOUT,
            title="Beekeeperタイムアウト",
            description="60秒応答がありません",
        )

        retrieved = manager.get_escalation(escalation.escalation_id)
        assert retrieved is not None
        assert retrieved.title == "Beekeeperタイムアウト"

    def test_acknowledge(self):
        """直訴を確認済みに"""
        manager = EscalationManager()
        escalation = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト",
            description="テスト",
        )

        result = manager.acknowledge(escalation.escalation_id)

        assert result is True
        assert manager.get_escalation(escalation.escalation_id).status == EscalationStatus.ACKNOWLEDGED

    def test_resolve(self):
        """直訴を解決済みに"""
        manager = EscalationManager()
        escalation = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト",
            description="テスト",
        )

        result = manager.resolve(escalation.escalation_id, "問題解決")

        assert result is True
        assert manager.get_escalation(escalation.escalation_id) is None  # 履歴に移動

    def test_dismiss(self):
        """直訴を却下"""
        manager = EscalationManager()
        escalation = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.RESOURCE_CONCERN,
            title="コスト懸念",
            description="API呼び出しが多い",
        )

        result = manager.dismiss(escalation.escalation_id, "許容範囲")

        assert result is True
        assert manager.get_escalation(escalation.escalation_id) is None

    def test_get_pending_escalations(self):
        """未対応の直訴一覧"""
        manager = EscalationManager()
        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト1",
            description="テスト",
        )
        e2 = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト2",
            description="テスト",
        )
        manager.acknowledge(e2.escalation_id)

        pending = manager.get_pending_escalations()
        assert len(pending) == 1

    def test_get_escalations_by_severity(self):
        """重要度別の直訴一覧"""
        manager = EscalationManager()
        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="警告",
            description="テスト",
            severity=EscalationSeverity.WARNING,
        )
        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.SECURITY_CONCERN,
            title="緊急",
            description="テスト",
            severity=EscalationSeverity.CRITICAL,
        )

        critical = manager.get_escalations_by_severity(EscalationSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].title == "緊急"

    def test_get_history(self):
        """直訴履歴"""
        manager = EscalationManager()
        e = manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト",
            description="テスト",
        )
        manager.resolve(e.escalation_id, "解決")

        history = manager.get_history()
        assert len(history) == 1

    def test_notification_callback(self):
        """通知コールバック"""
        notifications = []
        manager = EscalationManager()
        manager.set_notification_callback(lambda e: notifications.append(e))

        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="テスト",
            description="テスト",
        )

        assert len(notifications) == 1

    def test_get_critical_count(self):
        """CRITICAL直訴数"""
        manager = EscalationManager()
        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.SECURITY_CONCERN,
            title="緊急1",
            description="テスト",
            severity=EscalationSeverity.CRITICAL,
        )
        manager.create_escalation(
            colony_id="colony-1",
            queen_bee_id="queen-1",
            escalation_type=EscalationType.BLOCKED,
            title="警告",
            description="テスト",
            severity=EscalationSeverity.WARNING,
        )

        count = manager.get_critical_count()
        assert count == 1

    def test_acknowledge_nonexistent(self):
        """存在しない直訴の確認"""
        manager = EscalationManager()
        result = manager.acknowledge("nonexistent")
        assert result is False

    def test_resolve_nonexistent(self):
        """存在しない直訴の解決"""
        manager = EscalationManager()
        result = manager.resolve("nonexistent", "test")
        assert result is False

    def test_dismiss_nonexistent(self):
        """存在しない直訴の却下"""
        manager = EscalationManager()
        result = manager.dismiss("nonexistent")
        assert result is False


# Conflict Detection テスト
from hiveforge.beekeeper.conflict import (
    Conflict,
    ConflictType,
    ConflictSeverity,
    ConflictDetector,
    ResourceClaim,
)


class TestResourceClaim:
    """ResourceClaimの基本テスト"""

    def test_create_claim(self):
        """リソース要求を作成"""
        claim = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/path/to/file.py",
            operation="write",
        )

        assert claim.colony_id == "colony-1"
        assert claim.resource_type == "file"
        assert claim.operation == "write"


class TestConflict:
    """Conflictの基本テスト"""

    def test_create_conflict(self):
        """衝突を作成"""
        conflict = Conflict(
            conflict_type=ConflictType.FILE_CONFLICT,
            severity=ConflictSeverity.HIGH,
            resource_id="/path/to/file.py",
            colony_ids=["colony-1", "colony-2"],
        )

        assert conflict.conflict_id is not None
        assert not conflict.resolved


class TestConflictDetector:
    """ConflictDetectorのテスト"""

    def test_no_conflict_read_read(self):
        """読み取り同士は競合しない"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/file.py",
            operation="read",
        )
        claim2 = ResourceClaim(
            colony_id="colony-2",
            resource_type="file",
            resource_id="/file.py",
            operation="read",
        )

        result1 = detector.register_claim(claim1)
        result2 = detector.register_claim(claim2)

        assert result1 is None
        assert result2 is None

    def test_conflict_write_write(self):
        """書き込み同士は競合する"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )
        claim2 = ResourceClaim(
            colony_id="colony-2",
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        assert conflict is not None
        assert ConflictType.FILE_CONFLICT == conflict.conflict_type
        assert len(conflict.colony_ids) == 2

    def test_conflict_write_delete(self):
        """書き込みと削除は競合する"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )
        claim2 = ResourceClaim(
            colony_id="colony-2",
            resource_type="file",
            resource_id="/file.py",
            operation="delete",
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        assert conflict is not None
        assert conflict.severity == ConflictSeverity.CRITICAL

    def test_no_conflict_same_colony(self):
        """同一Colonyは競合しない"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )
        claim2 = ResourceClaim(
            colony_id="colony-1",  # 同じColony
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        assert conflict is None

    def test_release_claim(self):
        """リソース要求を解放"""
        detector = ConflictDetector()

        claim = ResourceClaim(
            colony_id="colony-1",
            resource_type="file",
            resource_id="/file.py",
            operation="write",
        )
        detector.register_claim(claim)

        result = detector.release_claim("colony-1", "/file.py")
        assert result is True

        result2 = detector.release_claim("colony-1", "/file.py")
        assert result2 is False

    def test_get_conflicts(self):
        """衝突一覧"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        detector.register_claim(claim2)

        conflicts = detector.get_conflicts()
        assert len(conflicts) == 1

    def test_mark_resolved(self):
        """衝突を解決済みに"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = detector.mark_resolved(conflict.conflict_id, "Merged changes")
        assert result is True

        unresolved = detector.get_conflicts(include_resolved=False)
        assert len(unresolved) == 0

    def test_conflict_listener(self):
        """衝突リスナー"""
        detected = []
        detector = ConflictDetector()
        detector.add_conflict_listener(lambda c: detected.append(c))

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        detector.register_claim(claim2)

        assert len(detected) == 1

    def test_get_claims_by_colony(self):
        """Colony別要求一覧"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file1.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file2.py", operation="write"
        )
        claim3 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file3.py", operation="write"
        )

        detector.register_claim(claim1)
        detector.register_claim(claim2)
        detector.register_claim(claim3)

        claims = detector.get_claims_by_colony("colony-1")
        assert len(claims) == 2

    def test_get_stats(self):
        """統計情報"""
        detector = ConflictDetector()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        detector.register_claim(claim2)

        stats = detector.get_stats()
        assert stats["total_conflicts"] == 1
        assert stats["unresolved_conflicts"] == 1

    def test_clear_all(self):
        """全クリア"""
        detector = ConflictDetector()

        claim = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        detector.register_claim(claim)

        detector.clear_all()

        stats = detector.get_stats()
        assert stats["total_resources"] == 0

    def test_high_severity_multiple_colonies(self):
        """3つ以上のColonyで HIGH 判定"""
        detector = ConflictDetector()

        for i in range(3):
            claim = ResourceClaim(
                colony_id=f"colony-{i}",
                resource_type="file",
                resource_id="/file.py",
                operation="write",
            )
            conflict = detector.register_claim(claim)

        # 最後のregister_claimで衝突が返る
        assert conflict is not None
        assert conflict.severity == ConflictSeverity.HIGH
