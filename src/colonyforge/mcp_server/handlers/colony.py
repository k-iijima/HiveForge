"""Colony関連のMCPハンドラー

Colony管理ツールのハンドラー実装。
BeekeeperMCPServer経由でHiveStoreに永続化する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.ar.hive_projections import build_hive_aggregate
from ...core.ar.hive_storage import HiveStore
from ...core.events import ColonyCompletedEvent, ColonyStartedEvent
from .base import BaseHandler

if TYPE_CHECKING:
    pass


class ColonyHandlers(BaseHandler):
    """Colony関連ハンドラー（Beekeeper委譲）"""

    def _get_hive_store(self) -> HiveStore:
        """HiveStoreを取得"""
        return self._server._get_hive_store()

    async def handle_create_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを作成（HiveStoreに永続化）"""
        beekeeper = self._server._get_beekeeper()
        # Beekeeperはgoalをdomainフィールドで受け取る
        bk_args = dict(args)
        if "goal" in bk_args and "domain" not in bk_args:
            bk_args["domain"] = bk_args.pop("goal")
        return await beekeeper.handle_create_colony(bk_args)

    async def handle_list_colonies(self, args: dict[str, Any]) -> dict[str, Any]:
        """Hive配下のColony一覧を取得（HiveStore投影から）"""
        beekeeper = self._server._get_beekeeper()
        return await beekeeper.handle_list_colonies(args)

    async def handle_start_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを開始（ColonyStartedイベントを発行）"""
        colony_id = args.get("colony_id")
        if not colony_id:
            return {"error": "colony_id is required"}

        store = self._get_hive_store()
        hive_id = self._find_hive_for_colony(colony_id, store)
        if not hive_id:
            return {"error": f"Colony {colony_id} not found"}

        event = ColonyStartedEvent(
            run_id=colony_id,
            actor="mcp",
            payload={"colony_id": colony_id, "hive_id": hive_id},
        )
        store.append(event, hive_id)

        return {"colony_id": colony_id, "status": "running"}

    async def handle_complete_colony(self, args: dict[str, Any]) -> dict[str, Any]:
        """Colonyを完了（ColonyCompletedイベントを発行）"""
        colony_id = args.get("colony_id")
        if not colony_id:
            return {"error": "colony_id is required"}

        store = self._get_hive_store()
        hive_id = self._find_hive_for_colony(colony_id, store)
        if not hive_id:
            return {"error": f"Colony {colony_id} not found"}

        event = ColonyCompletedEvent(
            run_id=colony_id,
            actor="mcp",
            payload={"colony_id": colony_id, "hive_id": hive_id},
        )
        store.append(event, hive_id)

        return {"colony_id": colony_id, "status": "completed"}

    def _find_hive_for_colony(self, colony_id: str, store: HiveStore) -> str | None:
        """Colony IDからHive IDを検索"""
        for hive_id in store.list_hives():
            events = list(store.replay(hive_id))
            if events:
                aggregate = build_hive_aggregate(hive_id, events)
                if colony_id in aggregate.colonies:
                    return hive_id
        return None
