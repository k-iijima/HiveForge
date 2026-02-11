"""Tasks エンドポイント

Task管理に関するエンドポイント。
"""

from fastapi import APIRouter, HTTPException, status

from ...core import build_run_projection, generate_event_id
from ...core.events import (
    EventType,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskProgressedEvent,
)
from ..helpers import apply_event_to_projection, get_active_runs, get_ar
from ..models import (
    AssignTaskRequest,
    CompleteTaskRequest,
    CreateTaskRequest,
    FailTaskRequest,
    ReportProgressRequest,
    TaskResponse,
)

router = APIRouter(prefix="/runs/{run_id}/tasks", tags=["Tasks"])


def _get_run_started_event_id(run_id: str) -> str | None:
    ar = get_ar()
    for event in ar.replay(run_id):
        if event.type == EventType.RUN_STARTED:
            return event.id
    return None


def _get_task_created_event_id(run_id: str, task_id: str) -> str | None:
    ar = get_ar()
    for event in ar.replay(run_id):
        if event.type == EventType.TASK_CREATED and event.task_id == task_id:
            return event.id
    return None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(run_id: str, request: CreateTaskRequest):
    """Taskを作成"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    task_id = generate_event_id()

    parents = request.parents
    if not parents:
        run_started_id = _get_run_started_event_id(run_id)
        if run_started_id:
            parents = [run_started_id]

    event = TaskCreatedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={
            "title": request.title,
            "description": request.description,
            "metadata": request.metadata,
        },
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    task = active_runs[run_id].tasks[task_id]

    return TaskResponse(
        task_id=task_id,
        title=task.title,
        state=task.state.value,
        progress=task.progress,
        assignee=task.assignee,
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(run_id: str):
    """Task一覧を取得"""
    active_runs = get_active_runs()
    ar = get_ar()

    if run_id in active_runs:
        proj = active_runs[run_id]
    else:
        # 完了済みRunはイベントからプロジェクションを再構築
        events = list(ar.replay(run_id))
        if not events:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        proj = build_run_projection(events, run_id)

    return [
        TaskResponse(
            task_id=task.id,
            title=task.title,
            state=task.state.value,
            progress=task.progress,
            assignee=task.assignee,
        )
        for task in proj.tasks.values()
    ]


@router.post("/{task_id}/complete")
async def complete_task(run_id: str, task_id: str, request: CompleteTaskRequest):
    """Taskを完了"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()

    parents = request.parents
    if not parents:
        created_id = _get_task_created_event_id(run_id, task_id)
        if created_id:
            parents = [created_id]

    event = TaskCompletedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"result": request.result},
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    return {"status": "completed", "task_id": task_id}


@router.post("/{task_id}/fail")
async def fail_task(run_id: str, task_id: str, request: FailTaskRequest):
    """Taskを失敗"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()

    parents = request.parents
    if not parents:
        created_id = _get_task_created_event_id(run_id, task_id)
        if created_id:
            parents = [created_id]

    event = TaskFailedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"error": request.error, "retryable": request.retryable},
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    return {"status": "failed", "task_id": task_id}


@router.post("/{task_id}/assign")
async def assign_task(run_id: str, task_id: str, request: AssignTaskRequest):
    """Taskを担当者に割り当て"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()

    parents = request.parents
    if not parents:
        created_id = _get_task_created_event_id(run_id, task_id)
        if created_id:
            parents = [created_id]

    event = TaskAssignedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"assignee": request.assignee},
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    return {"status": "assigned", "task_id": task_id, "assignee": request.assignee}


@router.post("/{task_id}/progress")
async def report_progress(run_id: str, task_id: str, request: ReportProgressRequest):
    """Taskの進捗を報告"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()

    parents = request.parents
    if not parents:
        created_id = _get_task_created_event_id(run_id, task_id)
        if created_id:
            parents = [created_id]

    event = TaskProgressedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"progress": request.progress, "message": request.message},
        parents=parents,
    )
    ar.append(event, run_id)

    # 投影を更新
    apply_event_to_projection(run_id, event)

    task = proj.tasks[task_id]
    return {
        "status": "updated",
        "task_id": task_id,
        "progress": task.progress,
    }
