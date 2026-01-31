"""HiveForge Core API

FastAPIベースのREST API。
Run管理、Task操作、イベント取得などを提供。
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..core import (
    AkashicRecord,
    EventType,
    RunProjection,
    build_run_projection,
    get_settings,
    generate_event_id,
)
from ..core.events import (
    RunStartedEvent,
    RunCompletedEvent,
    TaskCreatedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    HeartbeatEvent,
    parse_event,
)
from ..core.ar.projections import RunState, TaskState


# --- グローバル状態 ---
_ar: AkashicRecord | None = None
_active_runs: dict[str, RunProjection] = {}


def get_ar() -> AkashicRecord:
    """Akashic Recordインスタンスを取得"""
    global _ar
    if _ar is None:
        settings = get_settings()
        _ar = AkashicRecord(settings.get_vault_path())
    return _ar


# --- リクエスト/レスポンスモデル ---


class StartRunRequest(BaseModel):
    """Run開始リクエスト"""

    goal: str = Field(..., min_length=1, max_length=1000, description="Runの目標")
    metadata: dict[str, Any] = Field(default_factory=dict)


class StartRunResponse(BaseModel):
    """Run開始レスポンス"""

    run_id: str
    goal: str
    state: str
    started_at: datetime


class CreateTaskRequest(BaseModel):
    """Task作成リクエスト"""

    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Taskレスポンス"""

    task_id: str
    title: str
    state: str
    progress: int
    assignee: str | None = None


class CompleteTaskRequest(BaseModel):
    """Task完了リクエスト"""

    result: dict[str, Any] = Field(default_factory=dict)


class FailTaskRequest(BaseModel):
    """Task失敗リクエスト"""

    error: str
    retryable: bool = True


class RunStatusResponse(BaseModel):
    """Run状態レスポンス"""

    run_id: str
    goal: str
    state: str
    event_count: int
    tasks_total: int
    tasks_completed: int
    tasks_failed: int
    tasks_in_progress: int
    started_at: datetime | None
    last_heartbeat: datetime | None


class EventResponse(BaseModel):
    """イベントレスポンス"""

    id: str
    type: str
    timestamp: datetime
    actor: str
    payload: dict[str, Any]


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""

    status: str
    version: str
    active_runs: int


# --- ライフサイクル ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル"""
    # 起動時
    settings = get_settings()
    global _ar
    _ar = AkashicRecord(settings.get_vault_path())

    # 既存のRunを復元
    for run_id in _ar.list_runs():
        events = list(_ar.replay(run_id))
        if events:
            projection = build_run_projection(events, run_id)
            if projection.state == RunState.RUNNING:
                _active_runs[run_id] = projection

    yield

    # シャットダウン時
    _ar = None
    _active_runs.clear()


# --- FastAPIアプリケーション ---

app = FastAPI(
    title="HiveForge Core API",
    description="自律型ソフトウェア組立システム HiveForge のコアAPI",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番では制限すること
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- エンドポイント ---


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """ヘルスチェック"""
    from ..core import __version__ if hasattr(__import__("hiveforge.core"), "__version__") else "0.1.0"
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        active_runs=len(_active_runs),
    )


@app.post("/runs", response_model=StartRunResponse, status_code=status.HTTP_201_CREATED, tags=["Runs"])
async def start_run(request: StartRunRequest):
    """新しいRunを開始"""
    ar = get_ar()
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
    _active_runs[run_id] = projection

    return StartRunResponse(
        run_id=run_id,
        goal=request.goal,
        state=projection.state.value,
        started_at=event.timestamp,
    )


@app.get("/runs", response_model=list[RunStatusResponse], tags=["Runs"])
async def list_runs(active_only: bool = True):
    """Run一覧を取得"""
    ar = get_ar()
    results = []

    run_ids = list(_active_runs.keys()) if active_only else ar.list_runs()

    for run_id in run_ids:
        if run_id in _active_runs:
            proj = _active_runs[run_id]
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
                    tasks_failed=len([t for t in proj.tasks.values() if t.state == TaskState.FAILED]),
                    tasks_in_progress=len(proj.in_progress_tasks),
                    started_at=proj.started_at,
                    last_heartbeat=proj.last_heartbeat,
                )
            )

    return results


@app.get("/runs/{run_id}", response_model=RunStatusResponse, tags=["Runs"])
async def get_run(run_id: str):
    """Run詳細を取得"""
    ar = get_ar()

    if run_id in _active_runs:
        proj = _active_runs[run_id]
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
        started_at=proj.started_at,
        last_heartbeat=proj.last_heartbeat,
    )


@app.post("/runs/{run_id}/complete", tags=["Runs"])
async def complete_run(run_id: str):
    """Runを完了"""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    event = RunCompletedEvent(run_id=run_id, actor="api")
    ar.append(event, run_id)

    proj = _active_runs.pop(run_id)
    proj.state = RunState.COMPLETED
    proj.completed_at = event.timestamp

    return {"status": "completed", "run_id": run_id}


@app.post("/runs/{run_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(run_id: str, request: CreateTaskRequest):
    """Taskを作成"""
    if run_id not in _active_runs:
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
    )
    ar.append(event, run_id)

    # 投影を更新
    from ..core.ar.projections import RunProjector
    projector = RunProjector(run_id)
    projector.projection = _active_runs[run_id]
    projector.apply(event)

    task = _active_runs[run_id].tasks[task_id]

    return TaskResponse(
        task_id=task_id,
        title=task.title,
        state=task.state.value,
        progress=task.progress,
        assignee=task.assignee,
    )


@app.get("/runs/{run_id}/tasks", response_model=list[TaskResponse], tags=["Tasks"])
async def list_tasks(run_id: str):
    """Task一覧を取得"""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = _active_runs[run_id]
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


@app.post("/runs/{run_id}/tasks/{task_id}/complete", tags=["Tasks"])
async def complete_task(run_id: str, task_id: str, request: CompleteTaskRequest):
    """Taskを完了"""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = _active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()
    event = TaskCompletedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"result": request.result},
    )
    ar.append(event, run_id)

    # 投影を更新
    from ..core.ar.projections import RunProjector
    projector = RunProjector(run_id)
    projector.projection = proj
    projector.apply(event)

    return {"status": "completed", "task_id": task_id}


@app.post("/runs/{run_id}/tasks/{task_id}/fail", tags=["Tasks"])
async def fail_task(run_id: str, task_id: str, request: FailTaskRequest):
    """Taskを失敗"""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    proj = _active_runs[run_id]
    if task_id not in proj.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    ar = get_ar()
    event = TaskFailedEvent(
        run_id=run_id,
        task_id=task_id,
        actor="api",
        payload={"error": request.error, "retryable": request.retryable},
    )
    ar.append(event, run_id)

    # 投影を更新
    from ..core.ar.projections import RunProjector
    projector = RunProjector(run_id)
    projector.projection = proj
    projector.apply(event)

    return {"status": "failed", "task_id": task_id}


@app.get("/runs/{run_id}/events", response_model=list[EventResponse], tags=["Events"])
async def get_events(run_id: str, since: datetime | None = None, limit: int = 100):
    """イベント一覧を取得"""
    ar = get_ar()
    events = []

    for event in ar.replay(run_id, since=since):
        events.append(
            EventResponse(
                id=event.id,
                type=event.type.value,
                timestamp=event.timestamp,
                actor=event.actor,
                payload=event.payload,
            )
        )
        if len(events) >= limit:
            break

    return events


@app.post("/runs/{run_id}/heartbeat", tags=["System"])
async def send_heartbeat(run_id: str):
    """ハートビートを送信"""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found")

    ar = get_ar()
    event = HeartbeatEvent(run_id=run_id, actor="api")
    ar.append(event, run_id)

    # 投影を更新
    _active_runs[run_id].last_heartbeat = event.timestamp

    return {"status": "ok", "timestamp": event.timestamp}
