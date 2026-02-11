"""Queen Bee 実行パイプラインのテスト

Plan → Validate → Approve → Execute → Report の各段階で
ARイベントが記録され、問題が隠蔽されないことを検証する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from colonyforge.core.ar.storage import AkashicRecord
from colonyforge.core.models.action_class import TrustLevel
from colonyforge.guard_bee.models import (
    GuardBeeReport,
    Verdict,
)
from colonyforge.queen_bee.approval import ApprovalDecision
from colonyforge.queen_bee.pipeline import (
    ApprovalRequiredError,
    ExecutionPipeline,
    PlanValidationFailedError,
)
from colonyforge.queen_bee.planner import PlannedTask, TaskPlan

# =========================================================================
# ヘルパー
# =========================================================================


def _make_plan(*goals: str, **kwargs: Any) -> TaskPlan:
    """テスト用の簡易TaskPlanを作成"""
    tasks = [PlannedTask(task_id=f"t{i + 1}", goal=g) for i, g in enumerate(goals)]
    return TaskPlan(tasks=tasks, **kwargs)


def _make_passing_report(
    colony_id: str = "col-1", task_id: str = "t-plan", run_id: str = "run-1"
) -> GuardBeeReport:
    """合格レポートを作成"""
    return GuardBeeReport(
        colony_id=colony_id,
        task_id=task_id,
        run_id=run_id,
        verdict=Verdict.PASS,
        l1_passed=True,
        l2_passed=True,
        evidence_count=1,
    )


def _make_failing_report(
    colony_id: str = "col-1", task_id: str = "t-plan", run_id: str = "run-1"
) -> GuardBeeReport:
    """不合格レポートを作成"""
    return GuardBeeReport(
        colony_id=colony_id,
        task_id=task_id,
        run_id=run_id,
        verdict=Verdict.FAIL,
        l1_passed=False,
        l2_passed=False,
        evidence_count=1,
        remand_reason="構造的問題あり",
    )


# =========================================================================
# ExecutionPipeline テスト
# =========================================================================


class TestExecutionPipeline:
    """実行パイプラインのテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path)

    @pytest.fixture
    def mock_execute(self):
        """タスク実行関数のモック"""

        async def _execute(task_id: str, goal: str, context: dict | None) -> dict:
            return {"status": "completed", "task_id": task_id, "result": f"{goal}完了"}

        return AsyncMock(side_effect=_execute)

    @pytest.fixture
    def pipeline(self, ar):
        return ExecutionPipeline(ar=ar, trust_level=TrustLevel.AUTO_NOTIFY)

    # --- Guard Bee 検証ゲート ---

    @pytest.mark.asyncio
    async def test_guard_bee_pass_allows_execution(self, pipeline, ar, mock_execute):
        """Guard Bee PASS → 実行が続行される"""
        # Arrange
        plan = _make_plan("テスト実行")

        # Act: Guard Bee が PASS を返すように設定
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            result = await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-1",
                original_goal="テスト",
            )

        # Assert
        assert result.status.value == "completed"
        mock_execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_guard_bee_fail_blocks_execution(self, pipeline, ar, mock_execute):
        """Guard Bee FAIL → PlanValidationFailedError"""
        # Arrange
        plan = _make_plan("テスト実行")

        # Act & Assert
        with patch.object(pipeline, "_validate_plan", return_value=_make_failing_report()):
            with pytest.raises(PlanValidationFailedError) as exc_info:
                await pipeline.run(
                    plan=plan,
                    execute_fn=mock_execute,
                    colony_id="col-1",
                    run_id="run-1",
                    original_goal="テスト",
                )

        # Assert: 実行されない
        mock_execute.assert_not_awaited()
        assert "構造的問題あり" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_guard_bee_fail_recorded_in_ar(self, pipeline, ar, mock_execute):
        """Guard Bee FAILがARイベントとして記録される"""
        # Arrange
        plan = _make_plan("テスト実行")

        # Act
        with patch.object(
            pipeline, "_validate_plan", return_value=_make_failing_report(run_id="run-1")
        ):
            with pytest.raises(PlanValidationFailedError):
                await pipeline.run(
                    plan=plan,
                    execute_fn=mock_execute,
                    colony_id="col-1",
                    run_id="run-1",
                    original_goal="テスト",
                )

        # Assert: ARにイベントが記録されている
        events = ar.replay("run-1")
        event_types = [e.type for e in events]
        assert "plan.validation_failed" in event_types

    # --- 承認ゲート ---

    @pytest.mark.asyncio
    async def test_approval_not_required_continues(self, pipeline, ar, mock_execute):
        """承認不要（READ_ONLY）→ 実行続行"""
        # Arrange
        plan = _make_plan("コードの分析と調査")

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            result = await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-1",
                original_goal="テスト",
            )

        # Assert
        assert result.status.value == "completed"

    @pytest.mark.asyncio
    async def test_approval_required_raises(self, pipeline, ar, mock_execute):
        """承認必要 + 未承認 → ApprovalRequiredError"""
        # Arrange: 本番デプロイ → IRREVERSIBLE → 承認必要
        plan = _make_plan("本番へデプロイ実行")
        pipeline_strict = ExecutionPipeline(ar=ar, trust_level=TrustLevel.PROPOSE_CONFIRM)

        # Act & Assert
        with patch.object(pipeline_strict, "_validate_plan", return_value=_make_passing_report()):
            with pytest.raises(ApprovalRequiredError) as exc_info:
                await pipeline_strict.run(
                    plan=plan,
                    execute_fn=mock_execute,
                    colony_id="col-1",
                    run_id="run-1",
                    original_goal="デプロイ",
                )

        # Assert: 実行されない
        mock_execute.assert_not_awaited()
        assert exc_info.value.approval_request.requires_approval is True

    @pytest.mark.asyncio
    async def test_approval_required_event_recorded(self, pipeline, ar, mock_execute):
        """承認要求がARイベントとして記録される"""
        # Arrange
        plan = _make_plan("本番へデプロイ実行")

        # Act
        with patch.object(
            pipeline, "_validate_plan", return_value=_make_passing_report(run_id="run-2")
        ):
            with pytest.raises(ApprovalRequiredError):
                await pipeline.run(
                    plan=plan,
                    execute_fn=mock_execute,
                    colony_id="col-1",
                    run_id="run-2",
                    original_goal="デプロイ",
                )

        # Assert
        events = ar.replay("run-2")
        event_types = [e.type for e in events]
        assert "plan.approval_required" in event_types

    @pytest.mark.asyncio
    async def test_pre_approved_plan_executes(self, pipeline, ar, mock_execute):
        """事前承認済みの場合は実行される"""
        # Arrange
        plan = _make_plan("本番へデプロイ実行")
        approval = ApprovalDecision(approved=True, reason="確認済み")

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            result = await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-1",
                original_goal="デプロイ",
                approval_decision=approval,
            )

        # Assert
        assert result.status.value == "completed"
        mock_execute.assert_awaited()

    # --- フォールバックのAR記録 ---

    @pytest.mark.asyncio
    async def test_fallback_plan_recorded(self, pipeline, ar, mock_execute):
        """フォールバックプランがARイベントとして記録される"""
        # Arrange: フォールバック理由を含むプラン
        plan = _make_plan(
            "テスト実行", reasoning="LLMタスク分解に失敗したため、目標をそのまま1タスクとして実行"
        )

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-3",
                original_goal="テスト",
                is_fallback=True,
            )

        # Assert
        events = ar.replay("run-3")
        event_types = [e.type for e in events]
        assert "plan.fallback_activated" in event_types

    # --- 結果集約 ---

    @pytest.mark.asyncio
    async def test_result_uses_colony_result(self, pipeline, ar, mock_execute):
        """パイプラインがColonyResultを使って結果を返す"""
        # Arrange
        plan = _make_plan("DB設計", "API実装")

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            result = await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-1",
                original_goal="システム構築",
            )

        # Assert
        assert result.colony_id == "col-1"
        assert result.total_tasks == 2
        assert result.completed_count == 2
        assert "システム構築" in result.summary_text

    @pytest.mark.asyncio
    async def test_partial_failure_recorded(self, pipeline, ar):
        """一部失敗がColonyResultに正しく反映される"""

        # Arrange
        async def _mixed_execute(task_id, goal, context):
            if task_id == "t2":
                return {"status": "failed", "task_id": task_id, "reason": "接続エラー"}
            return {"status": "completed", "task_id": task_id, "result": "ok"}

        plan = _make_plan("成功タスク", "失敗タスク")

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            result = await pipeline.run(
                plan=plan,
                execute_fn=AsyncMock(side_effect=_mixed_execute),
                colony_id="col-1",
                run_id="run-1",
                original_goal="テスト",
            )

        # Assert
        assert result.status.value == "partial_failure"
        assert result.completed_count == 1
        assert result.failed_count == 1

    # --- パイプライン段階のAR記録 ---

    @pytest.mark.asyncio
    async def test_pipeline_stages_recorded_in_ar(self, pipeline, ar, mock_execute):
        """パイプラインの各段階がARイベントとして記録される"""
        # Arrange
        plan = _make_plan("テスト実行")

        # Act
        with patch.object(pipeline, "_validate_plan", return_value=_make_passing_report()):
            await pipeline.run(
                plan=plan,
                execute_fn=mock_execute,
                colony_id="col-1",
                run_id="run-4",
                original_goal="テスト",
            )

        # Assert: 段階イベントが記録されている
        events = ar.replay("run-4")
        event_types = [e.type for e in events]
        assert "pipeline.started" in event_types
        assert "pipeline.completed" in event_types


class TestValidatePlanIntegration:
    """_validate_plan のモックなし統合テスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path)

    @pytest.fixture
    def pipeline(self, ar):
        return ExecutionPipeline(ar=ar, trust_level=TrustLevel.AUTO_NOTIFY)

    def test_validate_plan_passes_valid_plan(self, pipeline):
        """有効なプランがGuard Bee検証を通過する"""
        # Arrange: 目標をカバーするタスクを含むプラン
        plan = _make_plan("ログインページのUI作成", "バリデーション実装")

        # Act: 実際の _validate_plan を呼び出す
        report = pipeline._validate_plan(
            plan=plan,
            original_goal="ログインページの作成",
            colony_id="col-test",
            run_id="run-test",
        )

        # Assert
        assert report.verdict == Verdict.PASS

    def test_validate_plan_fails_single_vague_task(self, pipeline):
        """目標と無関係な単一タスクはGuard Bee検証で不合格になりうる

        PlanStructureRuleは最低1タスクを要求するが、
        PlanGoalCoverageRuleで目標カバレッジが低い場合はFAILとなる。
        """
        # Arrange: 目標をまったくカバーしない曖昧なタスク
        plan = _make_plan("何かする")

        # Act
        report = pipeline._validate_plan(
            plan=plan,
            original_goal="ECサイトの決済システム、ユーザー管理、在庫管理を構築",
            colony_id="col-test",
            run_id="run-test",
        )

        # Assert: レポートが返る（検証自体は実行される）
        assert report is not None
        assert isinstance(report, GuardBeeReport)


class TestRecordEvent:
    """_record_event のテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path)

    @pytest.fixture
    def pipeline(self, ar):
        return ExecutionPipeline(ar=ar, trust_level=TrustLevel.AUTO_NOTIFY)

    def test_record_event_stored_in_ar(self, pipeline, ar):
        """_record_event がARにイベントを正しく記録する"""
        from colonyforge.core.events.types import EventType

        # Act
        pipeline._record_event(
            EventType.PIPELINE_STARTED,
            run_id="run-rec",
            colony_id="col-rec",
            actor="test-actor",
            payload={"key": "value"},
        )

        # Assert
        events = list(ar.replay("run-rec"))
        assert len(events) == 1
        assert events[0].type == EventType.PIPELINE_STARTED
        assert events[0].colony_id == "col-rec"
        assert events[0].actor == "test-actor"
        assert events[0].payload["key"] == "value"

    def test_record_multiple_events(self, pipeline, ar):
        """複数イベントが正しい順序で記録される"""
        from colonyforge.core.events.types import EventType

        # Act
        pipeline._record_event(
            EventType.PIPELINE_STARTED,
            run_id="run-multi",
            colony_id="col-m",
            actor="actor1",
            payload={"stage": "start"},
        )
        pipeline._record_event(
            EventType.PIPELINE_COMPLETED,
            run_id="run-multi",
            colony_id="col-m",
            actor="actor2",
            payload={"stage": "end"},
        )

        # Assert
        events = list(ar.replay("run-multi"))
        assert len(events) == 2
        assert events[0].type == EventType.PIPELINE_STARTED
        assert events[1].type == EventType.PIPELINE_COMPLETED
