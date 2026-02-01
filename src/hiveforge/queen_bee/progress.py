"""Queen Bee 進捗コレクター

Worker Beeからの進捗報告を集約し、全体進捗を計算する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import BaseEvent, EventType
from ..worker_bee.projections import WorkerPoolProjection, build_worker_pool_projection


@dataclass
class TaskProgress:
    """タスクごとの進捗情報"""

    task_id: str
    worker_id: str
    progress: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    result: str | None = None
    error: str | None = None


@dataclass
class ProgressCollector:
    """進捗コレクター

    複数Worker Beeからの進捗報告を集約する。
    """

    _task_progress: dict[str, TaskProgress] = field(default_factory=dict)
    _worker_pool: WorkerPoolProjection = field(default_factory=WorkerPoolProjection)

    def update_from_events(self, events: list[BaseEvent]) -> None:
        """イベントから進捗を更新"""
        self._worker_pool = build_worker_pool_projection(events)

        for event in events:
            self._process_event(event)

    def _process_event(self, event: BaseEvent) -> None:
        """個別イベントを処理"""
        task_id = event.task_id
        if not task_id:
            return

        if event.type == EventType.WORKER_ASSIGNED:
            worker_id = getattr(event, "worker_id", "unknown")
            self._task_progress[task_id] = TaskProgress(
                task_id=task_id,
                worker_id=worker_id,
                status="pending",
            )

        elif event.type == EventType.WORKER_STARTED:
            if task_id in self._task_progress:
                self._task_progress[task_id].status = "in_progress"

        elif event.type == EventType.WORKER_PROGRESS:
            if task_id in self._task_progress:
                progress = getattr(event, "progress", 0)
                self._task_progress[task_id].progress = progress

        elif event.type == EventType.WORKER_COMPLETED:
            if task_id in self._task_progress:
                self._task_progress[task_id].status = "completed"
                self._task_progress[task_id].progress = 100
                self._task_progress[task_id].result = event.payload.get("result", "")

        elif event.type == EventType.WORKER_FAILED:
            if task_id in self._task_progress:
                self._task_progress[task_id].status = "failed"
                reason = getattr(event, "reason", "Unknown error")
                self._task_progress[task_id].error = reason

    def get_task_progress(self, task_id: str) -> TaskProgress | None:
        """タスクの進捗を取得"""
        return self._task_progress.get(task_id)

    def get_all_progress(self) -> list[TaskProgress]:
        """全タスクの進捗を取得"""
        return list(self._task_progress.values())

    def get_overall_progress(self) -> int:
        """全体進捗を計算（0-100）"""
        if not self._task_progress:
            return 0

        total = sum(tp.progress for tp in self._task_progress.values())
        return total // len(self._task_progress)

    def get_completion_stats(self) -> dict[str, int]:
        """完了統計を取得"""
        stats = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
        }
        for tp in self._task_progress.values():
            if tp.status in stats:
                stats[tp.status] += 1
        return stats

    def is_all_completed(self) -> bool:
        """全タスクが完了したか"""
        if not self._task_progress:
            return False
        return all(tp.status in ("completed", "failed") for tp in self._task_progress.values())

    def get_failed_tasks(self) -> list[TaskProgress]:
        """失敗したタスクを取得"""
        return [tp for tp in self._task_progress.values() if tp.status == "failed"]

    def get_pending_tasks(self) -> list[TaskProgress]:
        """まだ開始していないタスクを取得"""
        return [tp for tp in self._task_progress.values() if tp.status == "pending"]

    def get_in_progress_tasks(self) -> list[TaskProgress]:
        """進行中のタスクを取得"""
        return [tp for tp in self._task_progress.values() if tp.status == "in_progress"]
