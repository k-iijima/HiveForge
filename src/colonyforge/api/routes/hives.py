"""Hive REST API エンドポイント

Hive管理用のREST API。
イベントソーシング設計: 全操作はイベントとしてHiveStoreに永続化され、
読み取りはイベント列からの投影（HiveAggregate）により再構築される。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from colonyforge.core.ar.hive_projections import HiveAggregate, build_hive_aggregate
from colonyforge.core.events import (
    HiveClosedEvent,
    HiveCreatedEvent,
    generate_event_id,
)

from ..helpers import get_hive_store

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


# --- ヘルパー ---


def _rebuild_hive(hive_id: str) -> HiveAggregate | None:
    """HiveStoreからイベントをリプレイしてHive集約を再構築

    Args:
        hive_id: Hive ID

    Returns:
        HiveAggregate（存在しない場合はNone）
    """
    store = get_hive_store()
    events = list(store.replay(hive_id))
    if not events:
        return None
    return build_hive_aggregate(hive_id, events)


def _aggregate_to_response(hive_id: str, aggregate: HiveAggregate) -> HiveResponse:
    """HiveAggregateからHiveResponseを生成

    Args:
        hive_id: Hive ID
        aggregate: Hive集約

    Returns:
        HiveResponse
    """
    projection = aggregate.projection
    return HiveResponse(
        hive_id=hive_id,
        name=projection.name,
        description=projection.metadata.get("description"),
        status=projection.state.value,
        colonies=list(projection.colonies.keys()),
    )


# --- エンドポイント ---


@router.post("", response_model=HiveResponse, status_code=201)
async def create_hive(request: CreateHiveRequest) -> HiveResponse:
    """Hiveを作成"""
    hive_id = generate_event_id()
    store = get_hive_store()

    # イベントを発行してHiveStoreに永続化
    event = HiveCreatedEvent(
        run_id=hive_id,
        actor="user",
        payload={
            "hive_id": hive_id,
            "name": request.name,
            "description": request.description,
        },
    )
    store.append(event, hive_id)

    # イベントから投影を再構築してレスポンス
    aggregate = _rebuild_hive(hive_id)
    assert aggregate is not None  # 直前にイベントを書いたので必ず存在
    return _aggregate_to_response(hive_id, aggregate)


@router.get("", response_model=list[HiveResponse])
async def list_hives() -> list[HiveResponse]:
    """Hive一覧を取得"""
    store = get_hive_store()
    hive_ids = store.list_hives()
    result = []
    for hive_id in hive_ids:
        aggregate = _rebuild_hive(hive_id)
        if aggregate is not None:
            result.append(_aggregate_to_response(hive_id, aggregate))
    return result


@router.get("/{hive_id}", response_model=HiveResponse)
async def get_hive(hive_id: str) -> HiveResponse:
    """Hive詳細を取得"""
    aggregate = _rebuild_hive(hive_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    return _aggregate_to_response(hive_id, aggregate)


@router.post("/{hive_id}/close", response_model=HiveCloseResponse)
async def close_hive(hive_id: str) -> HiveCloseResponse:
    """Hiveを終了"""
    aggregate = _rebuild_hive(hive_id)
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Hive {hive_id} not found")

    store = get_hive_store()

    # イベントを発行してHiveStoreに永続化
    event = HiveClosedEvent(
        run_id=hive_id,
        actor="user",
        payload={"hive_id": hive_id},
    )
    store.append(event, hive_id)

    return HiveCloseResponse(hive_id=hive_id, status="closed")
