"""HiveForge イベントモデル

イミュータブルなイベントの定義とシリアライズ。
全てのイベントはAkashic Recordに永続化される。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

import jcs
from pydantic import BaseModel, Field, computed_field
from ulid import ULID


class EventType(str, Enum):
    """イベント種別"""

    # Hive イベント
    HIVE_CREATED = "hive.created"
    HIVE_CLOSED = "hive.closed"

    # Colony イベント
    COLONY_CREATED = "colony.created"
    COLONY_STARTED = "colony.started"
    COLONY_COMPLETED = "colony.completed"
    COLONY_FAILED = "colony.failed"

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

    # Decision イベント（仕様変更・合意事項の記録など）
    DECISION_RECORDED = "decision.recorded"

    # Decision Protocol（意思決定ライフサイクル、v5.1追加）
    PROPOSAL_CREATED = "decision.proposal.created"  # 提案作成
    DECISION_APPLIED = "decision.applied"  # 決定適用
    DECISION_SUPERSEDED = "decision.superseded"  # 決定上書き

    # Conference（会議ライフサイクル、v5.1追加）
    CONFERENCE_STARTED = "conference.started"  # 会議開始
    CONFERENCE_ENDED = "conference.ended"  # 会議終了

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
        default_factory=lambda: datetime.now(UTC),
        description="イベント発生時刻 (UTC)",
    )
    run_id: str | None = Field(default=None, description="関連するRunのID")
    task_id: str | None = Field(default=None, description="関連するTaskのID")
    actor: str = Field(default="system", description="イベント発生者")
    payload: dict[str, Any] = Field(default_factory=dict, description="イベントペイロード")
    prev_hash: str | None = Field(default=None, description="前イベントのハッシュ（チェーン用）")
    parents: list[str] = Field(
        default_factory=list,
        description="親イベントのID（因果リンク用）",
    )

    @computed_field
    @property
    def hash(self) -> str:
        """イベントのハッシュ値を計算"""
        return compute_hash(self.model_dump(exclude={"hash"}))

    def to_json(self) -> str:
        """JSON文字列にシリアライズ"""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> BaseEvent:
        """JSON文字列からデシリアライズ"""
        return cls.model_validate_json(json_str)

    def to_jsonl(self) -> str:
        """JSONL形式（改行なし）でシリアライズ"""
        return self.model_dump_json()


# --- 具体的なイベントクラス ---


# Hive イベント
class HiveCreatedEvent(BaseEvent):
    """Hive作成イベント

    Hiveは複数のColonyを管理する最上位のコンテナ。
    run_idは持たず、payload内のhive_idで識別される。
    """

    type: Literal[EventType.HIVE_CREATED] = EventType.HIVE_CREATED


class HiveClosedEvent(BaseEvent):
    """Hive終了イベント"""

    type: Literal[EventType.HIVE_CLOSED] = EventType.HIVE_CLOSED


# Colony イベント
class ColonyCreatedEvent(BaseEvent):
    """Colony作成イベント

    ColonyはHive内のサブプロジェクト単位。
    複数のRunを束ねて1つの目標に向かう。
    """

    type: Literal[EventType.COLONY_CREATED] = EventType.COLONY_CREATED


class ColonyStartedEvent(BaseEvent):
    """Colony開始イベント"""

    type: Literal[EventType.COLONY_STARTED] = EventType.COLONY_STARTED


class ColonyCompletedEvent(BaseEvent):
    """Colony完了イベント"""

    type: Literal[EventType.COLONY_COMPLETED] = EventType.COLONY_COMPLETED


class ColonyFailedEvent(BaseEvent):
    """Colony失敗イベント"""

    type: Literal[EventType.COLONY_FAILED] = EventType.COLONY_FAILED


# Run イベント
class RunStartedEvent(BaseEvent):
    """Run開始イベント"""

    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED


class RunCompletedEvent(BaseEvent):
    """Run完了イベント"""

    type: Literal[EventType.RUN_COMPLETED] = EventType.RUN_COMPLETED


class RunFailedEvent(BaseEvent):
    """Run失敗イベント"""

    type: Literal[EventType.RUN_FAILED] = EventType.RUN_FAILED


class RunAbortedEvent(BaseEvent):
    """Run中断イベント"""

    type: Literal[EventType.RUN_ABORTED] = EventType.RUN_ABORTED


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


class TaskUnblockedEvent(BaseEvent):
    """Taskブロック解除イベント"""

    type: Literal[EventType.TASK_UNBLOCKED] = EventType.TASK_UNBLOCKED


class RequirementCreatedEvent(BaseEvent):
    """Requirement作成イベント"""

    type: Literal[EventType.REQUIREMENT_CREATED] = EventType.REQUIREMENT_CREATED


class RequirementApprovedEvent(BaseEvent):
    """Requirement承認イベント"""

    type: Literal[EventType.REQUIREMENT_APPROVED] = EventType.REQUIREMENT_APPROVED


class RequirementRejectedEvent(BaseEvent):
    """Requirement拒否イベント"""

    type: Literal[EventType.REQUIREMENT_REJECTED] = EventType.REQUIREMENT_REJECTED


class DecisionRecordedEvent(BaseEvent):
    """Decision記録イベント

    仕様変更や判断事項（Decision）をイベントとして永続化する。
    具体的な内容は payload に保持する。
    """

    type: Literal[EventType.DECISION_RECORDED] = EventType.DECISION_RECORDED


# Decision Protocol イベント（v5.1追加）
class ProposalCreatedEvent(BaseEvent):
    """提案作成イベント

    Decision Protocol: 意思決定ライフサイクルの最初のステップ。
    ColonyやBeekeeperが新しい提案を作成した時に発行する。

    payload:
        proposal_id: 提案ID
        proposer: 提案者（Colony ID or "user"）
        title: 提案タイトル
        description: 詳細説明
        options: 選択肢（あれば）
    """

    type: Literal[EventType.PROPOSAL_CREATED] = EventType.PROPOSAL_CREATED


class DecisionAppliedEvent(BaseEvent):
    """決定適用イベント

    Decision Protocol: 決定が実際に適用（実装）された時に発行する。

    payload:
        decision_id: 決定ID
        proposal_id: 対応する提案ID
        applied_by: 適用者
        applied_to: 適用対象（ファイルパス等）
    """

    type: Literal[EventType.DECISION_APPLIED] = EventType.DECISION_APPLIED


class DecisionSupersededEvent(BaseEvent):
    """決定上書きイベント

    Decision Protocol: 以前の決定が新しい決定で置き換えられた時に発行する。
    過去の決定を無効化するのではなく、新しい決定が優先されることを示す。

    payload:
        old_decision_id: 以前の決定ID
        new_decision_id: 新しい決定ID
        reason: 上書き理由
    """

    type: Literal[EventType.DECISION_SUPERSEDED] = EventType.DECISION_SUPERSEDED


# Conference イベント（v5.1追加）
class ConferenceStartedEvent(BaseEvent):
    """会議開始イベント

    Conference: Beekeeperと複数ColonyのQueen Beeが同時に対話するセッション。
    会議の開始時に発行する。

    payload:
        conference_id: 会議ID
        hive_id: Hive ID
        participants: 参加Colony IDリスト
        topic: 議題
        initiated_by: 開始者
    """

    type: Literal[EventType.CONFERENCE_STARTED] = EventType.CONFERENCE_STARTED


class ConferenceEndedEvent(BaseEvent):
    """会議終了イベント

    Conference: 会議の終了時に発行する。
    決定事項のサマリーを含む。

    payload:
        conference_id: 会議ID
        duration_seconds: 会議時間（秒）
        decisions_made: 決定IDリスト
        summary: サマリー
        ended_by: 終了者
    """

    type: Literal[EventType.CONFERENCE_ENDED] = EventType.CONFERENCE_ENDED


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
    # Hive
    EventType.HIVE_CREATED: HiveCreatedEvent,
    EventType.HIVE_CLOSED: HiveClosedEvent,
    # Colony
    EventType.COLONY_CREATED: ColonyCreatedEvent,
    EventType.COLONY_STARTED: ColonyStartedEvent,
    EventType.COLONY_COMPLETED: ColonyCompletedEvent,
    EventType.COLONY_FAILED: ColonyFailedEvent,
    # Run
    EventType.RUN_STARTED: RunStartedEvent,
    EventType.RUN_COMPLETED: RunCompletedEvent,
    EventType.RUN_FAILED: RunFailedEvent,
    EventType.RUN_ABORTED: RunAbortedEvent,
    EventType.TASK_CREATED: TaskCreatedEvent,
    EventType.TASK_ASSIGNED: TaskAssignedEvent,
    EventType.TASK_PROGRESSED: TaskProgressedEvent,
    EventType.TASK_COMPLETED: TaskCompletedEvent,
    EventType.TASK_FAILED: TaskFailedEvent,
    EventType.TASK_BLOCKED: TaskBlockedEvent,
    EventType.TASK_UNBLOCKED: TaskUnblockedEvent,
    EventType.REQUIREMENT_CREATED: RequirementCreatedEvent,
    EventType.REQUIREMENT_APPROVED: RequirementApprovedEvent,
    EventType.REQUIREMENT_REJECTED: RequirementRejectedEvent,
    EventType.DECISION_RECORDED: DecisionRecordedEvent,
    # Decision Protocol (v5.1)
    EventType.PROPOSAL_CREATED: ProposalCreatedEvent,
    EventType.DECISION_APPLIED: DecisionAppliedEvent,
    EventType.DECISION_SUPERSEDED: DecisionSupersededEvent,
    # Conference (v5.1)
    EventType.CONFERENCE_STARTED: ConferenceStartedEvent,
    EventType.CONFERENCE_ENDED: ConferenceEndedEvent,
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
