"""Requirements エンドポイント

確認要請に関するエンドポイント。
"""

from fastapi import APIRouter, HTTPException, status

from ...core import build_run_projection, generate_event_id
from ...core.events import (
    EventType,
    RequirementApprovedEvent,
    RequirementCreatedEvent,
    RequirementRejectedEvent,
)
from ..helpers import apply_event_to_projection, get_active_runs, get_ar
from ..models import (
    CreateRequirementRequest,
    RequirementResponse,
    ResolveRequirementRequest,
)


def _get_run_started_event_id(run_id: str) -> str | None:
    """Run開始イベントのIDを取得"""
    ar = get_ar()
    for event in ar.replay(run_id):
        if event.type == EventType.RUN_STARTED:
            return event.id
    return None


def _get_requirement_created_event_id(run_id: str, requirement_id: str) -> str | None:
    """Requirement作成イベントのIDを取得"""
    ar = get_ar()
    for event in ar.replay(run_id):
        if (
            event.type == EventType.REQUIREMENT_CREATED
            and event.payload.get("requirement_id") == requirement_id
        ):
            return event.id
    return None


router = APIRouter(prefix="/runs/{run_id}/requirements", tags=["Requirements"])


@router.get("", response_model=list[RequirementResponse])
async def get_requirements(run_id: str, pending_only: bool = False):
    """確認要請一覧を取得"""
    ar = get_ar()
    events = list(ar.replay(run_id))
    if not events:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    projection = build_run_projection(events, run_id)

    requirements = []
    for req in projection.pending_requirements:
        requirements.append(
            RequirementResponse(
                id=req.id,
                description=req.description,
                state="pending",
                options=req.metadata.get("options") if req.metadata else None,
                created_at=req.created_at if req.created_at else projection.started_at,
                selected_option=None,
                comment=None,
                resolved_at=None,
            )
        )

    if not pending_only:
        for req in projection.resolved_requirements:
            requirements.append(
                RequirementResponse(
                    id=req.id,
                    description=req.description,
                    state=req.state.value,
                    options=req.metadata.get("options") if req.metadata else None,
                    created_at=req.created_at if req.created_at else projection.started_at,
                    selected_option=req.selected_option,
                    comment=req.comment,
                    resolved_at=req.decided_at,
                )
            )

    return requirements


@router.post("", response_model=RequirementResponse, status_code=status.HTTP_201_CREATED)
async def create_requirement(run_id: str, request: CreateRequirementRequest):
    """確認要請を作成"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    requirement_id = generate_event_id()

    # auto-parents: 明示指定がなければ run.started を親にする
    parents = None
    run_started_id = _get_run_started_event_id(run_id)
    if run_started_id:
        parents = [run_started_id]

    event = RequirementCreatedEvent(
        run_id=run_id,
        actor="api",
        payload={
            "requirement_id": requirement_id,
            "description": request.description,
            "options": request.options,
        },
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    return RequirementResponse(
        id=requirement_id,
        description=request.description,
        state="pending",
        options=request.options,
        created_at=event.timestamp,
    )


@router.post("/{requirement_id}/resolve")
async def resolve_requirement(run_id: str, requirement_id: str, request: ResolveRequirementRequest):
    """確認要請を解決（承認/却下）"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()

    # auto-parents: requirement.created を親にする
    parents = None
    req_created_id = _get_requirement_created_event_id(run_id, requirement_id)
    if req_created_id:
        parents = [req_created_id]

    if request.approved:
        event = RequirementApprovedEvent(
            run_id=run_id,
            actor="user",
            payload={
                "requirement_id": requirement_id,
                "selected_option": request.selected_option,
                "comment": request.comment,
            },
            parents=parents,
        )
    else:
        event = RequirementRejectedEvent(
            run_id=run_id,
            actor="user",
            payload={
                "requirement_id": requirement_id,
                "selected_option": request.selected_option,
                "comment": request.comment,
            },
            parents=parents,
        )

    ar.append(event, run_id)

    return {
        "status": "resolved",
        "requirement_id": requirement_id,
        "approved": request.approved,
    }
