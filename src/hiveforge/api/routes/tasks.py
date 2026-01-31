"""Tasks エンドポイント

Task管理に関するエンドポイント。
"""

from fastapi import APIRouter, HTTPException, status

from ...core import generate_event_id
from ...core.events import (
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


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(run_id: str, request: CreateTaskRequest):
    """Taskを作成"""
    active_runs = get_active_runs()
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    task_id = generate_event_id()

    event = TaskCreatedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={
            "title": request.title,
            "description": request.description,
            "metadata": request.metadata,
        },
        parents=request.parents,
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
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = active_runs[run_id]
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
    event = TaskCompletedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"result": request.result},
        parents=request.parents,
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
    event = TaskFailedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"error": request.error, "retryable": request.retryable},
        parents=request.parents,
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
    event = TaskAssignedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"assignee": request.assignee},
        parents=request.parents,
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
    event = TaskProgressedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"progress": request.progress, "message": request.message},
        parents=request.parents,
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
