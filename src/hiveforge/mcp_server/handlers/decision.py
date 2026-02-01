"""Decision関連のMCPハンドラー

仕様変更や判断事項（Decision）をイベントとして記録する。
"""

from __future__ import annotations

from typing import Any

from ...core import generate_event_id
from ...core.events import DecisionRecordedEvent
from .base import BaseHandler


class DecisionHandlers(BaseHandler):
    """Decision関連ハンドラー"""

    async def handle_record_decision(self, args: dict[str, Any]) -> dict[str, Any]:
        """Decisionを記録"""
        if not self._current_run_id:
            return {"error": "No active run. Use start_run first."}

        decision_id = generate_event_id()

        event = DecisionRecordedEvent(
            run_id=self._current_run_id,
            actor="copilot",
            payload={
                "decision_id": decision_id,
                "key": args.get("key", ""),
                "title": args.get("title", ""),
                "rationale": args.get("rationale", ""),
                "options": args.get("options", []),
                "selected": args.get("selected", ""),
                "impact": args.get("impact", ""),
                "supersedes": args.get("supersedes", []),
            },
        )

        ar = self._get_ar()
        ar.append(event, self._current_run_id)

        return {
            "status": "recorded",
            "decision_id": decision_id,
            "key": args.get("key", ""),
            "title": args.get("title", ""),
            "selected": args.get("selected", ""),
        }
