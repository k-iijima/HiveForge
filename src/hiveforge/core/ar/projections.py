"""投影 (Projections) モジュール

イベントストリームから現在の状態を計算する投影機能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..events import BaseEvent, EventType


class TaskState(str, Enum):
    """タスク状態"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class RunState(str, Enum):
    """Run状態"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class RequirementState(str, Enum):
    """要件状態"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class TaskProjection:
    """タスクの現在状態"""

    id: str
    title: str
    state: TaskState = TaskState.PENDING
    assignee: str | None = None
    progress: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequirementProjection:
    """要件の現在状態"""

    id: str
    description: str
    state: RequirementState = RequirementState.PENDING
    created_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunProjection:
    """Runの現在状態"""

    id: str
    goal: str
    state: RunState = RunState.RUNNING
    tasks: dict[str, TaskProjection] = field(default_factory=dict)
    requirements: dict[str, RequirementProjection] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat: datetime | None = None
    event_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def pending_tasks(self) -> list[TaskProjection]:
        """未完了タスクを取得"""
        return [t for t in self.tasks.values() if t.state == TaskState.PENDING]

    @property
    def in_progress_tasks(self) -> list[TaskProjection]:
        """進行中タスクを取得"""
        return [t for t in self.tasks.values() if t.state == TaskState.IN_PROGRESS]

    @property
    def completed_tasks(self) -> list[TaskProjection]:
        """完了タスクを取得"""
        return [t for t in self.tasks.values() if t.state == TaskState.COMPLETED]

    @property
    def blocked_tasks(self) -> list[TaskProjection]:
        """ブロック中タスクを取得"""
        return [t for t in self.tasks.values() if t.state == TaskState.BLOCKED]

    @property
    def pending_requirements(self) -> list[RequirementProjection]:
        """未決定の要件を取得"""
        return [r for r in self.requirements.values() if r.state == RequirementState.PENDING]


class RunProjector:
    """Runの投影を計算するプロジェクター"""

    def __init__(self, run_id: str, goal: str = ""):
        self.projection = RunProjection(id=run_id, goal=goal)

    def apply(self, event: BaseEvent) -> RunProjection:
        """イベントを適用して投影を更新

        Args:
            event: 適用するイベント

        Returns:
            更新後の投影
        """
        self.projection.event_count += 1
        handler = getattr(self, f"_handle_{event.type.value.replace('.', '_')}", None)
        if handler:
            handler(event)
        return self.projection

    def _handle_run_started(self, event: BaseEvent) -> None:
        self.projection.state = RunState.RUNNING
        self.projection.started_at = event.timestamp
        self.projection.goal = event.payload.get("goal", self.projection.goal)

    def _handle_run_completed(self, event: BaseEvent) -> None:
        self.projection.state = RunState.COMPLETED
        self.projection.completed_at = event.timestamp

    def _handle_run_failed(self, event: BaseEvent) -> None:
        self.projection.state = RunState.FAILED
        self.projection.completed_at = event.timestamp

    def _handle_run_aborted(self, event: BaseEvent) -> None:
        self.projection.state = RunState.ABORTED
        self.projection.completed_at = event.timestamp

    def _handle_task_created(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id:
            self.projection.tasks[task_id] = TaskProjection(
                id=task_id,
                title=event.payload.get("title", ""),
                state=TaskState.PENDING,
                created_at=event.timestamp,
                updated_at=event.timestamp,
                metadata=event.payload.get("metadata", {}),
            )

    def _handle_task_assigned(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            task.state = TaskState.IN_PROGRESS
            task.assignee = event.payload.get("assignee")
            task.updated_at = event.timestamp

    def _handle_task_progressed(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            task.progress = event.payload.get("progress", task.progress)
            task.updated_at = event.timestamp

    def _handle_task_completed(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            task.state = TaskState.COMPLETED
            task.progress = 100
            task.completed_at = event.timestamp
            task.updated_at = event.timestamp

    def _handle_task_failed(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            task.state = TaskState.FAILED
            task.error_message = event.payload.get("error")
            task.updated_at = event.timestamp

    def _handle_task_blocked(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            task.state = TaskState.BLOCKED
            task.updated_at = event.timestamp

    def _handle_task_unblocked(self, event: BaseEvent) -> None:
        task_id = event.task_id
        if task_id and task_id in self.projection.tasks:
            task = self.projection.tasks[task_id]
            # ブロック解除後はIN_PROGRESSに戻す
            task.state = TaskState.IN_PROGRESS
            task.updated_at = event.timestamp

    def _handle_requirement_created(self, event: BaseEvent) -> None:
        req_id = event.payload.get("requirement_id")
        if req_id:
            self.projection.requirements[req_id] = RequirementProjection(
                id=req_id,
                description=event.payload.get("description", ""),
                state=RequirementState.PENDING,
                created_at=event.timestamp,
            )

    def _handle_requirement_approved(self, event: BaseEvent) -> None:
        req_id = event.payload.get("requirement_id")
        if req_id and req_id in self.projection.requirements:
            req = self.projection.requirements[req_id]
            req.state = RequirementState.APPROVED
            req.decided_at = event.timestamp
            req.decided_by = event.actor

    def _handle_requirement_rejected(self, event: BaseEvent) -> None:
        req_id = event.payload.get("requirement_id")
        if req_id and req_id in self.projection.requirements:
            req = self.projection.requirements[req_id]
            req.state = RequirementState.REJECTED
            req.decided_at = event.timestamp
            req.decided_by = event.actor

    def _handle_system_heartbeat(self, event: BaseEvent) -> None:
        self.projection.last_heartbeat = event.timestamp


def build_run_projection(events: list[BaseEvent], run_id: str, goal: str = "") -> RunProjection:
    """イベントリストからRun投影を構築

    Args:
        events: イベントのリスト
        run_id: Run ID
        goal: Runの目標

    Returns:
        構築された投影
    """
    projector = RunProjector(run_id, goal)
    for event in events:
        projector.apply(event)
    return projector.projection
