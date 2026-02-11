"""ExecutionPipeline → QueenBeeMCPServer 統合テスト

QueenBeeMCPServer.handle_execute_goal() が ExecutionPipeline 経由で
Guard Bee検証 + 承認ゲート を通過して実行するフローを検証する。

M2-2: Beekeeper → Queen Bee → Worker Bee 統合パスの確立
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from colonyforge.core.ar.storage import AkashicRecord
from colonyforge.core.events.types import EventType
from colonyforge.core.models.action_class import TrustLevel
from colonyforge.queen_bee.server import QueenBeeMCPServer


@pytest.fixture(autouse=True)
def _mock_plan_tasks():
    """_plan_tasksをモックし、LLM依存を排除する"""
    with patch(
        "colonyforge.queen_bee.server.QueenBeeMCPServer._plan_tasks",
        new_callable=AsyncMock,
        side_effect=lambda goal, context=None: [
            {"task_id": "task-001", "goal": goal, "depends_on": []}
        ],
    ):
        yield


@pytest.fixture
def ar(tmp_path):
    """テスト用AkashicRecord"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def queen_with_pipeline(ar):
    """Pipeline有効のQueen Bee"""
    queen = QueenBeeMCPServer(
        colony_id="colony-pipeline-test",
        ar=ar,
        use_pipeline=True,
        trust_level=TrustLevel.FULL_DELEGATION,  # 承認不要
    )
    return queen


@pytest.fixture
def queen_with_approval(ar):
    """承認必要なPipeline有効のQueen Bee"""
    queen = QueenBeeMCPServer(
        colony_id="colony-approval-test",
        ar=ar,
        use_pipeline=True,
        trust_level=TrustLevel.REPORT_ONLY,  # 常に承認必要
    )
    return queen


@pytest.fixture
def queen_no_pipeline(ar):
    """Pipeline無効のQueen Bee（後方互換）"""
    queen = QueenBeeMCPServer(
        colony_id="colony-no-pipeline",
        ar=ar,
        use_pipeline=False,
    )
    return queen


# =========================================================================
# Pipeline有効時の基本動作
# =========================================================================


class TestPipelineIntegration:
    """ExecutionPipeline経由のタスク実行"""

    @pytest.mark.asyncio
    async def test_pipeline_executes_through_guard_bee(self, queen_with_pipeline, ar):
        """Pipeline有効時にGuard Bee検証を通過してタスク実行される

        FULL_DELEGATION trust_level のため承認は不要。
        Guard Bee検証 → 実行 → 結果記録の流れを確認。
        """
        # Arrange
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "完了", "llm_output": "OK"},
        ):
            run_id = "pipeline-test-001"

            # Act
            result = await queen_with_pipeline.handle_execute_goal(
                {"run_id": run_id, "goal": "テストタスク実行"}
            )

        # Assert: 成功
        assert result["status"] == "completed"
        assert result["run_id"] == run_id

        # Assert: Pipeline関連イベントが記録されている
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        assert EventType.RUN_STARTED in event_types
        assert EventType.PIPELINE_STARTED in event_types
        assert EventType.PIPELINE_COMPLETED in event_types
        assert EventType.RUN_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_pipeline_records_run_started_before_pipeline(self, queen_with_pipeline, ar):
        """RunStartedイベントがPIPELINE_STARTEDより前に記録される"""
        # Arrange
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            run_id = "order-test-001"

            # Act
            await queen_with_pipeline.handle_execute_goal({"run_id": run_id, "goal": "順序テスト"})

        # Assert: RunStarted が PIPELINE_STARTED より前
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        run_started_idx = event_types.index(EventType.RUN_STARTED)
        pipeline_started_idx = event_types.index(EventType.PIPELINE_STARTED)
        assert run_started_idx < pipeline_started_idx

    @pytest.mark.asyncio
    async def test_pipeline_result_includes_colony_result(self, queen_with_pipeline, ar):
        """Pipeline経由の結果にColonyResult情報が含まれる"""
        # Arrange
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "成果", "llm_output": "LLM出力"},
        ):
            # Act
            result = await queen_with_pipeline.handle_execute_goal(
                {"run_id": "result-test-001", "goal": "結果テスト"}
            )

        # Assert
        assert result["status"] == "completed"
        assert result["tasks_total"] >= 1
        assert result["tasks_completed"] >= 1


# =========================================================================
# 承認ゲート統合
# =========================================================================


class TestPipelineApprovalGate:
    """承認ゲートの統合テスト"""

    @pytest.mark.asyncio
    async def test_approval_required_returns_pending_status(self, queen_with_approval, ar):
        """承認が必要な場合、status=approval_required を返す

        REPORT_ONLY trust_level の場合、全てのタスクで承認が必要。
        """
        # Act
        result = await queen_with_approval.handle_execute_goal(
            {"run_id": "approval-test-001", "goal": "テスト実行"}
        )

        # Assert: 承認待ちステータス
        assert result["status"] == "approval_required"
        assert "request_id" in result

    @pytest.mark.asyncio
    async def test_approval_required_records_event(self, queen_with_approval, ar):
        """承認待ち時に PLAN_APPROVAL_REQUIRED イベントが記録される"""
        # Act
        await queen_with_approval.handle_execute_goal(
            {"run_id": "approval-event-001", "goal": "承認必要タスク"}
        )

        # Assert
        events = list(ar.replay("approval-event-001"))
        event_types = [e.type for e in events]
        assert EventType.PLAN_APPROVAL_REQUIRED in event_types

    @pytest.mark.asyncio
    async def test_resume_with_approval_executes(self, queen_with_approval, ar):
        """承認後に resume_with_approval() でタスクが実行される"""
        # Arrange: 最初の実行で承認待ちになる
        result = await queen_with_approval.handle_execute_goal(
            {"run_id": "resume-test-001", "goal": "承認後実行タスク"}
        )
        assert result["status"] == "approval_required"
        request_id = result["request_id"]

        # Act: 承認付きで再実行
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            resumed = await queen_with_approval.resume_with_approval(
                request_id=request_id,
                approved=True,
                reason="承認します",
            )

        # Assert: 実行完了
        assert resumed["status"] == "completed"

    @pytest.mark.asyncio
    async def test_resume_with_rejection_cancels(self, queen_with_approval, ar):
        """拒否時に resume_with_approval(approved=False) でキャンセルされる"""
        # Arrange
        result = await queen_with_approval.handle_execute_goal(
            {"run_id": "reject-test-001", "goal": "拒否テスト"}
        )
        assert result["status"] == "approval_required"
        request_id = result["request_id"]

        # Act: 拒否
        rejected = await queen_with_approval.resume_with_approval(
            request_id=request_id,
            approved=False,
            reason="リスクが高すぎる",
        )

        # Assert: キャンセル
        assert rejected["status"] == "rejected"


# =========================================================================
# 後方互換性
# =========================================================================


class TestBackwardCompatibility:
    """Pipeline無効時の後方互換性"""

    @pytest.mark.asyncio
    async def test_no_pipeline_works_as_before(self, queen_no_pipeline, ar):
        """use_pipeline=False 時は従来通り直接実行される"""
        # Arrange
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            run_id = "compat-test-001"

            # Act
            result = await queen_no_pipeline.handle_execute_goal(
                {"run_id": run_id, "goal": "後方互換テスト"}
            )

        # Assert: 従来通りの結果
        assert result["status"] == "completed"
        assert result["run_id"] == run_id

        # Assert: Pipeline イベントは記録されない
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]
        assert EventType.PIPELINE_STARTED not in event_types
        assert EventType.PIPELINE_COMPLETED not in event_types

        # Assert: 従来のイベントは記録される
        assert EventType.RUN_STARTED in event_types
        assert EventType.TASK_CREATED in event_types
        assert EventType.RUN_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_no_pipeline_default_value(self, ar):
        """use_pipeline のデフォルト値は False"""
        queen = QueenBeeMCPServer(colony_id="default-test", ar=ar)
        assert queen.use_pipeline is False


# =========================================================================
# Pipeline失敗ハンドリング
# =========================================================================


class TestPipelineFailureHandling:
    """Pipeline実行中のエラーハンドリング"""

    @pytest.mark.asyncio
    async def test_worker_failure_through_pipeline(self, queen_with_pipeline, ar):
        """Pipeline経由でWorkerが失敗した場合にRunFailedが記録される"""
        # Arrange
        with patch(
            "colonyforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "failed", "reason": "コンパイルエラー"},
        ):
            run_id = "failure-test-001"

            # Act
            result = await queen_with_pipeline.handle_execute_goal(
                {"run_id": run_id, "goal": "失敗するタスク"}
            )

        # Assert
        assert result["status"] in ("partial", "error")

        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]
        assert EventType.RUN_STARTED in event_types
        # RunFailed or RunCompleted with partial
        assert EventType.RUN_FAILED in event_types or EventType.RUN_COMPLETED in event_types
