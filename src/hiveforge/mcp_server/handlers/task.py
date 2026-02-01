"""Task関連のMCPハンドラー

Task作成、割り当て、進捗報告、完了、失敗を担当。
"""

from __future__ import annotations

from typing import Any

from ...core import generate_event_id
from ...core.events import (
    EventType,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskProgressedEvent,
)
from .base import BaseHandler


class TaskHandlers(BaseHandler):
    """Task関連ハンドラー"""

    def _get_run_started_event_id(self, run_id: str) -> str | None:
        ar = self._get_ar()
        for event in ar.replay(run_id):
            if event.type == EventType.RUN_STARTED:
                return event.id
        return None

    def _get_task_created_event_id(self, run_id: str, task_id: str) -> str | None:
        ar = self._get_ar()
        for event in ar.replay(run_id):
            if event.type == EventType.TASK_CREATED and event.task_id == task_id:
                return event.id
        return None

    async def handle_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task作成"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = generate_event_id()

        parents = args.get("parents", [])
        if not parents:
            run_started_id = self._get_run_started_event_id(self._current_run_id)
            if run_started_id:
                parents = [run_started_id]

        event = TaskCreatedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            parents=parents,
            payload={
                "title": args.get("title", ""),
                "description": args.get("description", ""),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "created",
            "task_id": task_id,
            "title": args.get("title", ""),
        }

    async def handle_assign_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task割り当て"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")
        if not task_id:
            return {"error": "task_id is required"}

        parents = args.get("parents", [])
        if not parents:
            created_id = self._get_task_created_event_id(self._current_run_id, task_id)
            if created_id:
                parents = [created_id]

        event = TaskAssignedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            parents=parents,
            payload={"assignee": "copilot"},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "assigned",
            "task_id": task_id,
        }

    async def handle_report_progress(self, args: dict[str, Any]) -> dict[str, Any]:
        """進捗報告"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")
        progress = args.get("progress", 0)

        if not task_id:
            return {"error": "task_id is required"}

        parents = args.get("parents", [])
        if not parents:
            created_id = self._get_task_created_event_id(self._current_run_id, task_id)
            if created_id:
                parents = [created_id]

        event = TaskProgressedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            parents=parents,
            payload={
                "progress": progress,
                "message": args.get("message", ""),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "progressed",
            "task_id": task_id,
            "progress": progress,
        }

    async def handle_complete_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task完了"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")

        if not task_id:
            return {"error": "task_id is required"}

        parents = args.get("parents", [])
        if not parents:
            created_id = self._get_task_created_event_id(self._current_run_id, task_id)
            if created_id:
                parents = [created_id]

        event = TaskCompletedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            parents=parents,
            payload={"result": args.get("result", "")},
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "completed",
            "task_id": task_id,
        }

    async def handle_fail_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Task失敗"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        task_id = args.get("task_id")

        if not task_id:
            return {"error": "task_id is required"}

        parents = args.get("parents", [])
        if not parents:
            created_id = self._get_task_created_event_id(self._current_run_id, task_id)
            if created_id:
                parents = [created_id]

        event = TaskFailedEvent(
            run_id=self._current_run_id,
            task_id=task_id,
            actor="copilot",
            parents=parents,
            payload={
                "error": args.get("error", ""),
                "retryable": args.get("retryable", True),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "failed",
            "task_id": task_id,
            "error": args.get("error", ""),
        }
