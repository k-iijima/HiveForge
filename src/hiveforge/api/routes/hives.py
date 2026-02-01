"""Hive REST API エンドポイント

Hive管理用のREST API。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hiveforge.core.events import (
    EventType,
    HiveClosedEvent,
    HiveCreatedEvent,
    generate_event_id,
)

from ..helpers import get_ar

router = APIRouter(prefix="/hives", tags=["Hives"])


# --- Pydantic モデル ---


class CreateHiveRequest(BaseModel):
    """Hive作成リクエスト"""

    name: str = Field(..., min_length=1, max_length=200, description="Hiveの名前")
    description: str | None = Field(default=None, description="Hiveの説明")


class HiveResponse(BaseModel):
    """Hiveレスポンス"""

    hive_id: str = Field(..., description="HiveのID")
    name: str = Field(..., description="Hiveの名前")
    description: str | None = Field(default=None, description="Hiveの説明")
    status: str = Field(default="active", description="Hiveのステータス")
    colonies: list[str] = Field(default_factory=list, description="所属するColony ID")


class HiveCloseResponse(BaseModel):
    """Hive終了レスポンス"""

    hive_id: str = Field(..., description="HiveのID")
    status: str = Field(default="closed", description="Hiveのステータス")


# --- In-memory Hive ストレージ（Phase 1用簡易実装） ---
# TODO: Phase 2でAkashic Recordに移行

_hives: dict[str, dict[str, Any]] = {}


def _clear_hives() -> None:
    """テスト用: Hiveストレージをクリア"""
    _hives.clear()


# --- エンドポイント ---


@router.post("", response_model=HiveResponse, status_code=201)
async def create_hive(request: CreateHiveRequest) -> HiveResponse:
    """Hiveを作成"""
    hive_id = generate_event_id()

    # イベントを発行
    ar = get_ar()
    event = HiveCreatedEvent(
        run_id=hive_id,  # Hive IDをrun_idとして使用
        actor="user",
        payload={
            "hive_id": hive_id,
            "name": request.name,
            "description": request.description,
        },
    )

    # メモリに保存
    hive_data = {
        "hive_id": hive_id,
        "name": request.name,
        "description": request.description,
        "status": "active",
        "colonies": [],
    }
    _hives[hive_id] = hive_data

    # ARがあればイベントを記録
    if ar:
        ar.append(event, hive_id)

    return HiveResponse(**hive_data)


@router.get("", response_model=list[HiveResponse])
async def list_hives() -> list[HiveResponse]:
    """Hive一覧を取得"""
    return [HiveResponse(**hive) for hive in _hives.values()]


@router.get("/{hive_id}", response_model=HiveResponse)
async def get_hive(hive_id: str) -> HiveResponse:
    """Hive詳細を取得"""
    if hive_id not in _hives:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    return HiveResponse(**_hives[hive_id])


@router.post("/{hive_id}/close", response_model=HiveCloseResponse)
async def close_hive(hive_id: str) -> HiveCloseResponse:
    """Hiveを終了"""
    if hive_id not in _hives:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    # イベントを発行
    ar = get_ar()
    event = HiveClosedEvent(
        run_id=hive_id,
        actor="user",
        payload={"hive_id": hive_id},
    )

    # ステータスを更新
    _hives[hive_id]["status"] = "closed"

    if ar:
        ar.append(event, hive_id)

    return HiveCloseResponse(hive_id=hive_id, status="closed")
