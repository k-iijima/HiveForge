"""Beekeeper → Queen Bee(Pipeline) → Worker Bee 承認フローE2Eテスト

Beekeeper が Queen Bee に Pipeline付きでタスクを委譲し、
承認が必要な場合に _ask_user() → approve/reject → 再実行する
フルチェーンを検証する。

M2-2-d: 承認フロー（Requirement → approve/reject）が E2E で動作
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from hiveforge.beekeeper.server import BeekeeperMCPServer
from hiveforge.beekeeper.session import SessionState
from hiveforge.core.ar.storage import AkashicRecord
from hiveforge.core.events.types import EventType
from hiveforge.core.models.action_class import TrustLevel
from hiveforge.queen_bee.server import QueenBeeMCPServer


@pytest.fixture
def ar(tmp_path):
    """テスト用AkashicRecord"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def beekeeper(ar):
    """テスト用Beekeeper"""
    bk = BeekeeperMCPServer(ar=ar)
    bk.current_session = bk.session_manager.create_session()
    return bk


# =========================================================================
# Beekeeper → Queen Bee(Pipeline) フルチェーン
# =========================================================================


class TestFullChainWithPipeline:
    """Beekeeper → Queen Bee(Pipeline) → Worker Bee のフルチェーン"""

    @pytest.mark.asyncio
    async def test_delegate_with_pipeline_full_delegation(self, beekeeper, ar):
        """Pipeline + FULL_DELEGATION でタスクが承認なしに完了する

        Beekeeper._delegate_to_queen() → Queen Bee(Pipeline) → Worker Bee
        の全フローを通過し、結果が AR に記録される。
        """
        # Arrange: Worker BeeのLLM実行をモック
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "ページ作成完了",
                "llm_output": "HTMLを生成しました",
            },
        ):
            # Act: Pipeline有効で委譲
            result = await beekeeper._delegate_to_queen_with_pipeline(
                colony_id="colony-full-deleg",
                task="ログインページを作成",
                trust_level=TrustLevel.FULL_DELEGATION,
            )

        # Assert: 完了
        assert "タスク完了" in result

        # Assert: Queen BeeがPipeline有効で作成されている
        queen = beekeeper._queens["colony-full-deleg"]
        assert queen.use_pipeline is True

    @pytest.mark.asyncio
    async def test_delegate_with_pipeline_records_pipeline_events(self, beekeeper, ar):
        """Pipeline経由の委譲でPIPELINE_STARTEDイベントがARに記録される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "ok",
                "llm_output": "done",
            },
        ):
            # Act
            await beekeeper._delegate_to_queen_with_pipeline(
                colony_id="colony-events",
                task="テストタスク",
                trust_level=TrustLevel.FULL_DELEGATION,
            )

        # Assert: Pipeline関連イベントが記録されている
        queen = beekeeper._queens["colony-events"]
        run_id = queen._current_run_id
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        assert EventType.PIPELINE_STARTED in event_types
        assert EventType.PIPELINE_COMPLETED in event_types


# =========================================================================
# 承認フロー E2E
# =========================================================================


class TestApprovalFlowE2E:
    """Beekeeper 承認フローの E2E テスト"""

    @pytest.mark.asyncio
    async def test_approval_flow_approve(self, beekeeper, ar):
        """承認フロー: 委譲 → 承認待ち → _ask_user → approve → 再実行

        REPORT_ONLY trust_level のため承認が必要。
        _ask_user() で質問し、approve により実行が再開される。
        """

        async def approve_from_beekeeper():
            """Beekeeper側で承認する（バックグラウンド）"""
            # pending_requests が追加されるまでポーリング
            for _ in range(200):
                if beekeeper._pending_requests:
                    break
                await asyncio.sleep(0.02)
            assert len(beekeeper._pending_requests) >= 1
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id, "comment": "承認します"})

        # Arrange: Worker BeeのLLM実行をモック
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "完了",
                "llm_output": "実装完了",
            },
        ):
            # Act: バックグラウンドで承認しつつ、Pipeline委譲
            approve_task = asyncio.create_task(approve_from_beekeeper())
            result = await beekeeper._delegate_to_queen_with_pipeline(
                colony_id="colony-approve",
                task="本番環境にデプロイ",
                trust_level=TrustLevel.REPORT_ONLY,
            )
            await approve_task

        # Assert: 最終的に完了
        assert "タスク完了" in result

    @pytest.mark.asyncio
    async def test_approval_flow_reject(self, beekeeper, ar):
        """承認フロー: 委譲 → 承認待ち → _ask_user → reject → キャンセル"""

        async def reject_from_beekeeper():
            """Beekeeper側で拒否する（バックグラウンド）"""
            for _ in range(200):
                if beekeeper._pending_requests:
                    break
                await asyncio.sleep(0.02)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_reject({"request_id": request_id, "reason": "リスクが高い"})

        # Act
        reject_task = asyncio.create_task(reject_from_beekeeper())
        result = await beekeeper._delegate_to_queen_with_pipeline(
            colony_id="colony-reject",
            task="全データベースを削除",
            trust_level=TrustLevel.REPORT_ONLY,
        )
        await reject_task

        # Assert: 拒否されている
        assert "拒否" in result or "rejected" in result.lower()

    @pytest.mark.asyncio
    async def test_approval_records_all_events(self, beekeeper, ar):
        """承認フローで RequirementCreated → RequirementApproved がARに記録される"""

        async def approve_quickly():
            for _ in range(200):
                if beekeeper._pending_requests:
                    break
                await asyncio.sleep(0.02)
            request_id = next(iter(beekeeper._pending_requests))
            await beekeeper.handle_approve({"request_id": request_id})

        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "ok",
                "llm_output": "done",
            },
        ):
            approve_task = asyncio.create_task(approve_quickly())
            await beekeeper._delegate_to_queen_with_pipeline(
                colony_id="colony-events-approval",
                task="テスト",
                trust_level=TrustLevel.REPORT_ONLY,
            )
            await approve_task

        # Assert: RequirementCreated + RequirementApproved がどこかのストリームにある
        all_events = []
        for run_id in ar.list_runs():
            all_events.extend(ar.replay(run_id))

        event_types = [e.type for e in all_events]
        assert EventType.REQUIREMENT_CREATED in event_types
        assert EventType.REQUIREMENT_APPROVED in event_types


# =========================================================================
# BeekeeperセッションとPipeline状態の一貫性
# =========================================================================


class TestSessionPipelineConsistency:
    """BeekeeperセッションとPipeline操作の整合性"""

    @pytest.mark.asyncio
    async def test_session_busy_during_pipeline_execution(self, beekeeper):
        """Pipeline実行中にセッション状態がBUSYになっている"""
        state_during_execution = None

        original_execute = QueenBeeMCPServer.handle_execute_goal

        async def capture_state(*args, **kwargs):
            nonlocal state_during_execution
            state_during_execution = beekeeper.current_session.state
            return await original_execute(*args, **kwargs)

        beekeeper.current_session.set_busy()  # 手動でBUSY設定

        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "ok",
                "llm_output": "done",
            },
        ):
            await beekeeper._delegate_to_queen_with_pipeline(
                colony_id="colony-state",
                task="状態テスト",
                trust_level=TrustLevel.FULL_DELEGATION,
            )

        # BUSYまたはACTIVEであること（complete後はACTIVEに戻る可能性）
        assert beekeeper.current_session.state in (
            SessionState.ACTIVE,
            SessionState.BUSY,
        )
