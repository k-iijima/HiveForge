"""投影 (Projections) のテスト"""

from hiveforge.core.ar.projections import (
    RequirementProjection,
    RequirementState,
    RunProjection,
    RunProjector,
    RunState,
    TaskProjection,
    TaskState,
    build_run_projection,
)
from hiveforge.core.events import (
    EventType,
    HeartbeatEvent,
    RequirementApprovedEvent,
    RequirementCreatedEvent,
    RequirementRejectedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    TaskAssignedEvent,
    TaskBlockedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskProgressedEvent,
)


class TestRunProjector:
    """RunProjectorのテスト"""

    def test_run_started(self):
        """Run開始イベントの適用"""
        projector = RunProjector("run-001")

        event = RunStartedEvent(
            run_id="run-001",
            payload={"goal": "Build something"},
        )
        projector.apply(event)

        assert projector.projection.state == RunState.RUNNING
        assert projector.projection.goal == "Build something"
        assert projector.projection.started_at == event.timestamp

    def test_run_completed(self):
        """Run完了イベントの適用"""
        projector = RunProjector("run-001")

        # 開始
        projector.apply(RunStartedEvent(run_id="run-001", payload={"goal": "Test"}))

        # 完了
        event = RunCompletedEvent(run_id="run-001")
        projector.apply(event)

        assert projector.projection.state == RunState.COMPLETED
        assert projector.projection.completed_at == event.timestamp

    def test_task_lifecycle(self):
        """タスクのライフサイクル"""
        projector = RunProjector("run-001")

        # タスク作成
        create_event = TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"title": "First Task"},
        )
        projector.apply(create_event)

        task = projector.projection.tasks.get("task-001")
        assert task is not None
        assert task.state == TaskState.PENDING
        assert task.title == "First Task"

        # タスク割り当て
        assign_event = TaskAssignedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"assignee": "copilot"},
        )
        projector.apply(assign_event)

        assert task.state == TaskState.IN_PROGRESS
        assert task.assignee == "copilot"

        # タスク完了
        complete_event = TaskCompletedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"result": "Done"},
        )
        projector.apply(complete_event)

        assert task.state == TaskState.COMPLETED
        assert task.progress == 100

    def test_task_failure(self):
        """タスク失敗"""
        projector = RunProjector("run-001")

        # タスク作成
        projector.apply(
            TaskCreatedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"title": "Failing Task"},
            )
        )

        # タスク割り当て
        projector.apply(
            TaskAssignedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"assignee": "copilot"},
            )
        )

        # タスク失敗
        projector.apply(
            TaskFailedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"error": "Something went wrong"},
            )
        )

        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.FAILED
        assert task.error_message == "Something went wrong"

    def test_requirement_lifecycle(self):
        """要件のライフサイクル"""
        projector = RunProjector("run-001")

        # 要件作成
        projector.apply(
            RequirementCreatedEvent(
                run_id="run-001",
                payload={
                    "requirement_id": "req-001",
                    "description": "Use TypeScript?",
                },
            )
        )

        req = projector.projection.requirements.get("req-001")
        assert req is not None
        assert req.state == RequirementState.PENDING

        # 要件承認
        projector.apply(
            RequirementApprovedEvent(
                run_id="run-001",
                actor="human",
                payload={"requirement_id": "req-001"},
            )
        )

        assert req.state == RequirementState.APPROVED
        assert req.decided_by == "human"

    def test_run_failed(self):
        """Run失敗イベントの適用"""
        # Arrange: 開始済みのRun
        projector = RunProjector("run-001")
        projector.apply(RunStartedEvent(run_id="run-001", payload={"goal": "Test"}))

        # Act: 失敗イベントを適用
        event = RunFailedEvent(run_id="run-001", payload={"error": "Critical error"})
        projector.apply(event)

        # Assert: 状態がFAILEDに
        assert projector.projection.state == RunState.FAILED
        assert projector.projection.completed_at == event.timestamp

    def test_run_aborted(self):
        """Run中断イベントの適用"""
        # Arrange: 開始済みのRun
        projector = RunProjector("run-001")
        projector.apply(RunStartedEvent(run_id="run-001", payload={"goal": "Test"}))

        # Act: 中断イベント (RUN_ABORTEDイベント)
        from hiveforge.core.events import BaseEvent

        abort_event = BaseEvent(type=EventType.RUN_ABORTED, run_id="run-001")
        projector.apply(abort_event)

        # Assert: 状態がABORTEDに
        assert projector.projection.state == RunState.ABORTED
        assert projector.projection.completed_at == abort_event.timestamp

    def test_emergency_stop(self):
        """緊急停止イベントの適用

        system.emergency_stopイベントが発行されたとき、
        RunはABORTED状態になることを確認。
        """
        # Arrange: 開始済みのRun
        projector = RunProjector("run-001")
        projector.apply(RunStartedEvent(run_id="run-001", payload={"goal": "Test"}))
        assert projector.projection.state == RunState.RUNNING

        # Act: 緊急停止イベント
        from hiveforge.core.events import EmergencyStopEvent

        stop_event = EmergencyStopEvent(
            run_id="run-001",
            actor="api",
            payload={"reason": "ユーザーによる緊急停止", "scope": "run"},
        )
        projector.apply(stop_event)

        # Assert: 状態がABORTEDに、完了時刻が記録される
        assert projector.projection.state == RunState.ABORTED
        assert projector.projection.completed_at == stop_event.timestamp

    def test_task_progressed(self):
        """タスク進捗イベントの適用"""
        # Arrange: 進行中のタスク
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(run_id="run-001", task_id="task-001", payload={"title": "Task"})
        )
        projector.apply(
            TaskAssignedEvent(run_id="run-001", task_id="task-001", payload={"assignee": "copilot"})
        )

        # Act: 進捗イベントを適用
        progress_event = TaskProgressedEvent(
            run_id="run-001", task_id="task-001", payload={"progress": 50}
        )
        projector.apply(progress_event)

        # Assert: 進捗が更新される
        task = projector.projection.tasks["task-001"]
        assert task.progress == 50
        assert task.updated_at == progress_event.timestamp

    def test_task_blocked_and_unblocked(self):
        """タスクのブロック/アンブロック"""
        # Arrange: 進行中のタスク
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(run_id="run-001", task_id="task-001", payload={"title": "Task"})
        )
        projector.apply(
            TaskAssignedEvent(run_id="run-001", task_id="task-001", payload={"assignee": "copilot"})
        )

        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.IN_PROGRESS

        # Act: ブロックイベント
        projector.apply(
            TaskBlockedEvent(
                run_id="run-001", task_id="task-001", payload={"reason": "Waiting for human"}
            )
        )
        assert task.state == TaskState.BLOCKED

        # Act: アンブロックイベント (TASK_UNBLOCKEDイベントを手動で作成)
        from hiveforge.core.events import BaseEvent

        unblock_event = BaseEvent(
            type=EventType.TASK_UNBLOCKED, run_id="run-001", task_id="task-001"
        )
        projector.apply(unblock_event)

        # Assert: 進行中に戻る
        assert task.state == TaskState.IN_PROGRESS

    def test_requirement_rejected(self):
        """要件拒否イベントの適用"""
        # Arrange: 保留中の要件
        projector = RunProjector("run-001")
        projector.apply(
            RequirementCreatedEvent(
                run_id="run-001",
                payload={"requirement_id": "req-001", "description": "Use Python 2?"},
            )
        )

        req = projector.projection.requirements["req-001"]
        assert req.state == RequirementState.PENDING

        # Act: 拒否イベント
        reject_event = RequirementRejectedEvent(
            run_id="run-001",
            actor="human",
            payload={"requirement_id": "req-001"},
        )
        projector.apply(reject_event)

        # Assert: 拒否状態に
        assert req.state == RequirementState.REJECTED
        assert req.decided_by == "human"

    def test_heartbeat_event(self):
        """ハートビートイベントの適用"""
        # Arrange: 開始済みのRun
        projector = RunProjector("run-001")
        projector.apply(RunStartedEvent(run_id="run-001", payload={"goal": "Test"}))

        # Act: ハートビートイベント
        heartbeat = HeartbeatEvent(run_id="run-001")
        projector.apply(heartbeat)

        # Assert: 最終ハートビート時刻が更新される
        assert projector.projection.last_heartbeat == heartbeat.timestamp

    def test_unknown_event_type_is_ignored(self):
        """未知のイベントタイプは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")
        initial_count = projector.projection.event_count

        # Act: LLM_REQUESTなど、ハンドラがないイベントを適用
        from hiveforge.core.events import BaseEvent

        unknown_event = BaseEvent(type=EventType.LLM_REQUEST, run_id="run-001")
        projector.apply(unknown_event)

        # Assert: カウントは増えるが、他の状態は変わらない
        assert projector.projection.event_count == initial_count + 1

    def test_task_event_without_task_id_is_ignored(self):
        """task_idがないタスクイベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: task_idがNoneのイベント
        event = TaskCreatedEvent(run_id="run-001", task_id=None, payload={"title": "No ID"})
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_event_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへのイベントは無視される"""
        # Arrange: プロジェクター（タスクなし）
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへの完了イベント
        event = TaskCompletedEvent(run_id="run-001", task_id="nonexistent", payload={})
        projector.apply(event)

        # Assert: エラーにならず、タスクも作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_assigned_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへの割り当てイベントは無視される"""
        # Arrange: プロジェクター（タスクなし）
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへの割り当てイベント
        event = TaskAssignedEvent(
            run_id="run-001", task_id="nonexistent", payload={"assignee": "copilot"}
        )
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_progressed_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへの進捗イベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへの進捗イベント
        event = TaskProgressedEvent(
            run_id="run-001", task_id="nonexistent", payload={"progress": 50}
        )
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_failed_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへの失敗イベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへの失敗イベント
        event = TaskFailedEvent(run_id="run-001", task_id="nonexistent", payload={"error": "Error"})
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_blocked_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへのブロックイベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへのブロックイベント
        event = TaskBlockedEvent(run_id="run-001", task_id="nonexistent", payload={})
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_task_unblocked_for_nonexistent_task_is_ignored(self):
        """存在しないタスクへのアンブロックイベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: 存在しないタスクへのアンブロックイベント
        from hiveforge.core.events import BaseEvent

        event = BaseEvent(type=EventType.TASK_UNBLOCKED, run_id="run-001", task_id="nonexistent")
        projector.apply(event)

        # Assert: タスクは作成されない
        assert len(projector.projection.tasks) == 0

    def test_requirement_approved_for_nonexistent_is_ignored(self):
        """存在しない要件への承認イベントは無視される"""
        # Arrange: プロジェクター（要件なし）
        projector = RunProjector("run-001")

        # Act: 存在しない要件への承認イベント
        event = RequirementApprovedEvent(
            run_id="run-001", payload={"requirement_id": "nonexistent"}
        )
        projector.apply(event)

        # Assert: 要件は作成されない
        assert len(projector.projection.requirements) == 0

    def test_requirement_rejected_for_nonexistent_is_ignored(self):
        """存在しない要件への拒否イベントは無視される"""
        # Arrange: プロジェクター（要件なし）
        projector = RunProjector("run-001")

        # Act: 存在しない要件への拒否イベント
        event = RequirementRejectedEvent(
            run_id="run-001", payload={"requirement_id": "nonexistent"}
        )
        projector.apply(event)

        # Assert: 要件は作成されない
        assert len(projector.projection.requirements) == 0

    def test_requirement_created_without_id_is_ignored(self):
        """requirement_idがない要件作成イベントは無視される"""
        # Arrange: プロジェクター
        projector = RunProjector("run-001")

        # Act: requirement_idがないイベント
        event = RequirementCreatedEvent(run_id="run-001", payload={"description": "No ID"})
        projector.apply(event)

        # Assert: 要件は作成されない
        assert len(projector.projection.requirements) == 0

    def test_task_completed_result_saved_to_metadata(self):
        """タスク完了時のresultがmetadataに保存される

        Worker Beeの実行結果（output）がTaskProjectionに反映されることで、
        投影だけで完了タスクの成果物を確認できる。
        """
        # Arrange: タスクを作成
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"title": "Build login page"},
            )
        )

        # Act: resultとworker_idを含む完了イベントを適用
        projector.apply(
            TaskCompletedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={
                    "result": "Created login.html with form validation",
                    "worker_id": "worker-bee-1",
                },
            )
        )

        # Assert: resultとworker_idがmetadataに保存される
        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.COMPLETED
        assert task.metadata["result"] == "Created login.html with form validation"
        assert task.metadata["worker_id"] == "worker-bee-1"

    def test_task_completed_without_result_no_metadata_pollution(self):
        """resultがないタスク完了イベントではmetadataが汚染されない

        MCP経由やシンプルな完了イベントではresultが空文字の場合がある。
        その場合はmetadataに空文字を入れない。
        """
        # Arrange: タスクを作成
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"title": "Simple task"},
            )
        )

        # Act: resultなしの完了イベント
        projector.apply(
            TaskCompletedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={},
            )
        )

        # Assert: metadataにresultキーが追加されていない
        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.COMPLETED
        assert "result" not in task.metadata
        assert "worker_id" not in task.metadata

    def test_task_completed_preserves_existing_metadata(self):
        """タスク完了時に既存のmetadataが保持される

        タスク作成時に設定されたmetadata（priority等）が
        完了イベントで上書きされないことを確認。
        """
        # Arrange: metadataつきでタスクを作成
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={
                    "title": "Important task",
                    "metadata": {"priority": "high", "category": "frontend"},
                },
            )
        )

        # Act: resultつきの完了イベント
        projector.apply(
            TaskCompletedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"result": "Done", "worker_id": "worker-1"},
            )
        )

        # Assert: 既存のmetadataが保持され、resultが追加される
        task = projector.projection.tasks["task-001"]
        assert task.metadata["priority"] == "high"
        assert task.metadata["category"] == "frontend"
        assert task.metadata["result"] == "Done"
        assert task.metadata["worker_id"] == "worker-1"

    def test_task_failed_error_details_in_metadata(self):
        """タスク失敗時のworker_idがmetadataに保存される

        失敗タスクのworker_idを記録することで、
        どのWorkerが失敗したかをtask投影から追跡できる。
        """
        # Arrange: タスクを作成
        projector = RunProjector("run-001")
        projector.apply(
            TaskCreatedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={"title": "Risky task"},
            )
        )

        # Act: worker_idつきの失敗イベント
        projector.apply(
            TaskFailedEvent(
                run_id="run-001",
                task_id="task-001",
                payload={
                    "error": "Compilation failed",
                    "worker_id": "worker-bee-2",
                },
            )
        )

        # Assert: error_messageとmetadata.worker_idが保存される
        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.FAILED
        assert task.error_message == "Compilation failed"
        assert task.metadata["worker_id"] == "worker-bee-2"


class TestBuildRunProjection:
    """build_run_projection関数のテスト"""

    def test_build_from_events(self):
        """イベントリストから投影を構築"""
        events = [
            RunStartedEvent(run_id="run-001", payload={"goal": "Test Goal"}),
            TaskCreatedEvent(run_id="run-001", task_id="task-001", payload={"title": "Task 1"}),
            TaskCreatedEvent(run_id="run-001", task_id="task-002", payload={"title": "Task 2"}),
            TaskAssignedEvent(
                run_id="run-001", task_id="task-001", payload={"assignee": "copilot"}
            ),
            TaskCompletedEvent(run_id="run-001", task_id="task-001", payload={}),
        ]

        projection = build_run_projection(events, "run-001")

        assert projection.id == "run-001"
        assert projection.goal == "Test Goal"
        assert projection.event_count == 5
        assert len(projection.tasks) == 2
        assert len(projection.completed_tasks) == 1
        assert len(projection.pending_tasks) == 1


class TestProjectionProperties:
    """投影のプロパティのテスト"""

    def test_pending_tasks(self):
        """保留中タスクの取得"""
        projection = RunProjection(id="run-001", goal="Test")
        projection.tasks["task-001"] = TaskProjection(
            id="task-001", title="A", state=TaskState.PENDING
        )
        projection.tasks["task-002"] = TaskProjection(
            id="task-002", title="B", state=TaskState.IN_PROGRESS
        )
        projection.tasks["task-003"] = TaskProjection(
            id="task-003", title="C", state=TaskState.PENDING
        )

        pending = projection.pending_tasks
        assert len(pending) == 2

    def test_completed_tasks(self):
        """完了タスクの取得"""
        projection = RunProjection(id="run-001", goal="Test")
        projection.tasks["task-001"] = TaskProjection(
            id="task-001", title="A", state=TaskState.COMPLETED
        )
        projection.tasks["task-002"] = TaskProjection(
            id="task-002", title="B", state=TaskState.PENDING
        )

        completed = projection.completed_tasks
        assert len(completed) == 1
        assert completed[0].id == "task-001"

    def test_in_progress_tasks(self):
        """進行中タスクの取得"""
        # Arrange: 異なる状態のタスクを持つ投影
        projection = RunProjection(id="run-001", goal="Test")
        projection.tasks["task-001"] = TaskProjection(
            id="task-001", title="A", state=TaskState.IN_PROGRESS
        )
        projection.tasks["task-002"] = TaskProjection(
            id="task-002", title="B", state=TaskState.PENDING
        )
        projection.tasks["task-003"] = TaskProjection(
            id="task-003", title="C", state=TaskState.IN_PROGRESS
        )

        # Act: 進行中タスクを取得
        in_progress = projection.in_progress_tasks

        # Assert: 進行中のタスクが2件
        assert len(in_progress) == 2

    def test_blocked_tasks(self):
        """ブロック中タスクの取得"""
        # Arrange: ブロック状態のタスクを含む投影
        projection = RunProjection(id="run-001", goal="Test")
        projection.tasks["task-001"] = TaskProjection(
            id="task-001", title="A", state=TaskState.BLOCKED
        )
        projection.tasks["task-002"] = TaskProjection(
            id="task-002", title="B", state=TaskState.IN_PROGRESS
        )

        # Act: ブロック中タスクを取得
        blocked = projection.blocked_tasks

        # Assert: ブロック中のタスクが1件
        assert len(blocked) == 1
        assert blocked[0].id == "task-001"

    def test_pending_requirements(self):
        """未決定の要件の取得"""
        # Arrange: 異なる状態の要件を持つ投影
        projection = RunProjection(id="run-001", goal="Test")
        projection.requirements["req-001"] = RequirementProjection(
            id="req-001", description="A", state=RequirementState.PENDING
        )
        projection.requirements["req-002"] = RequirementProjection(
            id="req-002", description="B", state=RequirementState.APPROVED
        )
        projection.requirements["req-003"] = RequirementProjection(
            id="req-003", description="C", state=RequirementState.PENDING
        )

        # Act: 未決定の要件を取得
        pending = projection.pending_requirements

        # Assert: 未決定の要件が2件
        assert len(pending) == 2


class TestHiveAggregate:
    """HiveAggregate のテスト

    Hive集約はイベント列からHiveとColonyの状態を投影する。
    """

    def test_apply_hive_created_event(self):
        """HiveCreatedEventの適用

        Hive作成イベントで集約が初期化される。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import HiveCreatedEvent

        aggregate = HiveAggregate("hive-001")

        # Act: Hive作成イベントを適用
        event = HiveCreatedEvent(
            actor="beekeeper",
            payload={"hive_id": "hive-001", "name": "Test Hive"},
        )
        aggregate.apply(event)

        # Assert: 状態がACTIVEで、名前が設定される
        from hiveforge.core.ar.projections import HiveState

        assert aggregate.state == HiveState.ACTIVE
        assert aggregate.name == "Test Hive"

    def test_apply_colony_created_event(self):
        """ColonyCreatedEventの適用

        Colony作成イベントでColonyが登録される。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import ColonyCreatedEvent, HiveCreatedEvent

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))

        # Act: Colony作成イベントを適用
        event = ColonyCreatedEvent(
            actor="queen_bee",
            payload={"colony_id": "colony-001", "hive_id": "hive-001", "goal": "Build feature X"},
        )
        aggregate.apply(event)

        # Assert: Colonyが登録される
        assert "colony-001" in aggregate.colonies
        colony = aggregate.colonies["colony-001"]
        assert colony.goal == "Build feature X"
        from hiveforge.core.ar.projections import ColonyState

        assert colony.state == ColonyState.PENDING

    def test_apply_colony_started_event(self):
        """ColonyStartedEventの適用

        Colony開始イベントでColonyの状態がIN_PROGRESSになる。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import ColonyCreatedEvent, ColonyStartedEvent, HiveCreatedEvent

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))
        aggregate.apply(
            ColonyCreatedEvent(payload={"colony_id": "colony-001", "hive_id": "hive-001"})
        )

        # Act: Colony開始イベントを適用
        event = ColonyStartedEvent(payload={"colony_id": "colony-001"})
        aggregate.apply(event)

        # Assert: ColonyがIN_PROGRESSになる
        assert aggregate.colonies["colony-001"].state == ColonyState.IN_PROGRESS

    def test_apply_colony_completed_event(self):
        """ColonyCompletedEventの適用

        Colony完了イベントでColonyの状態がCOMPLETEDになる。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import (
            ColonyCompletedEvent,
            ColonyCreatedEvent,
            ColonyStartedEvent,
            HiveCreatedEvent,
        )

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))
        aggregate.apply(
            ColonyCreatedEvent(payload={"colony_id": "colony-001", "hive_id": "hive-001"})
        )
        aggregate.apply(ColonyStartedEvent(payload={"colony_id": "colony-001"}))

        # Act: Colony完了イベントを適用
        event = ColonyCompletedEvent(payload={"colony_id": "colony-001"})
        aggregate.apply(event)

        # Assert: ColonyがCOMPLETEDになる
        assert aggregate.colonies["colony-001"].state == ColonyState.COMPLETED

    def test_apply_colony_failed_event(self):
        """ColonyFailedEventの適用

        Colony失敗イベントでColonyの状態がFAILEDになる。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.ar.projections import ColonyState
        from hiveforge.core.events import (
            ColonyCreatedEvent,
            ColonyFailedEvent,
            ColonyStartedEvent,
            HiveCreatedEvent,
        )

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))
        aggregate.apply(
            ColonyCreatedEvent(payload={"colony_id": "colony-001", "hive_id": "hive-001"})
        )
        aggregate.apply(ColonyStartedEvent(payload={"colony_id": "colony-001"}))

        # Act: Colony失敗イベントを適用
        event = ColonyFailedEvent(payload={"colony_id": "colony-001", "error": "Critical error"})
        aggregate.apply(event)

        # Assert: ColonyがFAILEDになる
        assert aggregate.colonies["colony-001"].state == ColonyState.FAILED
        assert aggregate.colonies["colony-001"].error == "Critical error"

    def test_apply_hive_closed_event(self):
        """HiveClosedEventの適用

        Hive終了イベントでHiveの状態がCLOSEDになる。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.ar.projections import HiveState
        from hiveforge.core.events import HiveClosedEvent, HiveCreatedEvent

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))

        # Act: Hive終了イベントを適用
        event = HiveClosedEvent(payload={"hive_id": "hive-001", "reason": "completed"})
        aggregate.apply(event)

        # Assert: HiveがCLOSEDになる
        assert aggregate.state == HiveState.CLOSED

    def test_build_from_events(self):
        """イベント列からHive集約を構築

        複数のイベントを順に適用してHive状態を再構築する。
        """
        # Arrange
        from hiveforge.core.ar.hive_projections import build_hive_aggregate
        from hiveforge.core.ar.projections import ColonyState, HiveState
        from hiveforge.core.events import (
            ColonyCompletedEvent,
            ColonyCreatedEvent,
            ColonyStartedEvent,
            HiveCreatedEvent,
        )

        events = [
            HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test Hive"}),
            ColonyCreatedEvent(
                payload={"colony_id": "colony-001", "hive_id": "hive-001", "goal": "Goal 1"}
            ),
            ColonyCreatedEvent(
                payload={"colony_id": "colony-002", "hive_id": "hive-001", "goal": "Goal 2"}
            ),
            ColonyStartedEvent(payload={"colony_id": "colony-001"}),
            ColonyCompletedEvent(payload={"colony_id": "colony-001"}),
        ]

        # Act: イベント列から集約を構築
        aggregate = build_hive_aggregate("hive-001", events)

        # Assert: 状態が正しく反映される
        assert aggregate.state == HiveState.ACTIVE
        assert len(aggregate.colonies) == 2
        assert aggregate.colonies["colony-001"].state == ColonyState.COMPLETED
        assert aggregate.colonies["colony-002"].state == ColonyState.PENDING

    def test_active_colonies_property(self):
        """アクティブなColony一覧を取得"""
        # Arrange
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import (
            ColonyCompletedEvent,
            ColonyCreatedEvent,
            ColonyStartedEvent,
            HiveCreatedEvent,
        )

        aggregate = HiveAggregate("hive-001")
        aggregate.apply(HiveCreatedEvent(payload={"hive_id": "hive-001", "name": "Test"}))
        aggregate.apply(
            ColonyCreatedEvent(payload={"colony_id": "colony-001", "hive_id": "hive-001"})
        )
        aggregate.apply(
            ColonyCreatedEvent(payload={"colony_id": "colony-002", "hive_id": "hive-001"})
        )
        aggregate.apply(ColonyStartedEvent(payload={"colony_id": "colony-001"}))
        aggregate.apply(ColonyCompletedEvent(payload={"colony_id": "colony-001"}))

        # Act: アクティブなColonyを取得
        active = aggregate.active_colonies

        # Assert: PENDING の colony-002 のみ（IN_PROGRESS もアクティブだが今回はPENDINGのみ）
        # 実際には PENDING と IN_PROGRESS の両方がアクティブ
        assert len(active) == 1
        assert active[0].colony_id == "colony-002"


class TestRunColonyProjectionNullHandling:
    """RunColonyProjection のNull分岐テスト"""

    def test_apply_non_run_started_ignored(self):
        """RUN_STARTED以外のイベントは無視される"""
        from hiveforge.core.events import TaskCreatedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"title": "Test"},
        )

        # Act
        proj.apply(event)

        # Assert: 何も変わらない
        assert len(proj.orphan_runs) == 0
        assert len(proj.colony_runs) == 0

    def test_apply_run_started_with_none_run_id_ignored(self):
        """run_id=NoneのRUN_STARTEDは無視される"""
        from hiveforge.core.events import RunStartedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = RunStartedEvent(
            run_id=None,  # type: ignore
            colony_id="colony-001",
            payload={"goal": "Test"},
        )

        # Act
        proj.apply(event)

        # Assert
        assert len(proj.orphan_runs) == 0
        assert len(proj.colony_runs) == 0

    def test_apply_run_started_without_colony_id_added_to_orphans(self):
        """colony_id=NoneのRunはorphan_runsに追加される"""
        from hiveforge.core.events import RunStartedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = RunStartedEvent(
            run_id="run-001",
            colony_id=None,
            payload={"goal": "Test"},
        )

        # Act
        proj.apply(event)

        # Assert
        assert "run-001" in proj.orphan_runs
        assert len(proj.colony_runs) == 0

    def test_apply_run_started_with_colony_id_added_to_colony_runs(self):
        """colony_id付きRunはcolony_runsに追加される"""
        from hiveforge.core.events import RunStartedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = RunStartedEvent(
            run_id="run-001",
            colony_id="colony-001",
            payload={"goal": "Test"},
        )

        # Act
        proj.apply(event)

        # Assert
        assert "run-001" in proj.colony_runs["colony-001"]

    def test_duplicate_run_not_added_twice_to_orphans(self):
        """同じrunが2回orphansに追加されない"""
        from hiveforge.core.events import RunStartedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = RunStartedEvent(run_id="run-001", colony_id=None, payload={"goal": "Test"})

        # Act
        proj.apply(event)
        proj.apply(event)  # 2回目

        # Assert
        assert proj.orphan_runs.count("run-001") == 1

    def test_duplicate_run_not_added_twice_to_colony_runs(self):
        """同じrunが2回colony_runsに追加されない"""
        from hiveforge.core.events import RunStartedEvent
        from hiveforge.core.state.projections import RunColonyProjection

        proj = RunColonyProjection()
        event = RunStartedEvent(run_id="run-001", colony_id="col-001", payload={"goal": "Test"})

        # Act
        proj.apply(event)
        proj.apply(event)

        # Assert
        assert proj.colony_runs["col-001"].count("run-001") == 1


class TestHiveAggregateEdgeCases:
    """HiveAggregate の境界ケーステスト"""

    def test_unknown_event_type_ignored(self):
        """未知のイベントタイプは無視される

        _handlersに登録されていないイベントタイプを適用しても
        例外が発生せず、状態も変化しない。
        """
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import RunStartedEvent

        # Arrange
        aggregate = HiveAggregate("hive-001")

        # Act: HiveAggregateが処理しないRUN_STARTEDイベントを適用
        event = RunStartedEvent(
            run_id="run-001",
            actor="test",
            payload={"goal": "test"},
        )
        aggregate.apply(event)

        # Assert: エラーなし、デフォルト状態のまま（HiveCreatedを適用していないので）
        from hiveforge.core.ar.projections import HiveState

        assert aggregate.state == HiveState.ACTIVE

    def test_colony_created_empty_id_ignored(self):
        """colony_idが空のColonyCreatedは無視される"""
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import ColonyCreatedEvent

        # Arrange
        aggregate = HiveAggregate("hive-001")

        # Act: colony_idが空
        event = ColonyCreatedEvent(
            actor="queen",
            payload={"colony_id": "", "name": "Empty"},
        )
        aggregate.apply(event)

        # Assert: コロニーは登録されない
        assert len(aggregate.projection.colonies) == 0

    def test_colony_started_nonexistent_ignored(self):
        """存在しないColonyのStartedイベントは無視される"""
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import ColonyStartedEvent

        # Arrange
        aggregate = HiveAggregate("hive-001")

        # Act: 存在しないcolonyのstarted
        event = ColonyStartedEvent(
            actor="queen",
            payload={"colony_id": "nonexistent"},
        )
        aggregate.apply(event)

        # Assert: エラーなし
        assert len(aggregate.projection.colonies) == 0

    def test_colony_completed_nonexistent_ignored(self):
        """存在しないColonyのCompletedイベントは無視される"""
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import ColonyCompletedEvent

        aggregate = HiveAggregate("hive-001")
        event = ColonyCompletedEvent(
            actor="queen",
            payload={"colony_id": "nonexistent"},
        )
        aggregate.apply(event)
        assert len(aggregate.projection.colonies) == 0

    def test_colony_failed_nonexistent_ignored(self):
        """存在しないColonyのFailedイベントは無視される"""
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import ColonyFailedEvent

        aggregate = HiveAggregate("hive-001")
        event = ColonyFailedEvent(
            actor="queen",
            payload={"colony_id": "nonexistent", "error": "err"},
        )
        aggregate.apply(event)
        assert len(aggregate.projection.colonies) == 0

    def test_colony_suspended_nonexistent_ignored(self):
        """存在しないColonyのSuspendedイベントは無視される"""
        from hiveforge.core.ar.hive_projections import HiveAggregate
        from hiveforge.core.events import BaseEvent, EventType

        aggregate = HiveAggregate("hive-001")
        event = BaseEvent(
            type=EventType.COLONY_SUSPENDED,
            actor="sentinel",
            payload={"colony_id": "nonexistent"},
        )
        aggregate.apply(event)
        assert len(aggregate.projection.colonies) == 0
