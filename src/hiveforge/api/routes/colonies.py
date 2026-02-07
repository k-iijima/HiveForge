"""Colony REST API エンドポイント

Colony管理用のREST API。
イベントソーシング設計: 全操作はイベントとしてHiveStoreに永続化され、
読み取りはイベント列からの投影（HiveAggregate）により再構築される。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hiveforge.core.ar.hive_projections import build_hive_aggregate
from hiveforge.core.events import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyStartedEvent,
    generate_event_id,
)

from ..helpers import get_hive_store

router = APIRouter(tags=["Colonies"])


# --- Pydantic モデル ---


class CreateColonyRequest(BaseModel):
    """Colony作成リクエスト"""

    name: str = Field(..., min_length=1, max_length=200, description="Colonyの名前")
    goal: str | None = Field(default=None, description="Colonyの目標")


class ColonyResponse(BaseModel):
    """Colonyレスポンス"""

    colony_id: str = Field(..., description="ColonyのID")
    hive_id: str = Field(..., description="親HiveのID")
    name: str = Field(..., description="Colonyの名前")
    goal: str | None = Field(default=None, description="Colonyの目標")
    status: str = Field(default="created", description="Colonyのステータス")


class ColonyStatusResponse(BaseModel):
    """Colonyステータスレスポンス"""

    colony_id: str = Field(..., description="ColonyのID")
    status: str = Field(..., description="Colonyのステータス")


# --- ヘルパー ---


def _rebuild_hive(hive_id: str):
    """HiveStoreからイベントをリプレイしてHive集約を再構築"""
    store = get_hive_store()
    events = list(store.replay(hive_id))
    if not events:
        return None
    return build_hive_aggregate(hive_id, events)


def _find_colony_hive_id(colony_id: str) -> str | None:
    """Colony IDから所属するHive IDを検索

    全Hiveのイベントをスキャンしてcolony_idを含むHiveを見つける。
    """
    store = get_hive_store()
    for hive_id in store.list_hives():
        aggregate = _rebuild_hive(hive_id)
        if aggregate is not None and colony_id in aggregate.colonies:
            return hive_id
    return None


# Colony状態をAPIステータス文字列に変換するマッピング
_STATE_TO_STATUS = {
    "pending": "created",
    "in_progress": "running",
    "completed": "completed",
    "failed": "failed",
}


# --- Hive配下のColonyエンドポイント ---

hive_colonies_router = APIRouter(prefix="/hives/{hive_id}/colonies", tags=["Colonies"])


@hive_colonies_router.post("", response_model=ColonyResponse, status_code=201)
async def create_colony(hive_id: str, request: CreateColonyRequest) -> ColonyResponse:
    """Colonyを作成"""
    # Hiveの存在確認
    aggregate = _rebuild_hive(hive_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    colony_id = generate_event_id()
    store = get_hive_store()

    # イベントを発行してHiveStoreに永続化（Hiveのイベントストリームに追記）
    event = ColonyCreatedEvent(
        run_id=colony_id,
        actor="user",
        payload={
            "colony_id": colony_id,
            "hive_id": hive_id,
            "name": request.name,
            "goal": request.goal,
        },
    )
    store.append(event, hive_id)

    return ColonyResponse(
        colony_id=colony_id,
        hive_id=hive_id,
        name=request.name,
        goal=request.goal,
        status="created",
    )


@hive_colonies_router.get("", response_model=list[ColonyResponse])
async def list_colonies(hive_id: str) -> list[ColonyResponse]:
    """Hive配下のColony一覧を取得"""
    aggregate = _rebuild_hive(hive_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    result = []
    for colony_id, colony in aggregate.colonies.items():
        status = _STATE_TO_STATUS.get(colony.state.value, colony.state.value)
        name = colony.metadata.get("name", colony.goal)
        result.append(
            ColonyResponse(
                colony_id=colony_id,
                hive_id=hive_id,
                name=name,
                goal=colony.goal,
                status=status,
            )
        )
    return result


@hive_colonies_router.get("/{colony_id}", response_model=ColonyResponse)
async def get_colony(hive_id: str, colony_id: str) -> ColonyResponse:
    """Colony詳細を取得"""
    aggregate = _rebuild_hive(hive_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    if colony_id not in aggregate.colonies:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    colony = aggregate.colonies[colony_id]
    status = _STATE_TO_STATUS.get(colony.state.value, colony.state.value)
    name = colony.metadata.get("name", colony.goal)
    return ColonyResponse(
        colony_id=colony_id,
        hive_id=hive_id,
        name=name,
        goal=colony.goal,
        status=status,
    )


# --- Colonyライフサイクルエンドポイント ---


@router.post("/colonies/{colony_id}/start", response_model=ColonyStatusResponse)
async def start_colony(colony_id: str) -> ColonyStatusResponse:
    """Colonyを開始"""
    hive_id = _find_colony_hive_id(colony_id)
    if hive_id is None:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    store = get_hive_store()

    # イベントを発行してHiveStoreに永続化
    event = ColonyStartedEvent(
        run_id=colony_id,
        actor="user",
        payload={"colony_id": colony_id},
    )
    store.append(event, hive_id)

    return ColonyStatusResponse(colony_id=colony_id, status="running")


@router.post("/colonies/{colony_id}/complete", response_model=ColonyStatusResponse)
async def complete_colony(colony_id: str) -> ColonyStatusResponse:
    """Colonyを完了"""
    hive_id = _find_colony_hive_id(colony_id)
    if hive_id is None:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    store = get_hive_store()

    # イベントを発行してHiveStoreに永続化
    event = ColonyCompletedEvent(
        run_id=colony_id,
        actor="user",
        payload={"colony_id": colony_id},
    )
    store.append(event, hive_id)

    return ColonyStatusResponse(colony_id=colony_id, status="completed")
