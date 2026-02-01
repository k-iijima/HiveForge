"""Colony関連のMCPハンドラー

Colony管理ツールのハンドラー実装。
"""

from typing import Any

from .base import BaseHandler
from .hive import _hives

# In-memory Colony ストレージ（Phase 1用簡易実装）
_colonies: dict[str, dict[str, Any]] = {}


class ColonyHandlers(BaseHandler):
    """Colony関連ハンドラー"""

    async def handle_create_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを作成"""
        from hiveforge.core.events import generate_event_id

        hive_id = args.get("hive_id")
        name = args.get("name", "New Colony")
        goal = args.get("goal")

        if not hive_id or hive_id not in _hives:
            return {"error": f"Hive {hive_id} not found"}

        colony_id = generate_event_id()

        colony_data = {
            "colony_id": colony_id,
            "hive_id": hive_id,
            "name": name,
            "goal": goal,
            "status": "created",
        }
        _colonies[colony_id] = colony_data

        # HiveにColonyを追加
        _hives[hive_id]["colonies"].append(colony_id)

        return colony_data

    async def handle_list_colonies(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive配下のColony一覧を取得"""
        hive_id = args.get("hive_id")

        if not hive_id or hive_id not in _hives:
            return {"error": f"Hive {hive_id} not found"}

        colony_ids = _hives[hive_id]["colonies"]
        colonies = [_colonies[cid] for cid in colony_ids if cid in _colonies]

        return {"colonies": colonies}

    async def handle_start_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを開始"""
        colony_id = args.get("colony_id")

        if not colony_id or colony_id not in _colonies:
            return {"error": f"Colony {colony_id} not found"}

        _colonies[colony_id]["status"] = "running"

        return {"colony_id": colony_id, "status": "running"}

    async def handle_complete_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを完了"""
        colony_id = args.get("colony_id")

        if not colony_id or colony_id not in _colonies:
            return {"error": f"Colony {colony_id} not found"}

        _colonies[colony_id]["status"] = "completed"

        return {"colony_id": colony_id, "status": "completed"}
