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


# Conflict Resolver テスト
from hiveforge.beekeeper.resolver import (
    ResolutionStrategy,
    ResolutionStatus,
    ResolutionResult,
    MergeRule,
    ConflictResolver,
)


class TestResolutionResult:
    """ResolutionResultの基本テスト"""

    def test_create_result(self):
        """解決結果を作成"""
        result = ResolutionResult(
            conflict_id="conflict-1",
            strategy=ResolutionStrategy.FIRST_COME,
        )

        assert result.resolution_id is not None
        assert result.status == ResolutionStatus.PENDING


class TestConflictResolver:
    """ConflictResolverのテスト"""

    def test_resolve_first_come(self):
        """先着優先で解決"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.FIRST_COME)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.winner_colony_id == "colony-1"

    def test_resolve_priority_based(self):
        """優先度ベースで解決"""
        detector = ConflictDetector()
        resolver = ConflictResolver()
        resolver.set_colony_priority("colony-1", 10)
        resolver.set_colony_priority("colony-2", 20)

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.PRIORITY_BASED)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.winner_colony_id == "colony-2"  # 優先度が高い

    def test_resolve_abort_all(self):
        """全キャンセル"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.ABORT_ALL)

        assert result.status == ResolutionStatus.RESOLVED
        assert "aborted_colonies" in result.metadata

    def test_resolve_lock_and_queue(self):
        """ロック＆キュー"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.LOCK_AND_QUEUE)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.winner_colony_id == "colony-1"
        assert "queued_colonies" in result.metadata

    def test_resolve_manual(self):
        """手動解決"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.MANUAL)

        assert result.status == ResolutionStatus.ESCALATED

    def test_resolve_merge_no_rule(self):
        """マージルールなし"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.MERGE)

        assert result.status == ResolutionStatus.ESCALATED

    def test_resolve_merge_with_rule(self):
        """マージルールあり"""
        detector = ConflictDetector()
        resolver = ConflictResolver()
        resolver.add_merge_rule(MergeRule(resource_type="file", merge_function="append"))

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.MERGE)

        assert result.status == ResolutionStatus.RESOLVED

    def test_resolve_retry_later(self):
        """リトライ"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict, ResolutionStrategy.RETRY_LATER)

        assert result.status == ResolutionStatus.PENDING

    def test_set_strategy(self):
        """デフォルト戦略設定"""
        resolver = ConflictResolver()
        resolver.set_strategy(ConflictType.FILE_CONFLICT, ResolutionStrategy.MANUAL)

        detector = ConflictDetector()
        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        result = resolver.resolve(conflict)  # strategy指定なし

        assert result.strategy == ResolutionStrategy.MANUAL

    def test_resolution_listener(self):
        """解決リスナー"""
        resolved = []
        resolver = ConflictResolver()
        resolver.add_resolution_listener(lambda r: resolved.append(r))

        detector = ConflictDetector()
        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        resolver.resolve(conflict)

        assert len(resolved) == 1

    def test_get_stats(self):
        """統計情報"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        resolver.resolve(conflict, ResolutionStrategy.FIRST_COME)

        stats = resolver.get_stats()
        assert stats["total"] == 1
        assert stats["resolved"] == 1

    def test_get_pending_resolutions(self):
        """未解決一覧"""
        detector = ConflictDetector()
        resolver = ConflictResolver()

        claim1 = ResourceClaim(
            colony_id="colony-1", resource_type="file", resource_id="/file.py", operation="write"
        )
        claim2 = ResourceClaim(
            colony_id="colony-2", resource_type="file", resource_id="/file.py", operation="write"
        )

        detector.register_claim(claim1)
        conflict = detector.register_claim(claim2)

        resolver.resolve(conflict, ResolutionStrategy.MANUAL)

        pending = resolver.get_pending_resolutions()
        assert len(pending) == 1  # ESCALATEDも含む


# Conference テスト
from hiveforge.beekeeper.conference import (
    ConferenceSession,
    ConferenceStatus,
    ConferenceAgenda,
    ConferenceManager,
    Opinion,
    Vote,
    VoteType,
)


class TestConferenceSession:
    """ConferenceSessionの基本テスト"""

    def test_create_session(self):
        """セッション作成"""
        session = ConferenceSession(
            hive_id="hive-1",
            topic="APIデザイン",
            participants=["colony-1", "colony-2"],
        )

        assert session.session_id is not None
        assert session.status == ConferenceStatus.PENDING

    def test_is_active(self):
        """アクティブ状態チェック"""
        session = ConferenceSession()
        assert not session.is_active()

        session.status = ConferenceStatus.IN_PROGRESS
        assert session.is_active()


class TestConferenceManager:
    """ConferenceManagerのテスト"""

    def test_create_and_start_session(self):
        """セッション作成と開始"""
        manager = ConferenceManager()

        session = manager.create_session(
            hive_id="hive-1",
            topic="設計レビュー",
            participants=["colony-1", "colony-2", "colony-3"],
        )

        result = manager.start_session(session.session_id)

        assert result is True
        assert session.status == ConferenceStatus.IN_PROGRESS

    def test_submit_opinion(self):
        """意見提出"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2"],
        )
        manager.start_session(session.session_id)

        opinion = manager.submit_opinion(
            session.session_id,
            colony_id="colony-1",
            content="RESTよりGraphQLを推奨",
            rationale="柔軟なクエリが可能",
        )

        assert opinion is not None
        assert len(session.opinions) == 1

    def test_submit_opinion_not_participant(self):
        """参加者以外は意見提出不可"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1"],
        )
        manager.start_session(session.session_id)

        opinion = manager.submit_opinion(
            session.session_id,
            colony_id="colony-99",  # 参加者ではない
            content="意見",
        )

        assert opinion is None

    def test_voting(self):
        """投票"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2"],
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)

        vote = manager.cast_vote(
            session.session_id,
            colony_id="colony-1",
            vote_type=VoteType.APPROVE,
        )

        assert vote is not None
        assert len(session.votes) == 1

    def test_vote_replaces_previous(self):
        """再投票で上書き"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1"],
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)

        manager.cast_vote(session.session_id, "colony-1", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-1", VoteType.REJECT)

        assert len(session.votes) == 1
        assert session.votes[0].vote_type == VoteType.REJECT

    def test_conclude_session(self):
        """会議結論"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2"],
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)
        manager.cast_vote(session.session_id, "colony-1", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-2", VoteType.APPROVE)

        result = manager.conclude_session(session.session_id)

        assert result is True
        assert session.status == ConferenceStatus.CONCLUDED
        assert "Approved" in session.conclusion

    def test_conclude_rejected(self):
        """否決"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2", "colony-3"],
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)
        manager.cast_vote(session.session_id, "colony-1", VoteType.REJECT)
        manager.cast_vote(session.session_id, "colony-2", VoteType.REJECT)
        manager.cast_vote(session.session_id, "colony-3", VoteType.APPROVE)

        manager.conclude_session(session.session_id)

        assert "Rejected" in session.conclusion

    def test_cancel_session(self):
        """会議キャンセル"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1"],
        )
        manager.start_session(session.session_id)

        result = manager.cancel_session(session.session_id, "時間切れ")

        assert result is True
        assert session.status == ConferenceStatus.CANCELLED

    def test_get_vote_summary(self):
        """投票サマリ"""
        manager = ConferenceManager()
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2", "colony-3"],
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)
        manager.cast_vote(session.session_id, "colony-1", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-2", VoteType.REJECT)

        summary = manager.get_vote_summary(session.session_id)

        assert summary["approve"] == 1
        assert summary["reject"] == 1
        assert summary["pending"] == 1

    def test_get_active_sessions(self):
        """進行中セッション一覧"""
        manager = ConferenceManager()
        s1 = manager.create_session(hive_id="hive-1", topic="t1", participants=["c1"])
        s2 = manager.create_session(hive_id="hive-1", topic="t2", participants=["c2"])

        manager.start_session(s1.session_id)

        active = manager.get_active_sessions()
        assert len(active) == 1

    def test_listeners(self):
        """リスナー"""
        started = []
        concluded = []
        manager = ConferenceManager()
        manager.add_listener(
            on_started=lambda s: started.append(s),
            on_concluded=lambda s: concluded.append(s),
        )

        session = manager.create_session(hive_id="hive-1", topic="t", participants=["c1"])
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)
        manager.cast_vote(session.session_id, "c1", VoteType.APPROVE)
        manager.conclude_session(session.session_id)

        assert len(started) == 1
        assert len(concluded) == 1

    def test_get_stats(self):
        """統計情報"""
        manager = ConferenceManager()
        s1 = manager.create_session(hive_id="hive-1", topic="t1", participants=["c1"])
        s2 = manager.create_session(hive_id="hive-1", topic="t2", participants=["c2"])

        manager.start_session(s1.session_id)
        manager.start_voting(s1.session_id)
        manager.cast_vote(s1.session_id, "c1", VoteType.APPROVE)
        manager.conclude_session(s1.session_id)

        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["concluded"] == 1

    def test_consensus_required(self):
        """全員一致必要"""
        manager = ConferenceManager()
        agenda = ConferenceAgenda(
            title="重要決定",
            requires_consensus=True,
        )
        session = manager.create_session(
            hive_id="hive-1",
            topic="テスト",
            participants=["colony-1", "colony-2"],
            agenda=agenda,
        )
        manager.start_session(session.session_id)
        manager.start_voting(session.session_id)
        manager.cast_vote(session.session_id, "colony-1", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-2", VoteType.REJECT)

        manager.conclude_session(session.session_id)

        assert "No consensus" in session.conclusion
