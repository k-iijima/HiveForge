"""Standard Failure/Timeout イベント型のテスト

外部フィードバック対応: 共通のエラー分類と失敗理由の標準化。
"""


from hiveforge.core.events import (
    EVENT_TYPE_MAP,
    EventType,
    OperationFailedEvent,
    OperationTimeoutEvent,
    parse_event,
)


class TestFailureTimeoutEventTypes:
    """Failure/Timeout イベント型がEventTypeに定義されているかテスト"""

    def test_operation_timeout_event_type_exists(self):
        """OPERATION_TIMEOUTイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.OPERATION_TIMEOUT

        # Assert
        assert event_type.value == "operation.timeout"

    def test_operation_failed_event_type_exists(self):
        """OPERATION_FAILEDイベント型が存在する"""
        # Arrange & Act
        event_type = EventType.OPERATION_FAILED

        # Assert
        assert event_type.value == "operation.failed"


class TestOperationTimeoutEvent:
    """OperationTimeoutEvent のテスト"""

    def test_create_timeout_event(self):
        """タイムアウトイベントを生成できる"""
        # Arrange
        payload = {
            "operation_id": "op-001",
            "operation_type": "file_read",
            "timeout_seconds": 30,
            "waited_seconds": 30.5,
        }

        # Act
        event = OperationTimeoutEvent(
            actor="worker-bee-001",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.OPERATION_TIMEOUT
        assert event.payload["operation_id"] == "op-001"
        assert event.payload["timeout_seconds"] == 30

    def test_timeout_event_with_task_context(self):
        """タスクコンテキスト付きタイムアウト"""
        # Arrange
        payload = {
            "operation_id": "op-002",
            "operation_type": "llm_request",
            "timeout_seconds": 60,
            "waited_seconds": 61.2,
        }

        # Act
        event = OperationTimeoutEvent(
            actor="worker-bee-001",
            task_id="task-001",
            run_id="run-001",
            payload=payload,
        )

        # Assert
        assert event.task_id == "task-001"
        assert event.run_id == "run-001"


class TestOperationFailedEvent:
    """OperationFailedEvent のテスト"""

    def test_create_failed_event_tool_error(self):
        """ツールエラーによる失敗イベント"""
        # Arrange
        payload = {
            "operation_id": "op-003",
            "operation_type": "file_write",
            "failure_reason": "tool_error",
            "error_message": "Permission denied: /etc/passwd",
        }

        # Act
        event = OperationFailedEvent(
            actor="worker-bee-002",
            payload=payload,
        )

        # Assert
        assert event.type == EventType.OPERATION_FAILED
        assert event.payload["failure_reason"] == "tool_error"

    def test_failed_event_context_missing(self):
        """コンテキスト不足による失敗"""
        # Arrange
        payload = {
            "operation_id": "op-004",
            "operation_type": "code_analysis",
            "failure_reason": "context_missing",
            "error_message": "Required file not found",
            "missing_context": ["src/config.py", "requirements.txt"],
        }

        # Act
        event = OperationFailedEvent(actor="worker-bee-001", payload=payload)

        # Assert
        assert event.payload["failure_reason"] == "context_missing"
        assert len(event.payload["missing_context"]) == 2

    def test_failed_event_permission_denied(self):
        """権限不足による失敗"""
        # Arrange
        payload = {
            "operation_id": "op-005",
            "operation_type": "api_call",
            "failure_reason": "permission_denied",
            "error_message": "API key not authorized",
        }

        # Act
        event = OperationFailedEvent(actor="worker-bee-001", payload=payload)

        # Assert
        assert event.payload["failure_reason"] == "permission_denied"

    def test_failed_event_conflict(self):
        """衝突による失敗"""
        # Arrange
        payload = {
            "operation_id": "op-006",
            "operation_type": "merge",
            "failure_reason": "conflict",
            "error_message": "Merge conflict in file.py",
            "conflict_id": "conflict-001",
        }

        # Act
        event = OperationFailedEvent(actor="beekeeper", payload=payload)

        # Assert
        assert event.payload["failure_reason"] == "conflict"
        assert event.payload["conflict_id"] == "conflict-001"

    def test_failed_event_cancelled(self):
        """キャンセルによる失敗"""
        # Arrange
        payload = {
            "operation_id": "op-007",
            "operation_type": "batch_process",
            "failure_reason": "cancelled",
            "error_message": "Operation cancelled by user",
            "cancelled_by": "user",
        }

        # Act
        event = OperationFailedEvent(actor="user", payload=payload)

        # Assert
        assert event.payload["failure_reason"] == "cancelled"

    def test_failed_event_unknown(self):
        """不明なエラー"""
        # Arrange
        payload = {
            "operation_id": "op-008",
            "operation_type": "unknown_op",
            "failure_reason": "unknown",
            "error_message": "Unexpected error occurred",
        }

        # Act
        event = OperationFailedEvent(actor="system", payload=payload)

        # Assert
        assert event.payload["failure_reason"] == "unknown"


class TestFailureReasonEnum:
    """FailureReason Enum のテスト"""

    def test_failure_reason_enum_exists(self):
        """FailureReason Enum が存在する"""
        # Arrange & Act
        from hiveforge.core.events import FailureReason

        # Assert
        assert hasattr(FailureReason, "TIMEOUT")
        assert hasattr(FailureReason, "TOOL_ERROR")
        assert hasattr(FailureReason, "CONTEXT_MISSING")
        assert hasattr(FailureReason, "PERMISSION_DENIED")
        assert hasattr(FailureReason, "CONFLICT")
        assert hasattr(FailureReason, "CANCELLED")
        assert hasattr(FailureReason, "UNKNOWN")

    def test_failure_reason_values(self):
        """FailureReason の値が正しい"""
        # Arrange & Act
        from hiveforge.core.events import FailureReason

        # Assert
        assert FailureReason.TIMEOUT.value == "timeout"
        assert FailureReason.TOOL_ERROR.value == "tool_error"
        assert FailureReason.CONTEXT_MISSING.value == "context_missing"
        assert FailureReason.PERMISSION_DENIED.value == "permission_denied"
        assert FailureReason.CONFLICT.value == "conflict"
        assert FailureReason.CANCELLED.value == "cancelled"
        assert FailureReason.UNKNOWN.value == "unknown"


class TestFailureTimeoutEventTypeMap:
    """EVENT_TYPE_MAP に Failure/Timeout イベントが登録されているかテスト"""

    def test_operation_timeout_in_event_type_map(self):
        """OPERATION_TIMEOUTがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.OPERATION_TIMEOUT in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.OPERATION_TIMEOUT] == OperationTimeoutEvent

    def test_operation_failed_in_event_type_map(self):
        """OPERATION_FAILEDがEVENT_TYPE_MAPに登録されている"""
        # Assert
        assert EventType.OPERATION_FAILED in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[EventType.OPERATION_FAILED] == OperationFailedEvent


class TestFailureTimeoutParseEvent:
    """parse_event で Failure/Timeout イベントが正しくパースされるかテスト"""

    def test_parse_operation_timeout_event(self):
        """OPERATION_TIMEOUTイベントをパースできる"""
        # Arrange
        data = {
            "type": "operation.timeout",
            "actor": "worker-bee-001",
            "payload": {
                "operation_id": "op-001",
                "timeout_seconds": 30,
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, OperationTimeoutEvent)
        assert event.type == EventType.OPERATION_TIMEOUT

    def test_parse_operation_failed_event(self):
        """OPERATION_FAILEDイベントをパースできる"""
        # Arrange
        data = {
            "type": "operation.failed",
            "actor": "worker-bee-001",
            "payload": {
                "operation_id": "op-001",
                "failure_reason": "tool_error",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, OperationFailedEvent)
        assert event.type == EventType.OPERATION_FAILED
