"""
Direct Intervention REST API

ユーザー直接介入、Queen直訴、Beekeeperフィードバックのエンドポイント。
"""

import tempfile
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.events import (
    BeekeeperFeedbackEvent,
    EscalationType,
    QueenEscalationEvent,
    UserDirectInterventionEvent,
)
from ...core.intervention import (
    EscalationRecord,
    FeedbackRecord,
    InterventionRecord,
    InterventionStore,
)

router = APIRouter(prefix="/interventions", tags=["Interventions"])


# ============================================================================
# リクエスト/レスポンスモデル
# ============================================================================


class UserInterventionRequest(BaseModel):
    """ユーザー直接介入リクエスト"""

    colony_id: str = Field(..., description="対象Colony ID")
    instruction: str = Field(..., description="直接指示内容")
    reason: str = Field(default="", description="介入理由")
    bypass_beekeeper: bool = Field(default=True, description="Beekeeperをバイパスするか")
    share_with_beekeeper: bool = Field(default=True, description="Beekeeperにも共有するか")


class QueenEscalationRequest(BaseModel):
    """Queen直訴リクエスト"""

    colony_id: str = Field(..., description="Queen BeeのColony ID")
    escalation_type: str = Field(..., description="エスカレーション種別")
    summary: str = Field(..., description="問題の要約")
    details: str = Field(default="", description="詳細説明")
    suggested_actions: list[str] = Field(default_factory=list, description="提案アクション")
    beekeeper_context: str = Field(default="", description="Beekeeperとの経緯")


class BeekeeperFeedbackRequest(BaseModel):
    """Beekeeperフィードバックリクエスト"""

    escalation_id: str = Field(..., description="対応したエスカレーション/介入のID")
    resolution: str = Field(..., description="解決方法")
    beekeeper_adjustment: dict[str, Any] = Field(
        default_factory=dict, description="Beekeeperへの調整"
    )
    lesson_learned: str = Field(default="", description="学んだ教訓")


class InterventionResponse(BaseModel):
    """介入レスポンス"""

    event_id: str
    type: str
    colony_id: str | None = None
    message: str


# ============================================================================
# InterventionStore（MCP/APIで同一モデルを使用）
# ============================================================================

_intervention_store: InterventionStore | None = None


def get_intervention_store() -> InterventionStore:
    """InterventionStoreを取得（遅延初期化）"""
    global _intervention_store
    if _intervention_store is None:
        _intervention_store = InterventionStore(
            base_path=tempfile.mkdtemp(prefix="colonyforge-interventions-")
        )
    return _intervention_store


def set_intervention_store(store: InterventionStore) -> None:
    """InterventionStoreを設定（テスト・初期化用）"""
    global _intervention_store
    _intervention_store = store


# ============================================================================
# エンドポイント
# ============================================================================


@router.post("/user", response_model=InterventionResponse)
async def create_user_intervention(request: UserInterventionRequest) -> InterventionResponse:
    """ユーザー直接介入を作成

    ユーザーがBeekeeperをバイパスしてQueen Beeに直接指示を出す。
    """
    event = UserDirectInterventionEvent(
        actor="user",
        payload={
            "colony_id": request.colony_id,
            "instruction": request.instruction,
            "reason": request.reason,
            "bypass_beekeeper": request.bypass_beekeeper,
            "share_with_beekeeper": request.share_with_beekeeper,
        },
    )

    record = InterventionRecord(
        event_id=event.id,
        colony_id=request.colony_id,
        instruction=request.instruction,
        reason=request.reason,
        share_with_beekeeper=request.share_with_beekeeper,
        timestamp=event.timestamp.isoformat(),
    )
    get_intervention_store().add_intervention(record)

    return InterventionResponse(
        event_id=event.id,
        type="user_intervention",
        colony_id=request.colony_id,
        message=f"Direct intervention created for colony {request.colony_id}",
    )


@router.post("/escalation", response_model=InterventionResponse)
async def create_queen_escalation(request: QueenEscalationRequest) -> InterventionResponse:
    """Queen直訴を作成

    Queen BeeがBeekeeperとの調整で解決できない問題をユーザーにエスカレーション。
    """
    # エスカレーションタイプを検証
    try:
        esc_type = EscalationType(request.escalation_type)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid escalation_type: {request.escalation_type}. "
            f"Valid types: {[t.value for t in EscalationType]}",
        ) from err

    event = QueenEscalationEvent(
        actor=f"queen-{request.colony_id}",
        payload={
            "colony_id": request.colony_id,
            "escalation_type": esc_type.value,
            "summary": request.summary,
            "details": request.details,
            "suggested_actions": request.suggested_actions,
            "beekeeper_context": request.beekeeper_context,
        },
    )

    record = EscalationRecord(
        event_id=event.id,
        colony_id=request.colony_id,
        escalation_type=esc_type.value,
        summary=request.summary,
        details=request.details,
        suggested_actions=request.suggested_actions,
        beekeeper_context=request.beekeeper_context,
        timestamp=event.timestamp.isoformat(),
    )
    get_intervention_store().add_escalation(record)

    return InterventionResponse(
        event_id=event.id,
        type="queen_escalation",
        colony_id=request.colony_id,
        message=f"Escalation created: {request.summary}",
    )


@router.post("/feedback", response_model=InterventionResponse)
async def create_beekeeper_feedback(request: BeekeeperFeedbackRequest) -> InterventionResponse:
    """Beekeeperフィードバックを作成

    直接介入やエスカレーション解決後のフィードバックを記録。
    """
    # 対象のエスカレーション/介入を確認
    store = get_intervention_store()
    target = store.get_target(request.escalation_id)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Escalation or intervention not found: {request.escalation_id}",
        )

    event = BeekeeperFeedbackEvent(
        actor="user",
        payload={
            "escalation_id": request.escalation_id,
            "resolution": request.resolution,
            "beekeeper_adjustment": request.beekeeper_adjustment,
            "lesson_learned": request.lesson_learned,
        },
    )

    record = FeedbackRecord(
        event_id=event.id,
        escalation_id=request.escalation_id,
        resolution=request.resolution,
        beekeeper_adjustment=request.beekeeper_adjustment,
        lesson_learned=request.lesson_learned,
        timestamp=event.timestamp.isoformat(),
    )
    store.add_feedback(record)

    # エスカレーションのステータスを更新
    store.resolve_escalation(request.escalation_id)

    return InterventionResponse(
        event_id=event.id,
        type="beekeeper_feedback",
        colony_id=target.colony_id if hasattr(target, "colony_id") else None,
        message=f"Feedback recorded for {request.escalation_id}",
    )


@router.get("/escalations")
async def list_escalations(
    colony_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """エスカレーション一覧を取得"""
    escalations = get_intervention_store().list_escalations(colony_id=colony_id, status=status)

    return {
        "escalations": escalations,
        "count": len(escalations),
    }


@router.get("/escalations/{escalation_id}")
async def get_escalation(escalation_id: str) -> dict[str, Any]:
    """エスカレーション詳細を取得"""
    escalation = get_intervention_store().get_escalation(escalation_id)
    if not escalation:
        raise HTTPException(status_code=404, detail=f"Escalation not found: {escalation_id}")
    return escalation.model_dump(mode="json")


@router.get("/interventions")
async def list_interventions(colony_id: str | None = None) -> dict[str, Any]:
    """直接介入一覧を取得"""
    interventions = get_intervention_store().list_interventions(colony_id=colony_id)

    return {
        "interventions": interventions,
        "count": len(interventions),
    }
