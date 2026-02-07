"""Hive関連のMCPハンドラー

Hive管理ツールのハンドラー実装。
BeekeeperMCPServer経由でHiveStoreに永続化する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.ar.hive_projections import build_hive_aggregate
from ...core.ar.hive_storage import HiveStore
from .base import BaseHandler

if TYPE_CHECKING:
    from ..server import HiveForgeMCPServer


class HiveHandlers(BaseHandler):
    """Hive関連ハンドラー（Beekeeper委譲）"""

    def _get_hive_store(self) -> HiveStore:
        """HiveStoreを取得"""
        return self._server._get_hive_store()

    async def handle_create_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hiveを作成（HiveStoreに永続化）"""
        beekeeper = self._server._get_beekeeper()
        return await beekeeper.handle_create_hive(args)

    async def handle_list_hives(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive一覧を取得（HiveStore投影から）"""
        beekeeper = self._server._get_beekeeper()
        result = await beekeeper.handle_list_hives(args)
        return result

    async def handle_get_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive詳細を取得（HiveStore投影から）"""
        hive_id = args.get("hive_id")
        if not hive_id:
            return {"error": "hive_id is required"}

        store = self._get_hive_store()
        events = list(store.replay(hive_id))
        if not events:
            return {"error": f"Hive {hive_id} not found"}

        aggregate = build_hive_aggregate(hive_id, events)
        return {
            "hive_id": hive_id,
            "name": aggregate.name,
            "status": aggregate.state.value,
            "colony_count": len(aggregate.colonies),
        }

    async def handle_close_hive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hiveを終了（HiveClosedイベントを発行）"""
        from ...core.events import HiveClosedEvent

        hive_id = args.get("hive_id")
        if not hive_id:
            return {"error": "hive_id is required"}

        store = self._get_hive_store()
        events = list(store.replay(hive_id))
        if not events:
            return {"error": f"Hive {hive_id} not found"}

        event = HiveClosedEvent(
            run_id=hive_id,
            actor="mcp",
            payload={"hive_id": hive_id},
        )
        store.append(event, hive_id)

        return {"hive_id": hive_id, "status": "closed"}
