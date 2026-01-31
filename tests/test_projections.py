"""投影 (Projections) のテスト"""

import pytest
from datetime import datetime, timezone

from hiveforge.core.ar.projections import (
    RunProjection,
    TaskProjection,
    RequirementProjection,
    RunProjector,
    build_run_projection,
    RunState,
    TaskState,
    RequirementState,
)
from hiveforge.core.events import (
    RunStartedEvent,
    RunCompletedEvent,
    TaskCreatedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    RequirementCreatedEvent,
    RequirementApprovedEvent,
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
        projector.apply(TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"title": "Failing Task"},
        ))

        # タスク割り当て
        projector.apply(TaskAssignedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"assignee": "copilot"},
        ))

        # タスク失敗
        projector.apply(TaskFailedEvent(
            run_id="run-001",
            task_id="task-001",
            payload={"error": "Something went wrong"},
        ))

        task = projector.projection.tasks["task-001"]
        assert task.state == TaskState.FAILED
        assert task.error_message == "Something went wrong"

    def test_requirement_lifecycle(self):
        """要件のライフサイクル"""
        projector = RunProjector("run-001")

        # 要件作成
        projector.apply(RequirementCreatedEvent(
            run_id="run-001",
            payload={
                "requirement_id": "req-001",
                "description": "Use TypeScript?",
            },
        ))

        req = projector.projection.requirements.get("req-001")
        assert req is not None
        assert req.state == RequirementState.PENDING

        # 要件承認
        projector.apply(RequirementApprovedEvent(
            run_id="run-001",
            actor="human",
            payload={"requirement_id": "req-001"},
        ))

        assert req.state == RequirementState.APPROVED
        assert req.decided_by == "human"


class TestBuildRunProjection:
    """build_run_projection関数のテスト"""

    def test_build_from_events(self):
        """イベントリストから投影を構築"""
        events = [
            RunStartedEvent(run_id="run-001", payload={"goal": "Test Goal"}),
            TaskCreatedEvent(run_id="run-001", task_id="task-001", payload={"title": "Task 1"}),
            TaskCreatedEvent(run_id="run-001", task_id="task-002", payload={"title": "Task 2"}),
            TaskAssignedEvent(run_id="run-001", task_id="task-001", payload={"assignee": "copilot"}),
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
        projection.tasks["task-001"] = TaskProjection(id="task-001", title="A", state=TaskState.PENDING)
        projection.tasks["task-002"] = TaskProjection(id="task-002", title="B", state=TaskState.IN_PROGRESS)
        projection.tasks["task-003"] = TaskProjection(id="task-003", title="C", state=TaskState.PENDING)

        pending = projection.pending_tasks
        assert len(pending) == 2

    def test_completed_tasks(self):
        """完了タスクの取得"""
        projection = RunProjection(id="run-001", goal="Test")
        projection.tasks["task-001"] = TaskProjection(id="task-001", title="A", state=TaskState.COMPLETED)
        projection.tasks["task-002"] = TaskProjection(id="task-002", title="B", state=TaskState.PENDING)

        completed = projection.completed_tasks
        assert len(completed) == 1
        assert completed[0].id == "task-001"
