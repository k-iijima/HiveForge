"""Run関連のMCPハンドラー

Run開始、完了、状態取得、ハートビート、緊急停止を担当。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core import build_run_projection, generate_event_id
from ...core.ar.projections import TaskState
from ...core.events import (
    EmergencyStopEvent,
    EventType,
    HeartbeatEvent,
    RequirementRejectedEvent,
    RunCompletedEvent,
    RunStartedEvent,
    TaskFailedEvent,
)
from .base import BaseHandler


class RunHandlers(BaseHandler):
    """Run関連ハンドラー"""

    def _get_task_completed_event_ids(self, run_id: str, task_ids: set[str]) -> list[str]:
        if not task_ids:
            return []
        ar = self._get_ar()
        parents: list[str] = []
        for event in ar.replay(run_id):
            if event.type == EventType.TASK_COMPLETED and event.task_id in task_ids:
                parents.append(event.id)
        return parents

    async def handle_start_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run開始"""
        goal = args.get("goal", "").strip()
        if not goal:
            return {"error": "goal is required and must not be empty"}

        ar = self._get_ar()
        run_id = generate_event_id()

        event = RunStartedEvent(
            run_id=run_id,
            actor="copilot",
            payload={"goal": goal},
        )
        ar.append(event, run_id)

        self._current_run_id = run_id

        return {
            "status": "started",
            "run_id": run_id,
            "goal": goal,
            "message": f"Run '{run_id}' を開始しました。目標: {goal}",
        }

    async def handle_get_run_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run状態取得"""
        ar = self._get_ar()
        run_id = args.get("run_id") or self._current_run_id

        if not run_id:
            return {"error": "No active run. Use start_run first."}

        events = list(ar.replay(run_id))
        if not events:
            return {"error": f"Run {run_id} not found"}

        proj = build_run_projection(events, run_id)

        pending_tasks = [{"id": t.id, "title": t.title} for t in proj.pending_tasks]
        in_progress_tasks = [
            {"id": t.id, "title": t.title, "progress": t.progress, "assignee": t.assignee}
            for t in proj.in_progress_tasks
        ]
        completed_tasks = [{"id": t.id, "title": t.title} for t in proj.completed_tasks]
        blocked_tasks = [{"id": t.id, "title": t.title} for t in proj.blocked_tasks]
        pending_reqs = [
            {"id": r.id, "description": r.description} for r in proj.pending_requirements
        ]

        return {
            "run_id": run_id,
            "goal": proj.goal,
            "state": proj.state.value,
            "event_count": proj.event_count,
            "tasks": {
                "pending": pending_tasks,
                "in_progress": in_progress_tasks,
                "completed": completed_tasks,
                "blocked": blocked_tasks,
            },
            "pending_requirements": pending_reqs,
            "last_heartbeat": proj.last_heartbeat.isoformat() if proj.last_heartbeat else None,
        }

    async def handle_complete_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run完了

        未完了タスクがある場合はエラーを返す。
        force=trueで強制完了する場合、未完了タスクは自動的にキャンセルされる。
        """
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()
        run_id = self._current_run_id
        force = args.get("force", False)

        # プロジェクションを構築して未完了タスクをチェック
        events = list(ar.replay(run_id))
        proj = build_run_projection(events, run_id)

        incomplete_tasks = [
            task
            for task in proj.tasks.values()
            if task.state not in (TaskState.COMPLETED, TaskState.FAILED)
        ]

        # 未解決の確認要請をチェック
        pending_requirements = list(proj.pending_requirements)

        if (incomplete_tasks or pending_requirements) and not force:
            result: dict[str, Any] = {
                "error": "Cannot complete run with incomplete tasks or pending requirements",
                "hint": "強制完了する場合は force=true を指定してください",
            }
            if incomplete_tasks:
                result["incomplete_task_ids"] = [t.id for t in incomplete_tasks]
            if pending_requirements:
                result["pending_requirement_ids"] = [r.id for r in pending_requirements]
            return result

        cancelled_task_ids = []
        cancelled_task_event_ids: list[str] = []
        if incomplete_tasks and force:
            # 強制完了: 未完了タスクを自動的にキャンセル
            for task in incomplete_tasks:
                fail_event = TaskFailedEvent(
                    run_id=run_id,
                    task_id=task.id,
                    actor="system",
                    payload={
                        "error": "Runが強制完了されたためキャンセル",
                        "retryable": False,
                    },
                )
                ar.append(fail_event, run_id)
                cancelled_task_ids.append(task.id)
                cancelled_task_event_ids.append(fail_event.id)

        # 強制完了時は未解決の確認要請も却下する
        cancelled_requirement_ids = []
        cancelled_requirement_event_ids: list[str] = []
        if force:
            for req in pending_requirements:
                reject_event = RequirementRejectedEvent(
                    run_id=run_id,
                    actor="system",
                    payload={
                        "requirement_id": req.id,
                        "comment": "Runが強制完了されたため却下",
                    },
                )
                ar.append(reject_event, run_id)
                cancelled_requirement_ids.append(req.id)
                cancelled_requirement_event_ids.append(reject_event.id)

        parents = args.get("parents", [])
        if not parents:
            completed_task_ids = {t.id for t in proj.completed_tasks}
            parents = self._get_task_completed_event_ids(run_id, completed_task_ids)
            if force:
                parents = parents + cancelled_task_event_ids + cancelled_requirement_event_ids

        event = RunCompletedEvent(
            run_id=run_id,
            actor="copilot",
            parents=parents,
            payload={"summary": args.get("summary", "")},
        )
        ar.append(event, run_id)

        self._current_run_id = None

        completion_result: dict[str, Any] = {
            "status": "completed",
            "run_id": run_id,
            "summary": args.get("summary", ""),
        }
        if cancelled_task_ids:
            completion_result["cancelled_task_ids"] = cancelled_task_ids
        if cancelled_requirement_ids:
            completion_result["cancelled_requirement_ids"] = cancelled_requirement_ids
        return completion_result

    async def handle_heartbeat(self, args: dict[str, Any]) -> dict[str, Any]:
        """ハートビート"""
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()

        event = HeartbeatEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={"message": args.get("message", "")},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def handle_emergency_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        """緊急停止

        進行中の全タスクを中断し、未解決の確認要請を却下し、Runを即座に停止する。
        """
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()
        run_id = self._current_run_id
        reason = args.get("reason", "No reason provided")
        scope = args.get("scope", "run")

        # プロジェクションを構築
        events = list(ar.replay(run_id))
        proj = build_run_projection(events, run_id)

        # 未完了タスクを全て失敗にする
        cancelled_task_ids = []
        incomplete_tasks = [
            task
            for task in proj.tasks.values()
            if task.state not in (TaskState.COMPLETED, TaskState.FAILED)
        ]
        for task in incomplete_tasks:
            fail_event = TaskFailedEvent(
                run_id=run_id,
                task_id=task.id,
                actor="system",
                payload={
                    "error": f"緊急停止: {reason}",
                    "retryable": False,
                },
            )
            ar.append(fail_event, run_id)
            cancelled_task_ids.append(task.id)

        # 未解決の確認要請を全て却下する
        cancelled_requirement_ids = []
        for req in proj.pending_requirements:
            reject_event = RequirementRejectedEvent(
                run_id=run_id,
                actor="system",
                payload={
                    "requirement_id": req.id,
                    "comment": f"緊急停止により却下: {reason}",
                },
            )
            ar.append(reject_event, run_id)
            cancelled_requirement_ids.append(req.id)

        event = EmergencyStopEvent(
            run_id=run_id,
            actor="copilot",
            payload={"reason": reason, "scope": scope},
        )
        ar.append(event, run_id)

        self._current_run_id = None

        result = {
            "status": "aborted",
            "run_id": run_id,
            "reason": reason,
            "scope": scope,
            "stopped_at": datetime.now(UTC).isoformat(),
        }
        if cancelled_task_ids:
            result["cancelled_task_ids"] = cancelled_task_ids
        if cancelled_requirement_ids:
            result["cancelled_requirement_ids"] = cancelled_requirement_ids
        return result
