"""Lineage関連のMCPハンドラー

因果リンクの探索を担当。
"""

from __future__ import annotations

from typing import Any

from .base import BaseHandler


class LineageHandlers(BaseHandler):
    """Lineage関連ハンドラー"""

    async def handle_get_lineage(self, args: dict[str, Any]) -> dict[str, Any]:
        """因果リンクを取得"""
        if not self._current_run_id:
            return {"error": "No active run."}

        ar = self._get_ar()
        event_id = args.get("event_id")

        if not event_id:
            return {"error": "event_id is required"}

        direction = args.get("direction", "both")
        if direction not in ("ancestors", "descendants", "both"):
            return {
                "error": f"direction must be one of: ancestors, descendants, both (got '{direction}')"
            }

        max_depth = args.get("max_depth", 10)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 100:
            return {"error": "max_depth must be an integer between 1 and 100"}

        # 全イベントを取得してインデックス化
        all_events: dict[str, Any] = {}
        for event in ar.replay(self._current_run_id):
            all_events[event.id] = event

        if event_id not in all_events:
            return {"error": f"Event {event_id} not found"}

        ancestors: list[str] = []
        descendants: list[str] = []
        truncated = False

        # 祖先を探索（親方向）
        if direction in ("ancestors", "both"):
            visited: set[str] = set()
            queue = [(event_id, 0)]

            while queue:
                current_id, depth = queue.pop(0)
                if depth >= max_depth:
                    truncated = True
                    continue

                if current_id not in all_events:  # pragma: no cover (defensive check)
                    continue

                current_event = all_events[current_id]
                parents = getattr(current_event, "parents", [])

                for parent_id in parents:
                    if parent_id not in visited and parent_id in all_events:
                        visited.add(parent_id)
                        ancestors.append(parent_id)
                        queue.append((parent_id, depth + 1))

        # 子孫を探索（子方向） - 全走査
        if direction in ("descendants", "both"):
            visited_desc: set[str] = set()
            queue_desc = [(event_id, 0)]

            while queue_desc:
                current_id, depth = queue_desc.pop(0)
                if depth >= max_depth:
                    truncated = True
                    continue

                # 全イベントを走査して、parentsに含むものを検索
                for evt_id, evt in all_events.items():
                    parents = getattr(evt, "parents", [])
                    if current_id in parents and evt_id not in visited_desc:
                        visited_desc.add(evt_id)
                        descendants.append(evt_id)
                        queue_desc.append((evt_id, depth + 1))

        return {
            "event_id": event_id,
            "ancestors": ancestors,
            "descendants": descendants,
            "truncated": truncated,
        }
