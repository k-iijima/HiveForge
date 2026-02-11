"""Waggle Dance（ワグルダンス / 構造化I/O検証）のテスト

エージェント間の通信メッセージをPydanticスキーマで検証し、
スキーマ違反を自動検出・ARに記録する。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from colonyforge.waggle_dance.models import (
    MessageDirection,
    OpinionRequest,
    OpinionResponse,
    TaskAssignment,
    TaskResult,
    WaggleDanceResult,
)
from colonyforge.waggle_dance.models import (
    ValidationError as WDValidationError,
)

# ==================== M3-7-a: 通信メッセージのPydanticスキーマ定義 ====================


class TestOpinionRequest:
    """Beekeeper → Queen Bee: OpinionRequest"""

    def test_create_valid_request(self):
        """有効なOpinionRequestを作成"""
        req = OpinionRequest(
            colony_id="colony-001",
            question="このアーキテクチャで問題ないですか？",
            context={"files_changed": ["events.py"]},
        )

        assert req.colony_id == "colony-001"
        assert req.question != ""

    def test_empty_question_rejected(self):
        """空の質問は拒否される"""
        with pytest.raises(ValidationError):
            OpinionRequest(
                colony_id="colony-001",
                question="",
                context={},
            )

    def test_missing_colony_id_rejected(self):
        """colony_id欠落は拒否"""
        with pytest.raises(ValidationError):
            OpinionRequest(
                colony_id="",
                question="質問です",
                context={},
            )


class TestOpinionResponse:
    """Queen Bee → Beekeeper: OpinionResponse"""

    def test_create_valid_response(self):
        """有効なOpinionResponseを作成"""
        resp = OpinionResponse(
            colony_id="colony-001",
            answer="問題ないと考えます",
            confidence=0.85,
        )

        assert resp.confidence == 0.85

    def test_confidence_range(self):
        """confidenceは0.0〜1.0"""
        with pytest.raises(ValidationError):
            OpinionResponse(
                colony_id="colony-001",
                answer="回答",
                confidence=1.5,
            )

    def test_empty_answer_rejected(self):
        """空の回答は拒否"""
        with pytest.raises(ValidationError):
            OpinionResponse(
                colony_id="colony-001",
                answer="",
                confidence=0.5,
            )


class TestTaskAssignment:
    """Queen Bee → Worker Bee: TaskAssignment"""

    def test_create_valid_assignment(self):
        """有効なTaskAssignmentを作成"""
        assignment = TaskAssignment(
            task_id="task-001",
            colony_id="colony-001",
            instructions="events.pyにHIVE_UPDATEDイベントを追加してください",
            tools_allowed=["read_file", "write_file"],
        )

        assert assignment.task_id == "task-001"
        assert len(assignment.tools_allowed) == 2

    def test_empty_instructions_rejected(self):
        """指示なしは拒否"""
        with pytest.raises(ValidationError):
            TaskAssignment(
                task_id="task-001",
                colony_id="colony-001",
                instructions="",
                tools_allowed=[],
            )


class TestTaskResult:
    """Worker Bee → Queen Bee: TaskResult"""

    def test_create_valid_result(self):
        """有効なTaskResultを作成"""
        result = TaskResult(
            task_id="task-001",
            colony_id="colony-001",
            success=True,
            artifacts=["src/colonyforge/core/events.py"],
            evidence={"tests_passed": 10, "tests_total": 10},
        )

        assert result.success is True
        assert len(result.artifacts) == 1

    def test_failed_result(self):
        """失敗結果"""
        result = TaskResult(
            task_id="task-001",
            colony_id="colony-001",
            success=False,
            error_message="コンパイルエラー",
        )

        assert result.success is False
        assert result.error_message is not None


class TestMessageDirection:
    """メッセージ方向のテスト"""

    def test_all_directions(self):
        """全方向が定義されている"""
        assert MessageDirection.BEEKEEPER_TO_QUEEN is not None
        assert MessageDirection.QUEEN_TO_BEEKEEPER is not None
        assert MessageDirection.QUEEN_TO_WORKER is not None
        assert MessageDirection.WORKER_TO_QUEEN is not None
        assert MessageDirection.GUARD_RESULT is not None


# ==================== M3-7-b: 検証ミドルウェア ====================


from colonyforge.waggle_dance.validator import WaggleDanceValidator  # noqa: E402


class TestWaggleDanceValidator:
    """検証ミドルウェアのテスト"""

    def test_validate_valid_opinion_request(self):
        """有効なOpinionRequestの検証が通る"""
        validator = WaggleDanceValidator()

        result = validator.validate(
            direction=MessageDirection.BEEKEEPER_TO_QUEEN,
            data={
                "colony_id": "colony-001",
                "question": "質問です",
                "context": {},
            },
        )

        assert result.valid is True
        assert result.errors == []

    def test_validate_invalid_opinion_request(self):
        """不正なOpinionRequestはバリデーションエラー"""
        validator = WaggleDanceValidator()

        result = validator.validate(
            direction=MessageDirection.BEEKEEPER_TO_QUEEN,
            data={
                "colony_id": "",
                "question": "",
                "context": {},
            },
        )

        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_task_assignment(self):
        """TaskAssignmentの検証"""
        validator = WaggleDanceValidator()

        result = validator.validate(
            direction=MessageDirection.QUEEN_TO_WORKER,
            data={
                "task_id": "task-001",
                "colony_id": "colony-001",
                "instructions": "やることを書いてください",
                "tools_allowed": ["read_file"],
            },
        )

        assert result.valid is True

    def test_validate_task_result(self):
        """TaskResultの検証"""
        validator = WaggleDanceValidator()

        result = validator.validate(
            direction=MessageDirection.WORKER_TO_QUEEN,
            data={
                "task_id": "task-001",
                "colony_id": "colony-001",
                "success": True,
                "artifacts": ["file.py"],
            },
        )

        assert result.valid is True

    def test_validate_returns_error_details(self):
        """エラー詳細が返される"""
        validator = WaggleDanceValidator()

        result = validator.validate(
            direction=MessageDirection.QUEEN_TO_BEEKEEPER,
            data={
                "colony_id": "colony-001",
                "answer": "",
                "confidence": 2.0,  # 範囲外
            },
        )

        assert result.valid is False
        # エラーにフィールドと理由が含まれる
        for err in result.errors:
            assert "field" in err or "loc" in err or "msg" in err


class TestWaggleDanceResult:
    """検証結果モデルのテスト"""

    def test_valid_result(self):
        """合格結果"""
        result = WaggleDanceResult(
            valid=True, errors=[], direction=MessageDirection.BEEKEEPER_TO_QUEEN
        )
        assert result.valid is True

    def test_invalid_result(self):
        """不合格結果"""
        result = WaggleDanceResult(
            valid=False,
            errors=[WDValidationError(field="question", message="空文字は不可")],
            direction=MessageDirection.BEEKEEPER_TO_QUEEN,
        )
        assert len(result.errors) == 1


# ==================== M3-7-c: 検証エラーのARイベント記録 ====================


from colonyforge.core.events import EventType  # noqa: E402
from colonyforge.waggle_dance.recorder import WaggleDanceRecorder  # noqa: E402


class TestWaggleDanceRecorder:
    """ARイベント記録のテスト"""

    def test_record_validation_success(self):
        """検証成功のARイベントを生成"""
        recorder = WaggleDanceRecorder()

        result = WaggleDanceResult(
            valid=True, errors=[], direction=MessageDirection.BEEKEEPER_TO_QUEEN
        )

        event = recorder.create_event(result, colony_id="colony-001")

        assert event.type == EventType.WAGGLE_DANCE_VALIDATED
        assert event.payload["valid"] is True
        assert event.payload["direction"] == "beekeeper_to_queen"

    def test_record_validation_failure(self):
        """検証失敗のARイベントを生成"""
        recorder = WaggleDanceRecorder()

        result = WaggleDanceResult(
            valid=False,
            errors=[WDValidationError(field="question", message="空文字は不可")],
            direction=MessageDirection.BEEKEEPER_TO_QUEEN,
        )

        event = recorder.create_event(result, colony_id="colony-001")

        assert event.type == EventType.WAGGLE_DANCE_VIOLATION
        assert event.payload["valid"] is False
        assert len(event.payload["errors"]) == 1
        assert event.payload["colony_id"] == "colony-001"


class TestWaggleDanceValidatorEdgeCases:
    """バリデータのエッジケーステスト"""

    def test_unsupported_direction_returns_invalid(self):
        """未対応の MessageDirection（スキーママップに未登録）は invalid を返す

        GUARD_RESULT は _DIRECTION_SCHEMA_MAP に登録されていないため、
        防御的にバリデーション失敗を返す。
        """
        # Arrange
        validator = WaggleDanceValidator()

        # Act
        result = validator.validate(
            direction=MessageDirection.GUARD_RESULT,
            data={"some": "data"},
        )

        # Assert
        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].field == "direction"
        assert "未対応" in result.errors[0].message
        assert result.direction == MessageDirection.GUARD_RESULT
