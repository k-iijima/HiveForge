"""Hive関連のMCPハンドラー

Hive管理ツールのハンドラー実装。
"""

from typing import Any

from .base import BaseHandler

# In-memory Hive ストレージ（Phase 1用簡易実装）
_hives: dict[str, dict[str, Any]] = {}


class HiveHandlers(BaseHandler):
    """Hive関連ハンドラー"""

    async def handle_create_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hiveを作成"""
        from hiveforge.core.events import generate_event_id

        name = args.get("name", "New Hive")
        description = args.get("description")

        hive_id = generate_event_id()

        hive_data = {
            "hive_id": hive_id,
            "name": name,
            "description": description,
            "status": "active",
            "colonies": [],
        }
        _hives[hive_id] = hive_data

        return hive_data

    async def handle_list_hives(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive一覧を取得"""
        return {"hives": list(_hives.values())}

    async def handle_get_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive詳細を取得"""
        hive_id = args.get("hive_id")

        if not hive_id or hive_id not in _hives:
            return {"error": f"Hive {hive_id} not found"}

        return _hives[hive_id]

    async def handle_close_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hiveを終了"""
        hive_id = args.get("hive_id")

        if not hive_id or hive_id not in _hives:
            return {"error": f"Hive {hive_id} not found"}

        _hives[hive_id]["status"] = "closed"

        return {"hive_id": hive_id, "status": "closed"}
