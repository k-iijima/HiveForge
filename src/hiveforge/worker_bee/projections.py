"""Worker Bee Projection

イベントからWorker Beeの状態を投影する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..core.events import BaseEvent, EventType


class WorkerState(str, Enum):
    """Worker Beeの状態"""

    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class WorkerProjection:
    """Worker Beeの状態投影

    イベントから現在の状態を計算する。
    """

    worker_id: str
    state: WorkerState = WorkerState.IDLE
    current_task_id: str | None = None
    current_run_id: str | None = None
    progress: int = 0
    last_activity: datetime | None = None
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    error_message: str | None = None


def build_worker_projection(events: list[BaseEvent], worker_id: str) -> WorkerProjection:
    """イベントからWorker Projectionを構築

    Args:
        events: イベントリスト
        worker_id: 対象のWorker ID

    Returns:
        Worker Projection
    """
    projection = WorkerProjection(worker_id=worker_id)

    for event in events:
        _apply_event(projection, event)

    return projection


def _apply_event(projection: WorkerProjection, event: BaseEvent) -> None:
    """イベントを投影に適用"""
    # worker_idを持つイベントのみ処理
    if not hasattr(event, "worker_id"):
        return
    if event.worker_id != projection.worker_id:  # type: ignore
        return

    projection.last_activity = event.timestamp

    if event.type == EventType.WORKER_ASSIGNED:
        projection.state = WorkerState.IDLE
        projection.current_task_id = event.task_id
        projection.current_run_id = event.run_id

    elif event.type == EventType.WORKER_STARTED:
        projection.state = WorkerState.WORKING
        projection.current_task_id = event.task_id
        projection.current_run_id = event.run_id
        projection.progress = 0

    elif event.type == EventType.WORKER_PROGRESS:
        projection.progress = event.progress  # type: ignore

    elif event.type == EventType.WORKER_COMPLETED:
        if projection.current_task_id:
            projection.completed_tasks.append(projection.current_task_id)
        projection.state = WorkerState.IDLE
        projection.current_task_id = None
        projection.current_run_id = None
        projection.progress = 0

    elif event.type == EventType.WORKER_FAILED:
        if projection.current_task_id:
            projection.failed_tasks.append(projection.current_task_id)
        reason = getattr(event, "reason", "")
        projection.error_message = reason
        # recoverableかどうかでstateを分ける
        recoverable = event.payload.get("recoverable", True)
        projection.state = WorkerState.IDLE if recoverable else WorkerState.ERROR
        projection.current_task_id = None
        projection.current_run_id = None
        projection.progress = 0


@dataclass
class WorkerPoolProjection:
    """Worker Beeプールの状態投影

    全てのWorker Beeの状態を追跡する。
    """

    workers: dict[str, WorkerProjection] = field(default_factory=dict)

    def get_worker(self, worker_id: str) -> WorkerProjection | None:
        """Worker Projectionを取得"""
        return self.workers.get(worker_id)

    def get_idle_workers(self) -> list[WorkerProjection]:
        """IDLEのWorkerを取得"""
        return [w for w in self.workers.values() if w.state == WorkerState.IDLE]

    def get_working_workers(self) -> list[WorkerProjection]:
        """WORKING中のWorkerを取得"""
        return [w for w in self.workers.values() if w.state == WorkerState.WORKING]

    @property
    def total_workers(self) -> int:
        """全Worker数"""
        return len(self.workers)

    @property
    def idle_count(self) -> int:
        """IDLE Worker数"""
        return len(self.get_idle_workers())

    @property
    def working_count(self) -> int:
        """WORKING Worker数"""
        return len(self.get_working_workers())


def build_worker_pool_projection(
    events: list[BaseEvent],
) -> WorkerPoolProjection:
    """イベントからWorkerプール投影を構築"""
    pool = WorkerPoolProjection()

    for event in events:
        if not hasattr(event, "worker_id"):
            continue
        worker_id = event.worker_id  # type: ignore
        if worker_id not in pool.workers:
            pool.workers[worker_id] = WorkerProjection(worker_id=worker_id)
        _apply_event(pool.workers[worker_id], event)

    return pool
