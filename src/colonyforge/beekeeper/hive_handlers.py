"""Beekeeper Hive/Colony管理ハンドラMixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core.ar.hive_projections import build_hive_aggregate
from ..core.events import (
    ColonyCreatedEvent,
    HiveCreatedEvent,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class HiveHandlersMixin:
    """Hive/Colony CRUD + ステータスハンドラ"""

    async def handle_get_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """ステータス取得ハンドラ

        HiveStore投影から実データを取得する。
        hive_idが指定されていればそのHiveの詳細を、
        なければ全Hiveの概要を返す。
        """
        hive_id = arguments.get("hive_id")
        include_colonies = arguments.get("include_colonies", True)

        # 現在のセッション状態を返す
        session_info = None
        if self.current_session:
            session_info = {
                "session_id": self.current_session.session_id,
                "state": self.current_session.state.value,
                "hive_id": self.current_session.hive_id,
                "active_colonies": list(self.current_session.active_colonies.keys()),
            }

        assert self.hive_store is not None

        # Hive情報をHiveStore投影から取得
        hives_data: list[dict[str, Any]] = []
        colonies_data: list[dict[str, Any]] | None = [] if include_colonies else None

        if hive_id:
            # 特定Hiveの詳細
            events = list(self.hive_store.replay(hive_id))
            if events:
                aggregate = build_hive_aggregate(hive_id, events)
                hive_info: dict[str, Any] = {
                    "hive_id": hive_id,
                    "name": aggregate.name,
                    "status": aggregate.state.value,
                }
                if include_colonies and colonies_data is not None:
                    for cid, colony in aggregate.colonies.items():
                        colonies_data.append(
                            {
                                "colony_id": cid,
                                "hive_id": hive_id,
                                "goal": colony.goal,
                                "status": colony.state.value,
                            }
                        )
                    hive_info["colony_count"] = len(aggregate.colonies)
                hives_data.append(hive_info)
        else:
            # 全Hiveの概要
            for h_id in self.hive_store.list_hives():
                events = list(self.hive_store.replay(h_id))
                if events:
                    aggregate = build_hive_aggregate(h_id, events)
                    hive_info = {
                        "hive_id": h_id,
                        "name": aggregate.name,
                        "status": aggregate.state.value,
                        "colony_count": len(aggregate.colonies),
                    }
                    hives_data.append(hive_info)

                    if include_colonies and colonies_data is not None:
                        for cid, colony in aggregate.colonies.items():
                            colonies_data.append(
                                {
                                    "colony_id": cid,
                                    "hive_id": h_id,
                                    "goal": colony.goal,
                                    "status": colony.state.value,
                                }
                            )

        return {
            "status": "success",
            "session": session_info,
            "hives": hives_data,
            "colonies": colonies_data,
        }

    async def handle_create_hive(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive作成ハンドラ

        HiveCreatedイベントを発行し、HiveStoreに永続化する。
        セッションをこのHiveにアクティブ化する。
        """
        from ..core import generate_event_id

        name = arguments.get("name", "")
        goal = arguments.get("goal", "")

        hive_id = generate_event_id()

        # セッションをアクティブ化
        if not self.current_session:
            self.current_session = self.session_manager.create_session()
        self.current_session.activate(hive_id)

        # HiveCreatedイベントを発行してHiveStoreに永続化
        assert self.hive_store is not None
        event = HiveCreatedEvent(
            run_id=hive_id,
            actor="beekeeper",
            payload={
                "hive_id": hive_id,
                "name": name,
                "description": goal,
            },
        )
        self.hive_store.append(event, hive_id)

        return {
            "status": "created",
            "hive_id": hive_id,
            "name": name,
            "goal": goal,
        }

    async def handle_create_colony(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony作成ハンドラ

        ColonyCreatedイベントを発行し、HiveStoreに永続化する。
        Hiveの存在確認を行い、セッションにColonyを追加する。
        """
        from ..core import generate_event_id

        hive_id = arguments.get("hive_id", "")
        name = arguments.get("name", "")
        domain = arguments.get("domain", "")

        # Hiveの存在確認
        assert self.hive_store is not None
        events = list(self.hive_store.replay(hive_id))
        if not events:
            return {
                "status": "error",
                "error": f"Hive {hive_id} not found",
            }

        colony_id = generate_event_id()

        # セッションにColonyを追加
        if self.current_session:
            self.current_session.add_colony(colony_id)

        # ColonyCreatedイベントを発行してHiveStoreに永続化
        event = ColonyCreatedEvent(
            run_id=colony_id,
            actor="beekeeper",
            payload={
                "colony_id": colony_id,
                "hive_id": hive_id,
                "name": name,
                "goal": domain,
            },
        )
        self.hive_store.append(event, hive_id)

        return {
            "status": "created",
            "colony_id": colony_id,
            "hive_id": hive_id,
            "name": name,
            "domain": domain,
        }

    async def handle_list_hives(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive一覧ハンドラ

        HiveStore投影から全Hiveの一覧を取得する。
        """
        assert self.hive_store is not None
        hives: list[dict[str, Any]] = []

        for hive_id in self.hive_store.list_hives():
            events = list(self.hive_store.replay(hive_id))
            if events:
                aggregate = build_hive_aggregate(hive_id, events)
                hives.append(
                    {
                        "hive_id": hive_id,
                        "name": aggregate.name,
                        "status": aggregate.state.value,
                        "colony_count": len(aggregate.colonies),
                    }
                )

        return {
            "status": "success",
            "hives": hives,
        }

    async def handle_list_colonies(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony一覧ハンドラ

        HiveStore投影から指定HiveのColony一覧を取得する。
        """
        hive_id = arguments.get("hive_id", "")

        assert self.hive_store is not None
        events = list(self.hive_store.replay(hive_id))
        if not events:
            return {
                "status": "error",
                "error": f"Hive {hive_id} not found",
            }

        aggregate = build_hive_aggregate(hive_id, events)
        colonies: list[dict[str, Any]] = []
        for cid, colony in aggregate.colonies.items():
            colonies.append(
                {
                    "colony_id": cid,
                    "hive_id": hive_id,
                    "name": colony.metadata.get("name", colony.goal),
                    "goal": colony.goal,
                    "status": colony.state.value,
                }
            )

        return {
            "status": "success",
            "hive_id": hive_id,
            "colonies": colonies,
        }
