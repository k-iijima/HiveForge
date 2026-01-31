"""Run関連のMCPハンドラー

Run開始、完了、状態取得、ハートビート、緊急停止を担当。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...core import build_run_projection, generate_event_id
from ...core.events import (
    HeartbeatEvent,
    EmergencyStopEvent,
    RunCompletedEvent,
    RunStartedEvent,
    TaskFailedEvent,
)
from ...core.ar.projections import TaskState
from .base import BaseHandler


class RunHandlers(BaseHandler):
    """Run関連ハンドラー"""

    async def handle_start_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run開始"""
        ar = self._get_ar()
        run_id = generate_event_id()
        goal = args.get("goal", "")

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

        if incomplete_tasks and not force:
            task_ids = [t.id for t in incomplete_tasks]
            return {
                "error": "Cannot complete run with incomplete tasks",
                "incomplete_task_ids": task_ids,
                "hint": "強制完了する場合は force=true を指定してください",
            }

        cancelled_task_ids = []
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

        event = RunCompletedEvent(
            run_id=run_id,
            actor="copilot",
            payload={"summary": args.get("summary", "")},
        )
        ar.append(event, run_id)

        self._current_run_id = None

        result = {
            "status": "completed",
            "run_id": run_id,
            "summary": args.get("summary", ""),
        }
        if cancelled_task_ids:
            result["cancelled_task_ids"] = cancelled_task_ids
        return result

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def handle_emergency_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        """緊急停止"""
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()
        reason = args.get("reason", "No reason provided")
        scope = args.get("scope", "run")

        event = EmergencyStopEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={"reason": reason, "scope": scope},
        )
        ar.append(event, self._current_run_id)

        run_id = self._current_run_id
        self._current_run_id = None

        return {
            "status": "aborted",
            "run_id": run_id,
            "reason": reason,
            "scope": scope,
            "stopped_at": datetime.now(timezone.utc).isoformat(),
        }
