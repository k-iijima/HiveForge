"""Queen Bee タスクディスパッチャ

Queen BeeがWorker Beeにタスクを割り当てる機能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.events import WorkerAssignedEvent
from ..worker_bee.projections import (
    WorkerPoolProjection,
    WorkerProjection,
    WorkerState,
    build_worker_pool_projection,
)
from .server import QueenBeeMCPServer, ManagedWorker


@dataclass
class TaskAssignment:
    """タスク割り当て情報"""

    task_id: str
    worker_id: str
    run_id: str
    goal: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDispatcher:
    """タスクディスパッチャ

    Queen BeeがWorker Beeにタスクを割り当てる。
    """

    ar: AkashicRecord
    _worker_pool: WorkerPoolProjection = field(default_factory=WorkerPoolProjection)

    def register_worker(self, worker_id: str) -> None:
        """Worker Beeを登録"""
        if worker_id not in self._worker_pool.workers:
            self._worker_pool.workers[worker_id] = WorkerProjection(worker_id=worker_id)

    def unregister_worker(self, worker_id: str) -> None:
        """Worker Beeを登録解除"""
        if worker_id in self._worker_pool.workers:
            del self._worker_pool.workers[worker_id]

    def get_available_workers(self) -> list[WorkerProjection]:
        """利用可能なWorker Beeを取得"""
        return self._worker_pool.get_idle_workers()

    def get_worker_count(self) -> int:
        """登録Worker数"""
        return self._worker_pool.total_workers

    def assign_task(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        context: dict[str, Any] | None = None,
        preferred_worker_id: str | None = None,
    ) -> TaskAssignment | None:
        """タスクをWorker Beeに割り当て

        Args:
            task_id: タスクID
            run_id: Run ID
            goal: タスクの目標
            context: タスクコンテキスト
            preferred_worker_id: 優先するWorker ID（指定時はそのWorkerに割り当て）

        Returns:
            TaskAssignment: 割り当て成功時
            None: 利用可能なWorkerがない場合
        """
        context = context or {}

        # 優先Workerが指定されていて利用可能な場合
        if preferred_worker_id:
            worker = self._worker_pool.get_worker(preferred_worker_id)
            if worker and worker.state == WorkerState.IDLE:
                return self._do_assign(task_id, run_id, goal, context, worker)

        # 利用可能なWorkerを取得
        available = self.get_available_workers()
        if not available:
            return None

        # 最も完了タスクが多いWorkerを選択（経験豊富）
        worker = max(available, key=lambda w: len(w.completed_tasks))
        return self._do_assign(task_id, run_id, goal, context, worker)

    def _do_assign(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        context: dict[str, Any],
        worker: WorkerProjection,
    ) -> TaskAssignment:
        """実際の割り当て処理"""
        # イベントを発行
        event = WorkerAssignedEvent(
            id=generate_event_id(),
            run_id=run_id,
            task_id=task_id,
            worker_id=worker.worker_id,
            actor="queen",
            payload={"goal": goal, "context": context},
        )
        self.ar.append(event, run_id)

        # Worker状態を更新（割り当て済み = WORKING）
        worker.state = WorkerState.WORKING
        worker.current_task_id = task_id
        worker.current_run_id = run_id

        return TaskAssignment(
            task_id=task_id,
            worker_id=worker.worker_id,
            run_id=run_id,
            goal=goal,
            context=context,
        )

    def bulk_assign(
        self,
        tasks: list[dict[str, Any]],
        run_id: str,
    ) -> list[TaskAssignment]:
        """複数タスクを一括割り当て

        Args:
            tasks: タスクリスト [{"task_id": ..., "goal": ..., "context": ...}, ...]
            run_id: Run ID

        Returns:
            成功した割り当てリスト
        """
        assignments: list[TaskAssignment] = []

        for task in tasks:
            assignment = self.assign_task(
                task_id=task["task_id"],
                run_id=run_id,
                goal=task.get("goal", ""),
                context=task.get("context", {}),
            )
            if assignment:
                assignments.append(assignment)

        return assignments

    def reassign_task(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        failed_worker_id: str,
        context: dict[str, Any] | None = None,
    ) -> TaskAssignment | None:
        """失敗したタスクを別のWorkerに再割り当て

        Args:
            task_id: タスクID
            run_id: Run ID
            goal: タスクの目標
            failed_worker_id: 失敗したWorkerのID（除外対象）
            context: タスクコンテキスト

        Returns:
            TaskAssignment: 再割り当て成功時
            None: 代替Workerがない場合
        """
        context = context or {}

        # 失敗したWorker以外で利用可能なWorkerを探す
        available = [w for w in self.get_available_workers() if w.worker_id != failed_worker_id]

        if not available:
            return None

        worker = available[0]
        return self._do_assign(task_id, run_id, goal, context, worker)
