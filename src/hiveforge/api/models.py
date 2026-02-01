"""API リクエスト/レスポンスモデル

FastAPIエンドポイントで使用するPydanticモデル。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# --- Run モデル ---


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
    pending_requirements_count: int = 0
    started_at: datetime | None
    last_heartbeat: datetime | None


class CompleteRunRequest(BaseModel):
    """完了リクエスト"""

    force: bool = Field(
        default=False,
        description="未完了タスクがあっても強制的に完了するか。Trueの場合、未完了タスクは自動的にキャンセルされる",
    )
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


class EmergencyStopRequest(BaseModel):
    """緊急停止リクエスト"""

    reason: str = Field(..., description="停止理由")
    scope: str = Field(default="run", description="停止スコープ（run/system）")


# --- Task モデル ---


class CreateTaskRequest(BaseModel):
    """Task作成リクエスト"""

    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


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
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


class FailTaskRequest(BaseModel):
    """Task失敗リクエスト"""

    error: str
    retryable: bool = True
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


class AssignTaskRequest(BaseModel):
    """Task割り当てリクエスト"""

    assignee: str = Field(default="user", description="担当者名")
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


class ReportProgressRequest(BaseModel):
    """Task進捗報告リクエスト"""

    progress: int = Field(..., ge=0, le=100, description="進捗率(0-100)")
    message: str = Field(default="", description="進捗メッセージ")
    parents: list[str] = Field(default_factory=list, description="親イベントID（因果リンク用）")


# --- Requirement モデル ---


class RequirementResponse(BaseModel):
    """確認要請レスポンス"""

    id: str
    description: str
    state: str
    options: list[str] | None = None
    created_at: datetime
    selected_option: str | None = None
    comment: str | None = None
    resolved_at: datetime | None = None


class CreateRequirementRequest(BaseModel):
    """確認要請作成リクエスト"""

    description: str = Field(..., min_length=1)
    options: list[str] | None = None


class ResolveRequirementRequest(BaseModel):
    """確認要請解決リクエスト"""

    approved: bool
    selected_option: str | None = None
    comment: str | None = None


# --- Event モデル ---


class EventResponse(BaseModel):
    """イベントレスポンス"""

    id: str
    type: str
    timestamp: datetime
    actor: str
    payload: dict[str, Any]
    hash: str
    prev_hash: str | None = None
    parents: list[str] = Field(default_factory=list)


class LineageResponse(BaseModel):
    """因果リンクレスポンス"""

    event_id: str
    ancestors: list[str] = Field(default_factory=list, description="祖先イベントID一覧")
    descendants: list[str] = Field(default_factory=list, description="子孫イベントID一覧")
    truncated: bool = Field(default=False, description="結果が切り詰められたか")


# --- System モデル ---


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""

    status: str
    version: str
    active_runs: int
