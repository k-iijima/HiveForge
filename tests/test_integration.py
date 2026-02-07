"""統合テスト

Beekeeper ↔ Queen Bee ↔ Worker Bee のエンドツーエンド連携テスト。

既存の実装済みコンポーネントを使用した統合テスト。
"""

import pytest

from hiveforge.beekeeper.conference import ConferenceManager, VoteType
from hiveforge.beekeeper.conflict import ConflictDetector, ConflictType, ResourceClaim
from hiveforge.beekeeper.escalation import (
    EscalationManager,
    EscalationSeverity,
    EscalationType,
)
from hiveforge.beekeeper.resolver import ConflictResolver, ResolutionStrategy
from hiveforge.beekeeper.session import BeekeeperSession, SessionState
from hiveforge.core import AkashicRecord
from hiveforge.core.config import HiveForgeSettings
from hiveforge.core.events import (
    EventType,
    RunCompletedEvent,
    RunStartedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
)
from hiveforge.queen_bee.communication import ColonyMessenger, MessagePriority, MessageType
from hiveforge.queen_bee.progress import ProgressCollector, TaskProgress
from hiveforge.queen_bee.scheduler import ColonyPriority, ColonyScheduler
from hiveforge.worker_bee.process import WorkerProcess, WorkerProcessState
from hiveforge.worker_bee.retry import RetryExecutor, RetryPolicy, RetryStrategy
from hiveforge.worker_bee.tools import ToolCategory, ToolDefinition, ToolExecutor
from hiveforge.worker_bee.trust import ActionClass, TrustLevel, requires_confirmation


class TestIntegrationBasic:
    """基本的な統合テスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        """テスト用Akashic Record"""
        return AkashicRecord(vault_path=tmp_path)

    @pytest.fixture
    def settings(self):
        """テスト用設定"""
        return HiveForgeSettings()

    def test_config_loads_all_sections(self, settings):
        """設定が全セクション読み込める

        HiveForgeの設定が正しく読み込まれ、全セクションにアクセスできることを確認。
        """
        # Arrange & Act: 設定は fixture で読み込み済み

        # Assert: 全セクションが存在
        assert settings.hive is not None
        assert settings.governance is not None
        assert settings.agents is not None
        assert settings.conflict is not None
        assert settings.conference is not None

    def test_ar_can_store_events(self, ar):
        """ARにイベント保存できる

        AkashicRecordがイベントを正しく保存・取得できることを確認。
        """
        # Arrange
        run_id = "test-run-001"

        # Act: イベントを追加
        event = RunStartedEvent(
            run_id=run_id,
            payload={"goal": "Integration test run"},
        )
        ar.append(event, run_id)
        events = list(ar.replay(run_id))

        # Assert
        assert len(events) == 1
        assert events[0].type == EventType.RUN_STARTED


class TestBeekeeperIntegration:
    """Beekeeper統合テスト"""

    def test_beekeeper_session_lifecycle(self):
        """Beekeeperセッションのライフサイクル

        セッションの作成、アクティブ化、Colony追加、終了の一連の流れを確認。
        """
        # Arrange
        session = BeekeeperSession()

        # Assert: 初期状態
        assert session.state == SessionState.IDLE
        assert session.hive_id is None

        # Act: セッション開始
        session.activate("hive-001")

        # Assert
        assert session.state == SessionState.ACTIVE
        assert session.hive_id == "hive-001"

        # Act: Colony追加
        session.add_colony("colony-001", queen_bee_id="queen-001")

        # Assert
        assert "colony-001" in session.active_colonies

        # Act: 処理中に設定
        session.set_busy()
        assert session.state == SessionState.BUSY

        # Act: ユーザー待ちに設定
        session.set_waiting_user()
        assert session.state == SessionState.WAITING_USER

    def test_escalation_flow(self):
        """Escalationフロー

        Queen BeeからBeekeeperへの直訴（Escalation）の作成から解決までの流れを確認。
        """
        # Arrange
        manager = EscalationManager()

        # Act: Escalation作成
        escalation = manager.create_escalation(
            colony_id="colony-001",
            queen_bee_id="queen-001",
            escalation_type=EscalationType.RESOURCE_CONCERN,
            title="リソース不足",
            description="CPU使用率が90%を超えています",
            severity=EscalationSeverity.WARNING,
            context={"cpu_usage": 90},
        )

        # Assert
        assert escalation.escalation_id is not None
        assert escalation.colony_id == "colony-001"
        assert escalation.escalation_type == EscalationType.RESOURCE_CONCERN

        # Act: 確認済みに
        result = manager.acknowledge(escalation.escalation_id, "確認しました")
        assert result is True

        # Act: 解決
        result = manager.resolve(escalation.escalation_id, "リソースを追加割り当て")
        assert result is True


class TestQueenBeeIntegration:
    """Queen Bee統合テスト"""

    def test_scheduler_manages_colonies(self):
        """スケジューラがColonyを管理する

        Colony登録、優先度設定、リソース配分の流れを確認。
        """
        # Arrange
        scheduler = ColonyScheduler(total_workers=10)

        # Act: Colony登録
        scheduler.register_colony(
            colony_id="colony-001",
            priority=ColonyPriority.HIGH,
            max_workers=5,
        )
        scheduler.register_colony(
            colony_id="colony-002",
            priority=ColonyPriority.NORMAL,
            max_workers=3,
        )

        # Assert: 登録確認
        assert "colony-001" in scheduler._colonies
        assert "colony-002" in scheduler._colonies

        # Act: リソース配分
        allocations = scheduler.allocate_workers()

        # Assert: 優先度に応じた配分
        high_alloc = next((a for a in allocations if a.colony_id == "colony-001"), None)
        normal_alloc = next((a for a in allocations if a.colony_id == "colony-002"), None)

        assert high_alloc is not None
        assert normal_alloc is not None
        assert high_alloc.allocated_workers >= normal_alloc.allocated_workers

    def test_messenger_handles_messages(self):
        """メッセンジャーがメッセージを処理する

        Colony間のメッセージ送受信の流れを確認。
        """
        # Arrange
        messenger = ColonyMessenger()
        messenger.register_colony("colony-001")
        messenger.register_colony("colony-002")

        # Act: メッセージ送信
        msg_id = messenger.send(
            from_colony="colony-001",
            to_colony="colony-002",
            message_type=MessageType.REQUEST,
            payload={"task": "ファイル分析"},
            priority=MessagePriority.HIGH,
        )

        # Assert
        assert msg_id is not None

        # Act: メッセージ受信
        message = messenger.receive("colony-002")

        # Assert
        assert message is not None
        assert message.message_id == msg_id
        assert message.from_colony == "colony-001"

    def test_progress_collector(self):
        """進捗コレクターが進捗を集約する

        Worker Beeからの進捗報告を集約できることを確認。
        """
        # Arrange
        collector = ProgressCollector()

        # ProgressCollectorは内部状態を持つ
        # 直接タスク進捗を設定してテスト
        collector._task_progress["task-001"] = TaskProgress(
            task_id="task-001",
            worker_id="worker-001",
            progress=50,
            status="in_progress",
        )

        # Assert
        progress = collector.get_task_progress("task-001")
        assert progress is not None
        assert progress.progress == 50
        assert progress.status == "in_progress"


class TestWorkerBeeIntegration:
    """Worker Bee統合テスト"""

    def test_worker_process_state_lifecycle(self):
        """Workerプロセスの状態ライフサイクル

        WorkerProcessの状態遷移を確認。
        """
        # Arrange
        worker = WorkerProcess(
            worker_id="worker-001",
            colony_id="colony-001",
        )

        # Assert: 初期状態
        assert worker.state == WorkerProcessState.STOPPED
        assert not worker.is_running()

        # Act: 起動
        worker.state = WorkerProcessState.STARTING
        assert worker.is_running()

        # Act: 稼働中
        worker.state = WorkerProcessState.RUNNING
        assert worker.is_running()

        # Act: 停止
        worker.state = WorkerProcessState.STOPPED
        assert not worker.is_running()

    def test_tool_executor_registers_tools(self):
        """ツールエグゼキューターがツールを登録できる

        ツールの登録を確認。
        """
        # Arrange
        executor = ToolExecutor()

        tool = ToolDefinition(
            tool_id="echo-tool",
            name="echo",
            description="メッセージをエコーする",
            category=ToolCategory.CUSTOM,
        )

        # Act: 登録
        executor.register_tool(tool)

        # Assert: 登録確認
        assert executor.get_tool("echo-tool") is not None

    @pytest.mark.asyncio
    async def test_retry_executor_retries_on_failure(self):
        """リトライエグゼキューターが失敗時にリトライする

        一時的な失敗がリトライで成功することを確認。
        """
        # Arrange
        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED,
            max_retries=5,
            initial_delay=0.01,
        )
        executor = RetryExecutor(policy)

        # Act
        result = await executor.execute(flaky_operation)

        # Assert
        assert result.success
        assert call_count == 3  # 2回失敗 + 1回成功

    def test_trust_level_requires_confirmation(self):
        """信頼レベルが確認を要求する

        TrustLevelとActionClassの組み合わせで確認が必要かを判定できることを確認。
        """
        # Arrange & Act & Assert

        # SAFE操作はどの信頼レベルでも確認不要
        assert not requires_confirmation(TrustLevel.STANDARD, ActionClass.SAFE)
        assert not requires_confirmation(TrustLevel.ELEVATED, ActionClass.SAFE)

        # DANGEROUS操作はSTANDARDでは確認必要
        assert requires_confirmation(TrustLevel.STANDARD, ActionClass.DANGEROUS)

        # DANGEROUS操作はELEVATEDでは確認不要
        assert not requires_confirmation(TrustLevel.ELEVATED, ActionClass.DANGEROUS)


class TestConflictResolutionIntegration:
    """衝突検出・解決の統合テスト"""

    def test_conflict_detection_and_resolution(self):
        """衝突検出から解決まで

        リソース競合の検出と解決の流れを確認。
        """
        # Arrange
        detector = ConflictDetector()
        resolver = ConflictResolver()

        # Act: Colony1がファイルをクレーム
        claim1 = ResourceClaim(
            colony_id="colony-001",
            resource_type="file",
            resource_id="/src/main.py",
            operation="write",
        )
        conflict1 = detector.register_claim(claim1)

        # Assert: 最初は衝突なし
        assert conflict1 is None

        # Act: Colony2が同じファイルをクレーム → 衝突
        claim2 = ResourceClaim(
            colony_id="colony-002",
            resource_type="file",
            resource_id="/src/main.py",
            operation="write",
        )
        conflict2 = detector.register_claim(claim2)

        # Assert: 衝突検出
        assert conflict2 is not None
        assert conflict2.conflict_type == ConflictType.FILE_CONFLICT

        # Act: 衝突解決
        resolution = resolver.resolve(
            conflict2,
            strategy=ResolutionStrategy.FIRST_COME,
        )

        # Assert
        assert resolution.status.value == "resolved"
        assert resolution.winner_colony_id == "colony-001"


class TestConferenceIntegration:
    """Conference統合テスト"""

    def test_conference_voting_flow(self):
        """Conference投票フロー

        Conferenceの作成、意見提出、投票、結論までの流れを確認。
        """
        # Arrange
        manager = ConferenceManager()

        # Act: Conference作成
        session = manager.create_session(
            hive_id="hive-001",
            topic="APIフレームワーク選定",
            participants=["colony-001", "colony-002", "colony-003"],
        )

        # Assert
        assert session.session_id is not None
        assert session.topic == "APIフレームワーク選定"

        # Act: 会議開始
        manager.start_session(session.session_id)

        # Act: 意見提出
        opinion = manager.submit_opinion(
            session_id=session.session_id,
            colony_id="colony-001",
            content="FastAPIを推奨",
            rationale="型安全で高速",
        )
        assert opinion is not None

        # Act: 投票開始
        manager.start_voting(session.session_id)

        # Act: 投票
        manager.cast_vote(session.session_id, "colony-001", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-002", VoteType.APPROVE)
        manager.cast_vote(session.session_id, "colony-003", VoteType.ABSTAIN)

        # Act: Conference終了
        result = manager.conclude_session(session.session_id)

        # Assert
        assert result is True
        assert session.status.value == "concluded"

        # 投票結果確認
        approves = len([v for v in session.votes if v.vote_type == VoteType.APPROVE])
        abstains = len([v for v in session.votes if v.vote_type == VoteType.ABSTAIN])
        assert approves == 2
        assert abstains == 1


class TestEndToEndScenario:
    """エンドツーエンドシナリオテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path)

    def test_full_workflow_hive_to_task_completion(self, ar):
        """Hive作成からTask完了までの完全フロー

        Run開始 → Task作成 → Task実行 → 進捗報告 → Task完了 → Run完了の
        エンドツーエンドシナリオを確認。
        """
        # === Phase 1: Run/Task作成 ===

        run_id = "run-e2e-001"
        task_id = "task-e2e-001"

        # Run開始
        run_started = RunStartedEvent(
            run_id=run_id,
            payload={"goal": "E2Eテスト用Run"},
        )
        ar.append(run_started, run_id)

        # Task作成
        task_created = TaskCreatedEvent(
            run_id=run_id,
            task_id=task_id,
            payload={"title": "テストタスク実行"},
        )
        ar.append(task_created, run_id)

        # === Phase 2: Task実行 ===

        # Task開始
        task_assigned = TaskAssignedEvent(
            run_id=run_id,
            task_id=task_id,
            payload={"worker_id": "worker-001"},
        )
        ar.append(task_assigned, run_id)

        # Task完了
        task_completed = TaskCompletedEvent(
            run_id=run_id,
            task_id=task_id,
            payload={"result": {"output": "成功"}},
        )
        ar.append(task_completed, run_id)

        # === Phase 3: Run完了 ===

        run_completed = RunCompletedEvent(
            run_id=run_id,
            payload={"summary": "E2Eテスト完了"},
        )
        ar.append(run_completed, run_id)

        # === 検証 ===

        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        # イベントの存在確認
        assert EventType.RUN_STARTED in event_types
        assert EventType.TASK_CREATED in event_types
        assert EventType.TASK_ASSIGNED in event_types
        assert EventType.TASK_COMPLETED in event_types
        assert EventType.RUN_COMPLETED in event_types

        # イベント順序確認
        assert len(events) == 5

    def test_multi_colony_coordination(self):
        """複数Colony協調シナリオ

        複数のColonyが同時に作業し、リソース競合を解決するシナリオ。
        """
        # Arrange
        scheduler = ColonyScheduler(total_workers=10)
        detector = ConflictDetector()
        resolver = ConflictResolver()
        messenger = ColonyMessenger()

        # Colony登録
        scheduler.register_colony("colony-001", ColonyPriority.HIGH, max_workers=5)
        scheduler.register_colony("colony-002", ColonyPriority.NORMAL, max_workers=3)
        messenger.register_colony("colony-001")
        messenger.register_colony("colony-002")

        # リソース配分
        allocations = scheduler.allocate_workers()
        assert len(allocations) == 2

        # Colony間メッセージ
        msg_id = messenger.send(
            from_colony="colony-001",
            to_colony="colony-002",
            message_type=MessageType.NOTIFICATION,
            payload={"resource": "/shared/config.yaml"},
        )
        assert msg_id is not None

        # リソース競合
        claim1 = ResourceClaim(
            colony_id="colony-001",
            resource_type="file",
            resource_id="/shared/data.json",
            operation="write",
        )
        detector.register_claim(claim1)

        claim2 = ResourceClaim(
            colony_id="colony-002",
            resource_type="file",
            resource_id="/shared/data.json",
            operation="write",
        )
        conflict = detector.register_claim(claim2)

        # 競合解決
        assert conflict is not None
        resolution = resolver.resolve(conflict, ResolutionStrategy.FIRST_COME)
        assert resolution.status.value == "resolved"
