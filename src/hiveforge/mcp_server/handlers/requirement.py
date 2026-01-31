"""Requirement関連のMCPハンドラー

確認要請の作成を担当。
"""

from __future__ import annotations

from typing import Any

from ...core import generate_event_id
from ...core.events import RequirementCreatedEvent
from .base import BaseHandler


class RequirementHandlers(BaseHandler):
    """Requirement関連ハンドラー"""

    async def handle_create_requirement(self, args: dict[str, Any]) -> dict[str, Any]:
        """要件作成"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        ar = self._get_ar()
        req_id = generate_event_id()

        event = RequirementCreatedEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={
                "requirement_id": req_id,
                "description": args.get("description", ""),
                "options": args.get("options", []),
            },
        )
        ar.append(event, self._current_run_id)

        return {
            "status": "created",
            "requirement_id": req_id,
            "description": args.get("description", ""),
            "message": "ユーザーの承認を待っています。",
        }
