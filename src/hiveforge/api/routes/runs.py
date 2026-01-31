"""Runs エンドポイント

Run管理に関するエンドポイント。
"""

from fastapi import APIRouter, HTTPException, status

from ...core import RunProjection, build_run_projection, generate_event_id
from ...core.events import (
    EmergencyStopEvent,
    HeartbeatEvent,
    RunCompletedEvent,
    RunStartedEvent,
)
from ...core.ar.projections import RunState, TaskState
from ..helpers import apply_event_to_projection, get_active_runs, get_ar
from ..models import (
    EmergencyStopRequest,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
)


router = APIRouter(prefix="/runs", tags=["Runs"])


@router.post("", response_model=StartRunResponse, status_code=status.HTTP_201_CREATED)
async def start_run(request: StartRunRequest):
    """新しいRunを開始"""
    ar = get_ar()
    active_runs = get_active_runs()
    run_id = generate_event_id()

    event = RunStartedEvent(
        run_id=run_id,
        actor="api",
        payload={"goal": request.goal, "metadata": request.metadata},
    )
    ar.append(event, run_id)

    projection = RunProjection(
        id=run_id,
        goal=request.goal,
        state=RunState.RUNNING,
        started_at=event.timestamp,
    )
    active_runs[run_id] = projection

    return StartRunResponse(
        run_id=run_id,
        goal=request.goal,
        state=projection.state.value,
        started_at=event.timestamp,
    )


@router.get("", response_model=list[RunStatusResponse])
async def list_runs(active_only: bool = True):
    """Run一覧を取得"""
    ar = get_ar()
    active_runs = get_active_runs()
    results = []

    run_ids = list(active_runs.keys()) if active_only else ar.list_runs()

    for run_id in run_ids:
        if run_id in active_runs:
            proj = active_runs[run_id]
        else:
            events = list(ar.replay(run_id))
            proj = build_run_projection(events, run_id) if events else None

        if proj:
            results.append(
                RunStatusResponse(
                    run_id=proj.id,
                    goal=proj.goal,
                    state=proj.state.value,
                    event_count=proj.event_count,
                    tasks_total=len(proj.tasks),
                    tasks_completed=len(proj.completed_tasks),
                    tasks_failed=len(
                        [t for t in proj.tasks.values() if t.state == TaskState.FAILED]
                    ),
                    tasks_in_progress=len(proj.in_progress_tasks),
                    pending_requirements_count=len(proj.pending_requirements),
                    started_at=proj.started_at,
                    last_heartbeat=proj.last_heartbeat,
                )
            )

    return results


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str):
    """Run詳細を取得"""
    ar = get_ar()
    active_runs = get_active_runs()

    if run_id in active_runs:
        proj = active_runs[run_id]
    else:
        events = list(ar.replay(run_id))
        if not events:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        proj = build_run_projection(events, run_id)

    return RunStatusResponse(
        run_id=proj.id,
        goal=proj.goal,
        state=proj.state.value,
        event_count=proj.event_count,
        tasks_total=len(proj.tasks),
        tasks_completed=len(proj.completed_tasks),
        tasks_failed=len([t for t in proj.tasks.values() if t.state == TaskState.FAILED]),
        tasks_in_progress=len(proj.in_progress_tasks),
        pending_requirements_count=len(proj.pending_requirements),
        started_at=proj.started_at,
        last_heartbeat=proj.last_heartbeat,
    )


@router.post("/{run_id}/complete")
async def complete_run(run_id: str):
    """Runを完了"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    event = RunCompletedEvent(run_id=run_id, actor="api")
    ar.append(event, run_id)

    proj = active_runs.pop(run_id)
    proj.state = RunState.COMPLETED
    proj.completed_at = event.timestamp

    return {"status": "completed", "run_id": run_id}


@router.post("/{run_id}/emergency-stop")
async def emergency_stop(run_id: str, request: EmergencyStopRequest):
    """Runを緊急停止する

    進行中の全タスクを中断し、Runを即座に停止する。
    """
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    event = EmergencyStopEvent(
        run_id=run_id,
        actor="api",
        payload={"reason": request.reason, "scope": request.scope},
    )
    ar.append(event, run_id)

    proj = active_runs.pop(run_id)
    proj.state = RunState.ABORTED
    proj.completed_at = event.timestamp

    return {
        "status": "aborted",
        "run_id": run_id,
        "reason": request.reason,
        "stopped_at": event.timestamp.isoformat(),
    }


@router.post("/{run_id}/heartbeat")
async def send_heartbeat(run_id: str):
    """ハートビートを送信"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    event = HeartbeatEvent(run_id=run_id, actor="api")
    ar.append(event, run_id)

    # 投影を更新
    active_runs[run_id].last_heartbeat = event.timestamp

    return {"status": "ok", "timestamp": event.timestamp}
