"""Activity エンドポイント

エージェント活動のリアルタイム配信（SSE）およびREST API。
ActivityBusからイベントを取得し、VS Code拡張に配信する。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...core.activity_bus import (
    ActivityBus,
    ActivityEvent,
    ActivityType,
    AgentInfo,
    AgentRole,
)

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("/recent")
async def get_recent_events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    """最近のアクティビティイベントを取得"""
    bus = ActivityBus.get_instance()
    events = bus.get_recent_events(limit=limit)
    return {"events": [e.to_dict() for e in events]}


@router.get("/hierarchy")
async def get_hierarchy() -> dict[str, Any]:
    """アクティブエージェントの階層構造を取得"""
    bus = ActivityBus.get_instance()
    hierarchy = bus.get_hierarchy()

    # AgentInfoをシリアライズ
    def serialize_hierarchy(h: dict[str, Any]) -> dict[str, Any]:
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
async def get_active_agents() -> dict[str, Any]:
    """アクティブなエージェント一覧を取得"""
    bus = ActivityBus.get_instance()
    agents = bus.get_active_agents()
    return {"agents": [a.to_dict() for a in agents]}


# =============================================================================
# イベント投入 API
# =============================================================================


class EmitEventRequest(BaseModel):
    """イベント投入リクエスト"""

    activity_type: str = Field(..., description="アクティビティタイプ (例: llm.request)")
    agent_id: str = Field(..., description="エージェントID")
    role: str = Field(default="worker_bee", description="ロール (beekeeper/queen_bee/worker_bee)")
    hive_id: str = Field(default="h-1", description="Hive ID")
    colony_id: str | None = Field(default=None, description="Colony ID")
    summary: str = Field(..., description="サマリー")
    detail: dict[str, Any] = Field(default_factory=dict, description="詳細")


@router.post("/emit")
async def emit_event(req: EmitEventRequest) -> dict[str, str]:
    """HTTP経由でアクティビティイベントを投入する

    テスト・デモ用。サーバープロセス内のActivityBusに直接emitする。
    """
    bus = ActivityBus.get_instance()
    agent = AgentInfo(
        agent_id=req.agent_id,
        role=AgentRole(req.role),
        hive_id=req.hive_id,
        colony_id=req.colony_id,
    )
    event = ActivityEvent(
        activity_type=ActivityType(req.activity_type),
        agent=agent,
        summary=req.summary,
        detail=req.detail,
    )
    await bus.emit(event)
    return {"status": "ok", "event_id": event.event_id}


@router.post("/seed")
async def seed_demo_data() -> dict[str, Any]:
    """デモ用テストデータを投入する

    2つのHive、複数エージェントを登録し、
    各種アクティビティイベントを発行する。
    モニターの動作確認用。
    """
    bus = ActivityBus.get_instance()

    # エージェント定義
    agents: dict[str, AgentInfo] = {
        "bk-a": AgentInfo(agent_id="beekeeper-A", role=AgentRole.BEEKEEPER, hive_id="hive-alpha"),
        "qb-ui": AgentInfo(
            agent_id="queen-ui",
            role=AgentRole.QUEEN_BEE,
            hive_id="hive-alpha",
            colony_id="colony-frontend",
        ),
        "qb-api": AgentInfo(
            agent_id="queen-api",
            role=AgentRole.QUEEN_BEE,
            hive_id="hive-alpha",
            colony_id="colony-backend",
        ),
        "w-fe1": AgentInfo(
            agent_id="worker-frontend-1",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-alpha",
            colony_id="colony-frontend",
        ),
        "w-fe2": AgentInfo(
            agent_id="worker-frontend-2",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-alpha",
            colony_id="colony-frontend",
        ),
        "w-be1": AgentInfo(
            agent_id="worker-backend-1",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-alpha",
            colony_id="colony-backend",
        ),
        "w-be2": AgentInfo(
            agent_id="worker-backend-2",
            role=AgentRole.WORKER_BEE,
            hive_id="hive-alpha",
            colony_id="colony-backend",
        ),
    }

    emitted = 0

    # Step 1: 全エージェント起動
    for agent in agents.values():
        await bus.emit(
            ActivityEvent(
                activity_type=ActivityType.AGENT_STARTED,
                agent=agent,
                summary=f"{agent.agent_id} が起動しました",
            )
        )
        emitted += 1

    # Step 2: 各種アクティビティ
    scenarios: list[tuple[str, ActivityType, str]] = [
        ("qb-ui", ActivityType.TASK_ASSIGNED, "worker-frontend-1にログインUI実装を割り当て"),
        ("qb-ui", ActivityType.TASK_ASSIGNED, "worker-frontend-2にダッシュボード実装を割り当て"),
        ("w-fe1", ActivityType.LLM_REQUEST, "ログイン画面のReactコンポーネント設計を依頼"),
        ("w-fe1", ActivityType.LLM_RESPONSE, "フォームバリデーション付きコンポーネントを提案"),
        ("w-fe1", ActivityType.MCP_TOOL_CALL, "create_file: src/components/LoginForm.tsx"),
        ("w-fe1", ActivityType.MCP_TOOL_RESULT, "ファイル作成完了 (42行)"),
        ("w-fe2", ActivityType.LLM_REQUEST, "KPIダッシュボードの構造設計"),
        ("w-fe2", ActivityType.LLM_RESPONSE, "3タブ構成を提案 (Overview/KPI/Activity)"),
        ("qb-api", ActivityType.TASK_ASSIGNED, "worker-backend-1にAPI実装を割り当て"),
        ("qb-api", ActivityType.TASK_ASSIGNED, "worker-backend-2にDB設計を割り当て"),
        ("w-be1", ActivityType.LLM_REQUEST, "REST API エンドポイント設計"),
        ("w-be1", ActivityType.LLM_RESPONSE, "OpenAPI仕様ベースの設計完了"),
        ("w-be1", ActivityType.MCP_TOOL_CALL, "create_file: src/api/routes/users.py"),
        ("w-be1", ActivityType.MCP_TOOL_RESULT, "ファイル作成完了 (85行)"),
        ("w-be2", ActivityType.LLM_REQUEST, "PostgreSQLスキーマ設計"),
        ("w-be2", ActivityType.MCP_TOOL_CALL, "run_in_terminal: alembic revision"),
        ("w-be2", ActivityType.MCP_TOOL_RESULT, "マイグレーション作成完了"),
        ("bk-a", ActivityType.MESSAGE_RECEIVED, "queen-uiから進捗報告: フロントエンド70%完了"),
        ("bk-a", ActivityType.MESSAGE_RECEIVED, "queen-apiから進捗報告: バックエンド50%完了"),
        ("w-fe1", ActivityType.TASK_PROGRESS, "ログイン画面 100% 完了"),
        ("w-be1", ActivityType.TASK_PROGRESS, "API実装 80% 完了"),
        ("qb-ui", ActivityType.MESSAGE_SENT, "beekeeperに統合レポート送信"),
        ("qb-api", ActivityType.MESSAGE_SENT, "beekeeperにAPI進捗報告送信"),
    ]

    for agent_key, activity_type, summary in scenarios:
        agent = agents[agent_key]
        await bus.emit(
            ActivityEvent(
                activity_type=activity_type,
                agent=agent,
                summary=summary,
            )
        )
        emitted += 1
        await asyncio.sleep(0.05)  # リアルタイム感を出す

    return {
        "status": "ok",
        "agents_registered": len(agents),
        "events_emitted": emitted,
    }


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    """SSEでアクティビティイベントをリアルタイム配信

    Server-Sent Events (SSE) ストリーム。
    VS Code拡張のAgent Monitorパネルが接続して
    リアルタイムにエージェント活動を表示する。
    """

    async def event_generator() -> AsyncGenerator[str, None]:
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
