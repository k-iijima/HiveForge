"""PipelineExecutionMixin の未カバーパステスト

pipeline_execution.py (76% → ~100%) の以下を検証:
- ApprovalRequiredError キャッチ → approval_required 返却
- PipelineError キャッチ → RunFailedEvent 記録 + error 返却
- 汎用 Exception キャッチ → RunFailedEvent 記録 + error 返却
- failed_count > 0 → RunFailedEvent 記録 + partial 返却
- tasks_raw が空リスト → デフォルトタスク生成
- resume_with_approval: 不明request_id / 拒否 / 承認再実行
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from colonyforge.core.ar.storage import AkashicRecord
from colonyforge.core.events import RunFailedEvent
from colonyforge.core.models.action_class import TrustLevel
from colonyforge.queen_bee.pipeline_execution import PipelineExecutionMixin

# ---------------------------------------------------------------------------
# テスト用の具象クラス（Mixin を使うために必要な属性をすべて満たす）
# ---------------------------------------------------------------------------


class _ConcreteQueen(PipelineExecutionMixin):
    """テスト専用: PipelineExecutionMixin が TYPE_CHECKING で要求する属性を定義"""

    def __init__(self, ar: AkashicRecord, colony_id: str = "col-test") -> None:
        self.ar = ar
        self.colony_id = colony_id
        self.trust_level = TrustLevel.AUTO_NOTIFY
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._plan_tasks_mock = AsyncMock(return_value=[])
        self._execute_task_mock = AsyncMock(return_value={"status": "completed", "result": "ok"})

    async def _plan_tasks(self, goal: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._plan_tasks_mock(goal, context)

    async def _execute_task(
        self,
        task_id: str,
        run_id: str,
        goal: str,
        context: dict[str, Any],
        worker: Any | None = None,
    ) -> dict[str, Any]:
        return await self._execute_task_mock(task_id, run_id, goal, context)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ar(tmp_path):
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def queen(ar):
    return _ConcreteQueen(ar=ar)


# ---------------------------------------------------------------------------
# _execute_with_pipeline テスト
# ---------------------------------------------------------------------------


class TestExecuteWithPipeline:
    """_execute_with_pipeline のブランチカバレッジテスト"""

    @pytest.mark.asyncio
    async def test_empty_tasks_raw_creates_default_task(self, queen: _ConcreteQueen):
        """tasks_rawが空リストの場合、ゴールをそのまま1タスクとして実行する

        タスク分解が0件を返した場合でもフォールバックとして
        元のゴールを単一タスクに変換して実行を継続する。
        """
        # Arrange: _plan_tasks が空リストを返す
        queen._plan_tasks_mock.return_value = []

        # Pipeline.run をモックして completed を返す
        mock_result = MagicMock()
        mock_result.failed_count = 0
        mock_result.completed_count = 1
        mock_result.total_tasks = 1
        mock_result.task_results = [{"task_id": "t1", "status": "completed"}]

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(return_value=mock_result)

            # Act
            result = await queen._execute_with_pipeline(
                run_id="run-1", goal="テスト目標", context={}
            )

        # Assert: completed ステータスが返る
        assert result["status"] == "completed"
        assert result["tasks_completed"] == 1

    @pytest.mark.asyncio
    async def test_partial_failure_records_run_failed_event(self, queen: _ConcreteQueen):
        """一部のタスクが失敗した場合、RunFailedEvent が記録され partial が返る"""
        # Arrange
        queen._plan_tasks_mock.return_value = [
            {"task_id": "t1", "goal": "タスク1"},
            {"task_id": "t2", "goal": "タスク2"},
        ]

        mock_result = MagicMock()
        mock_result.failed_count = 1
        mock_result.completed_count = 1
        mock_result.total_tasks = 2
        mock_result.task_results = []

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(return_value=mock_result)

            # Act
            result = await queen._execute_with_pipeline(
                run_id="run-partial", goal="部分失敗テスト", context={}
            )

        # Assert
        assert result["status"] == "partial"
        assert result["tasks_completed"] == 1
        assert result["tasks_total"] == 2

        # RunFailedEvent が記録されている
        events = list(queen.ar.replay("run-partial"))
        assert any(isinstance(e, RunFailedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_approval_required_saves_pending_and_returns(self, queen: _ConcreteQueen):
        """ApprovalRequiredError 発生時、承認待ち状態を保存して approval_required を返す"""
        from colonyforge.queen_bee.pipeline import ApprovalRequiredError

        # Arrange
        queen._plan_tasks_mock.return_value = [{"task_id": "t1", "goal": "承認必要タスク"}]

        mock_approval_request = MagicMock()
        mock_approval_request.action_class.value = "DANGEROUS"
        mock_approval_request.task_count = 1

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(
                side_effect=ApprovalRequiredError(approval_request=mock_approval_request)
            )

            # Act
            result = await queen._execute_with_pipeline(
                run_id="run-approval", goal="危険な操作", context={"key": "val"}
            )

        # Assert
        assert result["status"] == "approval_required"
        assert result["action_class"] == "DANGEROUS"
        assert "request_id" in result

        # _pending_approvals に保存されている
        request_id = result["request_id"]
        assert request_id in queen._pending_approvals
        assert queen._pending_approvals[request_id]["goal"] == "危険な操作"

    @pytest.mark.asyncio
    async def test_pipeline_error_records_run_failed(self, queen: _ConcreteQueen):
        """PipelineError 発生時、RunFailedEvent が記録されて error が返る"""
        from colonyforge.queen_bee.pipeline import PipelineError

        # Arrange
        queen._plan_tasks_mock.return_value = [{"task_id": "t1", "goal": "失敗タスク"}]

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(side_effect=PipelineError("検証失敗"))

            # Act
            result = await queen._execute_with_pipeline(
                run_id="run-pipe-err", goal="パイプラインエラー", context={}
            )

        # Assert
        assert result["status"] == "error"
        assert "検証失敗" in result["error"]

        events = list(queen.ar.replay("run-pipe-err"))
        assert any(isinstance(e, RunFailedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_generic_exception_records_run_failed(self, queen: _ConcreteQueen):
        """予期しない Exception 時、RunFailedEvent が記録されて error が返る"""
        # Arrange
        queen._plan_tasks_mock.return_value = [{"task_id": "t1", "goal": "例外タスク"}]

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(side_effect=RuntimeError("予期しないエラー"))

            # Act
            result = await queen._execute_with_pipeline(
                run_id="run-exc", goal="例外テスト", context={}
            )

        # Assert
        assert result["status"] == "error"
        assert "予期しないエラー" in result["error"]

        events = list(queen.ar.replay("run-exc"))
        assert any(isinstance(e, RunFailedEvent) for e in events)


# ---------------------------------------------------------------------------
# resume_with_approval テスト
# ---------------------------------------------------------------------------


class TestResumeWithApproval:
    """resume_with_approval のブランチカバレッジテスト"""

    @pytest.mark.asyncio
    async def test_unknown_request_id_returns_error(self, queen: _ConcreteQueen):
        """存在しないrequest_idで再開しようとするとエラーを返す"""
        # Act
        result = await queen.resume_with_approval(request_id="nonexistent", approved=True)

        # Assert
        assert result["status"] == "error"
        assert "Unknown request_id" in result["error"]

    @pytest.mark.asyncio
    async def test_rejected_returns_rejected_status(self, queen: _ConcreteQueen):
        """approved=False の場合、rejected ステータスを返す"""
        # Arrange: 承認待ちを手動で追加
        queen._pending_approvals["req-1"] = {
            "run_id": "run-rej",
            "goal": "拒否テスト",
            "context": {},
            "approval_request": MagicMock(),
        }

        # Act
        result = await queen.resume_with_approval(
            request_id="req-1", approved=False, reason="リスクが高い"
        )

        # Assert
        assert result["status"] == "rejected"
        assert result["run_id"] == "run-rej"
        assert result["reason"] == "リスクが高い"

        # _pending_approvals から削除されている
        assert "req-1" not in queen._pending_approvals

    @pytest.mark.asyncio
    async def test_approved_resumes_pipeline_execution(self, queen: _ConcreteQueen):
        """approved=True の場合、承認付きでパイプラインが再実行される"""
        # Arrange
        queen._pending_approvals["req-2"] = {
            "run_id": "run-approve",
            "goal": "承認テスト",
            "context": {"key": "val"},
            "approval_request": MagicMock(),
        }

        mock_result = MagicMock()
        mock_result.failed_count = 0
        mock_result.completed_count = 1
        mock_result.total_tasks = 1
        mock_result.task_results = []

        with patch("colonyforge.queen_bee.pipeline.ExecutionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run = AsyncMock(return_value=mock_result)

            # Act
            result = await queen.resume_with_approval(
                request_id="req-2", approved=True, reason="承認します"
            )

        # Assert
        assert result["status"] == "completed"
        assert "req-2" not in queen._pending_approvals
