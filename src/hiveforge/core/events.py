"""HiveForge イベントモデル

イミュータブルなイベントの定義とシリアライズ。
全てのイベントはAkashic Recordに永続化される。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

import jcs
from pydantic import BaseModel, Field, computed_field
from ulid import ULID


class EventType(str, Enum):
    """イベント種別"""

    # Run イベント
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_ABORTED = "run.aborted"

    # Task イベント
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_PROGRESSED = "task.progressed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_BLOCKED = "task.blocked"
    TASK_UNBLOCKED = "task.unblocked"

    # Requirement イベント
    REQUIREMENT_CREATED = "requirement.created"
    REQUIREMENT_APPROVED = "requirement.approved"
    REQUIREMENT_REJECTED = "requirement.rejected"

    # LLM イベント
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"

    # システムイベント
    HEARTBEAT = "system.heartbeat"
    ERROR = "system.error"
    SILENCE_DETECTED = "system.silence_detected"
    EMERGENCY_STOP = "system.emergency_stop"


def generate_event_id() -> str:
    """イベントIDを生成 (ULID形式)"""
    return str(ULID())


def _serialize_value(value: Any) -> Any:
    """JCSシリアライズ用に値を変換

    datetime, enum等のJSONシリアライズ不可能な型を文字列に変換する。
    """
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def compute_hash(data: dict[str, Any]) -> str:
    """JCS正規化JSONのSHA-256ハッシュを計算

    Args:
        data: ハッシュ対象のデータ（hashフィールドを除く）

    Returns:
        16進数文字列のSHA-256ハッシュ
    """
    # hashフィールドを除外してコピー
    data_for_hash = {k: v for k, v in data.items() if k != "hash"}
    # datetime, enum等をシリアライズ可能な形式に変換
    data_for_hash = _serialize_value(data_for_hash)
    # JCS (RFC 8785) で正規化
    canonical = jcs.canonicalize(data_for_hash)
    return hashlib.sha256(canonical).hexdigest()


class BaseEvent(BaseModel):
    """イベント基底クラス

    全てのイベントはイミュータブルで、生成時にIDとタイムスタンプが付与される。
    """

    model_config = {
        "frozen": True,
        "ser_json_timedelta": "iso8601",
    }

    id: str = Field(default_factory=generate_event_id, description="イベントID (ULID)")
    type: EventType = Field(..., description="イベント種別")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="イベント発生時刻 (UTC)",
    )
    run_id: str | None = Field(default=None, description="関連するRunのID")
    task_id: str | None = Field(default=None, description="関連するTaskのID")
    actor: str = Field(default="system", description="イベント発生者")
    payload: dict[str, Any] = Field(default_factory=dict, description="イベントペイロード")
    prev_hash: str | None = Field(default=None, description="前イベントのハッシュ（チェーン用）")

    @computed_field
    @property
    def hash(self) -> str:
        """イベントのハッシュ値を計算"""
        return compute_hash(self.model_dump(exclude={"hash"}))

    def to_json(self) -> str:
        """JSON文字列にシリアライズ"""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "BaseEvent":
        """JSON文字列からデシリアライズ"""
        return cls.model_validate_json(json_str)

    def to_jsonl(self) -> str:
        """JSONL形式（改行なし）でシリアライズ"""
        return self.model_dump_json()


# --- 具体的なイベントクラス ---


class RunStartedEvent(BaseEvent):
    """Run開始イベント"""

    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED


class RunCompletedEvent(BaseEvent):
    """Run完了イベント"""

    type: Literal[EventType.RUN_COMPLETED] = EventType.RUN_COMPLETED


class RunFailedEvent(BaseEvent):
    """Run失敗イベント"""

    type: Literal[EventType.RUN_FAILED] = EventType.RUN_FAILED


class TaskCreatedEvent(BaseEvent):
    """Task作成イベント"""

    type: Literal[EventType.TASK_CREATED] = EventType.TASK_CREATED


class TaskAssignedEvent(BaseEvent):
    """Task割り当てイベント"""

    type: Literal[EventType.TASK_ASSIGNED] = EventType.TASK_ASSIGNED


class TaskProgressedEvent(BaseEvent):
    """Task進捗イベント"""

    type: Literal[EventType.TASK_PROGRESSED] = EventType.TASK_PROGRESSED


class TaskCompletedEvent(BaseEvent):
    """Task完了イベント"""

    type: Literal[EventType.TASK_COMPLETED] = EventType.TASK_COMPLETED


class TaskFailedEvent(BaseEvent):
    """Task失敗イベント"""

    type: Literal[EventType.TASK_FAILED] = EventType.TASK_FAILED


class TaskBlockedEvent(BaseEvent):
    """Taskブロックイベント"""

    type: Literal[EventType.TASK_BLOCKED] = EventType.TASK_BLOCKED


class RequirementCreatedEvent(BaseEvent):
    """Requirement作成イベント"""

    type: Literal[EventType.REQUIREMENT_CREATED] = EventType.REQUIREMENT_CREATED


class RequirementApprovedEvent(BaseEvent):
    """Requirement承認イベント"""

    type: Literal[EventType.REQUIREMENT_APPROVED] = EventType.REQUIREMENT_APPROVED


class RequirementRejectedEvent(BaseEvent):
    """Requirement拒否イベント"""

    type: Literal[EventType.REQUIREMENT_REJECTED] = EventType.REQUIREMENT_REJECTED


class HeartbeatEvent(BaseEvent):
    """ハートビートイベント"""

    type: Literal[EventType.HEARTBEAT] = EventType.HEARTBEAT


class ErrorEvent(BaseEvent):
    """エラーイベント"""

    type: Literal[EventType.ERROR] = EventType.ERROR


class SilenceDetectedEvent(BaseEvent):
    """沈黙検出イベント"""

    type: Literal[EventType.SILENCE_DETECTED] = EventType.SILENCE_DETECTED


class EmergencyStopEvent(BaseEvent):
    """緊急停止イベント"""

    type: Literal[EventType.EMERGENCY_STOP] = EventType.EMERGENCY_STOP


# イベントタイプからクラスへのマッピング
EVENT_TYPE_MAP: dict[EventType, type[BaseEvent]] = {
    EventType.RUN_STARTED: RunStartedEvent,
    EventType.RUN_COMPLETED: RunCompletedEvent,
    EventType.RUN_FAILED: RunFailedEvent,
    EventType.TASK_CREATED: TaskCreatedEvent,
    EventType.TASK_ASSIGNED: TaskAssignedEvent,
    EventType.TASK_PROGRESSED: TaskProgressedEvent,
    EventType.TASK_COMPLETED: TaskCompletedEvent,
    EventType.TASK_FAILED: TaskFailedEvent,
    EventType.TASK_BLOCKED: TaskBlockedEvent,
    EventType.REQUIREMENT_CREATED: RequirementCreatedEvent,
    EventType.REQUIREMENT_APPROVED: RequirementApprovedEvent,
    EventType.REQUIREMENT_REJECTED: RequirementRejectedEvent,
    EventType.HEARTBEAT: HeartbeatEvent,
    EventType.ERROR: ErrorEvent,
    EventType.SILENCE_DETECTED: SilenceDetectedEvent,
    EventType.EMERGENCY_STOP: EmergencyStopEvent,
}


def parse_event(data: dict[str, Any] | str) -> BaseEvent:
    """イベントデータをパースして適切なイベントクラスに変換

    Args:
        data: イベントデータ（dictまたはJSON文字列）

    Returns:
        対応するイベントクラスのインスタンス
    """
    if isinstance(data, str):
        data = json.loads(data)

    event_type = EventType(data["type"])
    event_class = EVENT_TYPE_MAP.get(event_type, BaseEvent)
    return event_class.model_validate(data)
