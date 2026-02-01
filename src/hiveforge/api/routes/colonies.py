"""Colony REST API エンドポイント

Colony管理用のREST API。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hiveforge.core.events import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyStartedEvent,
    generate_event_id,
)

from ..helpers import get_ar
from .hives import _hives

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


# --- In-memory Colony ストレージ（Phase 1用簡易実装） ---
# TODO: Phase 2でAkashic Recordに移行

_colonies: dict[str, dict[str, Any]] = {}


def _clear_colonies() -> None:
    """テスト用: Colonyストレージをクリア"""
    _colonies.clear()


# --- Hive配下のColonyエンドポイント ---

hive_colonies_router = APIRouter(prefix="/hives/{hive_id}/colonies", tags=["Colonies"])


@hive_colonies_router.post("", response_model=ColonyResponse, status_code=201)
async def create_colony(hive_id: str, request: CreateColonyRequest) -> ColonyResponse:
    """Colonyを作成"""
    if hive_id not in _hives:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    colony_id = generate_event_id()

    # イベントを発行
    ar = get_ar()
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

    # メモリに保存
    colony_data = {
        "colony_id": colony_id,
        "hive_id": hive_id,
        "name": request.name,
        "goal": request.goal,
        "status": "created",
    }
    _colonies[colony_id] = colony_data

    # HiveにColonyを追加
    _hives[hive_id]["colonies"].append(colony_id)

    if ar:
        ar.append(event, colony_id)

    return ColonyResponse(**colony_data)


@hive_colonies_router.get("", response_model=list[ColonyResponse])
async def list_colonies(hive_id: str) -> list[ColonyResponse]:
    """Hive配下のColony一覧を取得"""
    if hive_id not in _hives:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    colony_ids = _hives[hive_id]["colonies"]
    return [
        ColonyResponse(**_colonies[cid]) for cid in colony_ids if cid in _colonies
    ]


@hive_colonies_router.get("/{colony_id}", response_model=ColonyResponse)
async def get_colony(hive_id: str, colony_id: str) -> ColonyResponse:
    """Colony詳細を取得"""
    if hive_id not in _hives:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    if colony_id not in _colonies:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    return ColonyResponse(**_colonies[colony_id])


# --- Colonyライフサイクルエンドポイント ---


@router.post("/colonies/{colony_id}/start", response_model=ColonyStatusResponse)
async def start_colony(colony_id: str) -> ColonyStatusResponse:
    """Colonyを開始"""
    if colony_id not in _colonies:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    # イベントを発行
    ar = get_ar()
    event = ColonyStartedEvent(
        run_id=colony_id,
        actor="user",
        payload={"colony_id": colony_id},
    )

    _colonies[colony_id]["status"] = "running"

    if ar:
        ar.append(event, colony_id)

    return ColonyStatusResponse(colony_id=colony_id, status="running")


@router.post("/colonies/{colony_id}/complete", response_model=ColonyStatusResponse)
async def complete_colony(colony_id: str) -> ColonyStatusResponse:
    """Colonyを完了"""
    if colony_id not in _colonies:
        raise HTTPException(status_code=404, detail=f"Colony {colony_id} not found")

    # イベントを発行
    ar = get_ar()
    event = ColonyCompletedEvent(
        run_id=colony_id,
        actor="user",
        payload={"colony_id": colony_id},
    )

    _colonies[colony_id]["status"] = "completed"

    if ar:
        ar.append(event, colony_id)

    return ColonyStatusResponse(colony_id=colony_id, status="completed")
