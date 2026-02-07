"""Activity エンドポイント

エージェント活動のリアルタイム配信（SSE）およびREST API。
ActivityBusからイベントを取得し、VS Code拡張に配信する。
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ...core.activity_bus import ActivityBus, ActivityEvent

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("/recent")
async def get_recent_events(limit: int = Query(default=100, ge=1, le=1000)):
    """最近のアクティビティイベントを取得"""
    bus = ActivityBus.get_instance()
    events = bus.get_recent_events(limit=limit)
    return {"events": [e.to_dict() for e in events]}


@router.get("/hierarchy")
async def get_hierarchy():
    """アクティブエージェントの階層構造を取得"""
    bus = ActivityBus.get_instance()
    hierarchy = bus.get_hierarchy()

    # AgentInfoをシリアライズ
    def serialize_hierarchy(h: dict) -> dict:
        result = {}
        for hive_id, hive_data in h.items():
            beekeeper = hive_data.get("beekeeper")
            colonies = {}
            for col_id, col_data in hive_data.get("colonies", {}).items():
                queen = col_data.get("queen_bee")
                colonies[col_id] = {
                    "queen_bee": queen.to_dict() if queen else None,
                    "workers": [w.to_dict() for w in col_data.get("workers", [])],
                }
            result[hive_id] = {
                "beekeeper": beekeeper.to_dict() if beekeeper else None,
                "colonies": colonies,
            }
        return result

    return {"hierarchy": serialize_hierarchy(hierarchy)}


@router.get("/agents")
async def get_active_agents():
    """アクティブなエージェント一覧を取得"""
    bus = ActivityBus.get_instance()
    agents = bus.get_active_agents()
    return {"agents": [a.to_dict() for a in agents]}


@router.get("/stream")
async def stream_events():
    """SSEでアクティビティイベントをリアルタイム配信

    Server-Sent Events (SSE) ストリーム。
    VS Code拡張のAgent Monitorパネルが接続して
    リアルタイムにエージェント活動を表示する。
    """

    async def event_generator():
        bus = ActivityBus.get_instance()
        queue: asyncio.Queue[ActivityEvent] = asyncio.Queue()

        async def handler(event: ActivityEvent) -> None:
            await queue.put(event)

        bus.subscribe(handler)

        try:
            while True:
                try:
                    # 15秒ごとにkeep-alive
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    data = json.dumps(event.to_dict(), ensure_ascii=False)
                    yield f"data: {data}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(handler)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
