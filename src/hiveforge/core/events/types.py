"""イベントタイプと関連列挙型

EventType enum と関連する列挙型（ConflictCategory等）を定義。
"""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """イベント種別"""

    # Hive イベント
    HIVE_CREATED = "hive.created"
    HIVE_CLOSED = "hive.closed"

    # Colony イベント
    COLONY_CREATED = "colony.created"
    COLONY_STARTED = "colony.started"
    COLONY_SUSPENDED = "colony.suspended"
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

    # Conflict Detection（衝突検出・解決、v5.1追加）
    CONFLICT_DETECTED = "conflict.detected"  # 衝突検出
    CONFLICT_RESOLVED = "conflict.resolved"  # 衝突解決

    # Operation Failure/Timeout（標準エラー分類、v5.1追加）
    OPERATION_TIMEOUT = "operation.timeout"  # タイムアウト
    OPERATION_FAILED = "operation.failed"  # 失敗

    # Direct Intervention（直接介入、v5.2追加）
    USER_DIRECT_INTERVENTION = "intervention.user_direct"  # ユーザー直接介入
    QUEEN_ESCALATION = "intervention.queen_escalation"  # Queen直訴
    BEEKEEPER_FEEDBACK = "intervention.beekeeper_feedback"  # Beekeeper改善フィードバック

    # Worker Bee イベント（Phase 2追加）
    WORKER_ASSIGNED = "worker.assigned"  # Worker Beeにタスク割り当て
    WORKER_STARTED = "worker.started"  # Worker Bee作業開始
    WORKER_PROGRESS = "worker.progress"  # Worker Bee進捗報告
    WORKER_COMPLETED = "worker.completed"  # Worker Bee作業完了
    WORKER_FAILED = "worker.failed"  # Worker Bee作業失敗

    # LLM イベント
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"

    # Sentinel Hornet イベント（M2-0追加）
    SENTINEL_ALERT_RAISED = "sentinel.alert_raised"
    SENTINEL_REPORT = "sentinel.report"

    # Guard Bee イベント（M3-3追加）
    GUARD_VERIFICATION_REQUESTED = "guard.verification_requested"
    GUARD_PASSED = "guard.passed"
    GUARD_CONDITIONAL_PASSED = "guard.conditional_passed"
    GUARD_FAILED = "guard.failed"

    # システムイベント
    HEARTBEAT = "system.heartbeat"
    ERROR = "system.error"
    SILENCE_DETECTED = "system.silence_detected"
    EMERGENCY_STOP = "system.emergency_stop"


class ConflictCategory(str, Enum):
    """衝突カテゴリ（v5.2追加）"""

    ASSUMPTION = "assumption"
    PRIORITY = "priority"
    DEPENDENCY = "dependency"
    CONSTRAINT = "constraint"


class ConflictSeverity(str, Enum):
    """衝突の深刻度（v5.2追加）"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKER = "blocker"


class EscalationType(str, Enum):
    """エスカレーション種別（v5.2追加）"""

    BEEKEEPER_CONFLICT = "beekeeper_conflict"
    RESOURCE_SHORTAGE = "resource_shortage"
    TECHNICAL_BLOCKER = "technical_blocker"
    SCOPE_CLARIFICATION = "scope_clarification"
    PRIORITY_DISPUTE = "priority_dispute"
    EXTERNAL_DEPENDENCY = "external_dependency"


class DecisionScope(str, Enum):
    """決定の適用範囲（v5.2追加）"""

    HIVE = "hive"
    COLONY = "colony"
    RUN = "run"
    TASK = "task"


class RiskLevel(str, Enum):
    """リスクレベル（v5.2追加）"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FailureReason(str, Enum):
    """失敗理由の標準分類"""

    TIMEOUT = "timeout"
    TOOL_ERROR = "tool_error"
    CONTEXT_MISSING = "context_missing"
    PERMISSION_DENIED = "permission_denied"
    CONFLICT = "conflict"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
