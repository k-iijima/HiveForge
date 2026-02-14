"""Runs エンドポイント

Run管理に関するエンドポイント。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...core import RunProjection, build_run_projection, generate_event_id
from ...core.ar.projections import RunState, TaskState
from ...core.events import (
    EmergencyStopEvent,
    EventType,
    HeartbeatEvent,
    RequirementRejectedEvent,
    RunCompletedEvent,
    RunStartedEvent,
    TaskFailedEvent,
)
from ..helpers import apply_event_to_projection, get_active_runs, get_ar
from ..models import (
    CompleteRunRequest,
    EmergencyStopRequest,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
)

router = APIRouter(prefix="/runs", tags=["Runs"])


def _get_task_completed_event_ids(run_id: str, task_ids: set[str]) -> list[str]:
    if not task_ids:
        return []
    ar = get_ar()
    parents: list[str] = []
    for event in ar.replay(run_id):
        if event.type == EventType.TASK_COMPLETED and event.task_id in task_ids:
            parents.append(event.id)
    return parents


@router.post("", response_model=StartRunResponse, status_code=status.HTTP_201_CREATED)
async def start_run(request: StartRunRequest) -> StartRunResponse:
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
async def list_runs(active_only: bool = True) -> list[RunStatusResponse]:
    """Run一覧を取得"""
    ar = get_ar()
    active_runs = get_active_runs()
    results = []

    run_ids = list(active_runs.keys()) if active_only else ar.list_runs()

    for run_id in run_ids:
        proj: RunProjection | None = None
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
async def get_run(run_id: str) -> RunStatusResponse:
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
async def complete_run(run_id: str, request: CompleteRunRequest | None = None) -> dict[str, Any]:
    """Runを完了

    未完了タスクがある場合はエラーを返す。
    force=trueで強制完了する場合、未完了タスクは自動的にキャンセルされる。
    """
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    proj = active_runs[run_id]
    force = request.force if request else False

    # 未完了タスクをチェック
    incomplete_tasks = [
        task
        for task in proj.tasks.values()
        if task.state not in (TaskState.COMPLETED, TaskState.FAILED)
    ]

    # 未解決の確認要請をチェック
    pending_requirements = list(proj.pending_requirements)

    if (incomplete_tasks or pending_requirements) and not force:
        # 未完了タスクまたは未解決の確認要請がある場合はエラー
        detail: dict[str, Any] = {
            "message": "Cannot complete run with incomplete tasks or pending requirements",
            "hint": "強制完了する場合は force=true を指定してください",
        }
        if incomplete_tasks:
            detail["incomplete_task_ids"] = [t.id for t in incomplete_tasks]
        if pending_requirements:
            detail["pending_requirement_ids"] = [r.id for r in pending_requirements]
        raise HTTPException(status_code=400, detail=detail)

    cancelled_task_ids = []
    cancelled_task_event_ids: list[str] = []
    if incomplete_tasks and force:
        # 強制完了: 未完了タスクを自動的にキャンセル
        for task in incomplete_tasks:
            fail_event = TaskFailedEvent(
                run_id=run_id,
                task_id=task.id,
                actor="system",
                payload={
                    "error": "Runが強制完了されたためキャンセル",
                    "retryable": False,
                },
            )
            ar.append(fail_event, run_id)
            apply_event_to_projection(run_id, fail_event)
            cancelled_task_ids.append(task.id)
            cancelled_task_event_ids.append(fail_event.id)

    # 強制完了時は未解決の確認要請も却下する
    cancelled_requirement_ids = []
    cancelled_requirement_event_ids: list[str] = []
    if force:
        for req in pending_requirements:
            reject_event = RequirementRejectedEvent(
                run_id=run_id,
                actor="system",
                payload={
                    "requirement_id": req.id,
                    "comment": "Runが強制完了されたため却下",
                },
            )
            ar.append(reject_event, run_id)
            apply_event_to_projection(run_id, reject_event)
            cancelled_requirement_ids.append(req.id)
            cancelled_requirement_event_ids.append(reject_event.id)

    parents = request.parents if request else []
    if not parents:
        completed_task_ids = {t.id for t in proj.tasks.values() if t.state == TaskState.COMPLETED}
        parents = _get_task_completed_event_ids(run_id, completed_task_ids)
        if force:
            parents = parents + cancelled_task_event_ids + cancelled_requirement_event_ids

    event = RunCompletedEvent(run_id=run_id, actor="api", parents=parents)
    ar.append(event, run_id)

    active_runs.pop(run_id)
    proj.state = RunState.COMPLETED
    proj.completed_at = event.timestamp

    result: dict[str, Any] = {"status": "completed", "run_id": run_id}
    if cancelled_task_ids:
        result["cancelled_task_ids"] = cancelled_task_ids
    if cancelled_requirement_ids:
        result["cancelled_requirement_ids"] = cancelled_requirement_ids
    return result


@router.post("/{run_id}/emergency-stop")
async def emergency_stop(run_id: str, request: EmergencyStopRequest) -> dict[str, Any]:
    """緊急停止

    進行中の全タスクを中断し、未解決の確認要請を却下し、Runを即座に停止する。
    """
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    proj = active_runs[run_id]

    # 未完了タスクを全て失敗にする
    cancelled_task_ids = []
    incomplete_tasks = [
        task
        for task in proj.tasks.values()
        if task.state not in (TaskState.COMPLETED, TaskState.FAILED)
    ]
    for task in incomplete_tasks:
        fail_event = TaskFailedEvent(
            run_id=run_id,
            task_id=task.id,
            actor="system",
            payload={
                "error": f"緊急停止: {request.reason}",
                "retryable": False,
            },
        )
        ar.append(fail_event, run_id)
        apply_event_to_projection(run_id, fail_event)
        cancelled_task_ids.append(task.id)

    # 未解決の確認要請を全て却下する
    cancelled_requirement_ids = []
    for req in proj.pending_requirements:
        reject_event = RequirementRejectedEvent(
            run_id=run_id,
            actor="system",
            payload={
                "requirement_id": req.id,
                "comment": f"緊急停止により却下: {request.reason}",
            },
        )
        ar.append(reject_event, run_id)
        apply_event_to_projection(run_id, reject_event)
        cancelled_requirement_ids.append(req.id)

    event = EmergencyStopEvent(
        run_id=run_id,
        actor="api",
        payload={"reason": request.reason, "scope": request.scope},
    )
    ar.append(event, run_id)

    active_runs.pop(run_id)
    proj.state = RunState.ABORTED
    proj.completed_at = event.timestamp

    result: dict[str, Any] = {
        "status": "aborted",
        "run_id": run_id,
        "reason": request.reason,
        "stopped_at": event.timestamp.isoformat(),
    }
    if cancelled_task_ids:
        result["cancelled_task_ids"] = cancelled_task_ids
    if cancelled_requirement_ids:
        result["cancelled_requirement_ids"] = cancelled_requirement_ids
    return result


@router.post("/{run_id}/heartbeat")
async def send_heartbeat(run_id: str) -> dict[str, Any]:
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
