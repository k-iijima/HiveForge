"""エージェントチェーン統合テスト

Beekeeper → Queen Bee → Worker Bee のフルチェーン統合テスト。
LLM呼び出しをモックし、イベント発行・AR記録を検証する。

M2-2 完了条件:
- Beekeeper内部ツール（create_hive, create_colony, delegate_to_queen）が動作
- Queen Beeがライフサイクルイベント（RunStarted/Completed/Failed）を発行
- Worker Bee実行結果がARに記録され投影で確認可能
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.beekeeper.server import BeekeeperMCPServer
from hiveforge.core import AkashicRecord
from hiveforge.core.events import EventType
from hiveforge.queen_bee.server import QueenBeeMCPServer


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def beekeeper(ar):
    """テスト用Beekeeper"""
    return BeekeeperMCPServer(ar=ar)


@pytest.fixture
def queen_bee(ar):
    """テスト用Queen Bee"""
    return QueenBeeMCPServer(colony_id="colony-1", ar=ar)


# =========================================================================
# Beekeeper 内部ツールのテスト
# =========================================================================


class TestBeekeeperInternalTools:
    """Beekeeperの内部ツール（LLMが使えるツール）のテスト"""

    @pytest.mark.asyncio
    async def test_internal_create_hive(self, beekeeper):
        """内部ツールcreate_hiveでHiveが作成される

        LLMがcreate_hiveツールを呼んだときの動作を検証。
        HiveCreatedイベントがHiveStoreに永続化される。
        """
        # Act
        result = await beekeeper._internal_create_hive(
            name="テストプロジェクト", goal="テスト用のHive"
        )

        # Assert: 文字列結果にHive IDが含まれる
        assert "Hive作成完了" in result
        assert "hive_id=" in result

    @pytest.mark.asyncio
    async def test_internal_create_colony(self, beekeeper):
        """内部ツールcreate_colonyでColonyが作成される

        事前にHiveを作成し、そのHive内にColonyを作成。
        ColonyCreatedイベントがHiveStoreに永続化される。
        """
        # Arrange: まずHiveを作成
        hive_result = await beekeeper.handle_create_hive({"name": "テストHive", "goal": "テスト"})
        hive_id = hive_result["hive_id"]

        # Act
        result = await beekeeper._internal_create_colony(
            hive_id=hive_id, name="フロントエンド", domain="UI構築"
        )

        # Assert
        assert "Colony作成完了" in result
        assert "colony_id=" in result

    @pytest.mark.asyncio
    async def test_internal_create_colony_invalid_hive(self, beekeeper):
        """存在しないHiveにColonyを作成するとエラー"""
        # Act
        result = await beekeeper._internal_create_colony(
            hive_id="nonexistent", name="テスト", domain="テスト"
        )

        # Assert
        assert "Colony作成失敗" in result

    @pytest.mark.asyncio
    async def test_internal_list_hives_empty(self, beekeeper):
        """Hiveがない場合のlist_hives"""
        # Act
        result = await beekeeper._internal_list_hives()

        # Assert
        assert "まだありません" in result

    @pytest.mark.asyncio
    async def test_internal_list_hives_with_data(self, beekeeper):
        """Hive作成後のlist_hives"""
        # Arrange
        await beekeeper.handle_create_hive({"name": "テストHive", "goal": "テスト"})

        # Act
        result = await beekeeper._internal_list_hives()

        # Assert
        assert "Hive一覧" in result
        assert "テストHive" in result

    @pytest.mark.asyncio
    async def test_internal_tools_registered_with_agent_runner(self, beekeeper):
        """AgentRunner初期化時に内部ツールが登録される

        create_hive, create_colony, delegate_to_queen, ask_user,
        get_hive_status, list_hives の6ツールが登録されることを確認。
        """
        # Arrange: AgentRunnerのモックを設定
        mock_runner = MagicMock()
        mock_runner.register_tool = MagicMock()

        with patch.object(beekeeper, "_agent_runner", mock_runner):
            # Act
            beekeeper._register_internal_tools()

        # Assert: 6ツールが登録される
        assert mock_runner.register_tool.call_count == 6
        registered_names = [call.args[0].name for call in mock_runner.register_tool.call_args_list]
        assert "create_hive" in registered_names
        assert "create_colony" in registered_names
        assert "delegate_to_queen" in registered_names
        assert "ask_user" in registered_names
        assert "get_hive_status" in registered_names
        assert "list_hives" in registered_names


# =========================================================================
# Queen Bee ライフサイクルイベントのテスト
# =========================================================================


class TestQueenBeeLifecycleEvents:
    """Queen Beeが発行するライフサイクルイベントのテスト"""

    @pytest.mark.asyncio
    async def test_execute_goal_emits_run_started(self, queen_bee, ar):
        """execute_goal実行時にRunStartedイベントが発行される

        RunStartedイベントにはcolony_idとgoalが含まれる。
        """
        # Arrange: Worker BeeのLLM実行をモック
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "ok"},
        ):
            run_id = "test-run-001"

            # Act
            result = await queen_bee.handle_execute_goal(
                {"run_id": run_id, "goal": "Hello World作成"}
            )

        # Assert: RunStartedイベントがARに記録されている
        events = list(ar.replay(run_id))
        run_started_events = [e for e in events if e.type == EventType.RUN_STARTED]
        assert len(run_started_events) == 1
        assert run_started_events[0].payload["colony_id"] == "colony-1"
        assert run_started_events[0].payload["goal"] == "Hello World作成"

    @pytest.mark.asyncio
    async def test_execute_goal_emits_colony_started(self, queen_bee, ar):
        """execute_goal実行時にColonyStartedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "ok"},
        ):
            run_id = "test-run-002"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        events = list(ar.replay(run_id))
        colony_started = [e for e in events if e.type == EventType.COLONY_STARTED]
        assert len(colony_started) == 1
        assert colony_started[0].payload["colony_id"] == "colony-1"

    @pytest.mark.asyncio
    async def test_execute_goal_emits_run_completed_on_success(self, queen_bee, ar):
        """全タスク成功時にRunCompletedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "ok"},
        ):
            run_id = "test-run-003"

            # Act
            result = await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        assert result["status"] == "completed"
        events = list(ar.replay(run_id))
        run_completed = [e for e in events if e.type == EventType.RUN_COMPLETED]
        assert len(run_completed) == 1
        assert run_completed[0].payload["tasks_completed"] == 1
        assert run_completed[0].payload["tasks_total"] == 1

    @pytest.mark.asyncio
    async def test_execute_goal_emits_run_failed_on_failure(self, queen_bee, ar):
        """タスク失敗時にRunFailedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "failed", "reason": "LLM error"},
        ):
            run_id = "test-run-004"

            # Act
            result = await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        assert result["status"] == "partial"
        events = list(ar.replay(run_id))
        run_failed = [e for e in events if e.type == EventType.RUN_FAILED]
        assert len(run_failed) == 1
        assert run_failed[0].payload["tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_execute_goal_emits_run_failed_on_exception(self, queen_bee, ar):
        """Worker Bee例外発生時にRunFailedイベントが発行される

        _execute_task内で例外がキャッチされるため、handle_execute_goalは
        "partial"ステータスを返す。RunFailedイベントは記録される。
        """
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("接続エラー"),
        ):
            run_id = "test-run-005"

            # Act
            result = await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert: _execute_task が例外をキャッチするため partial として返る
        assert result["status"] == "partial"
        events = list(ar.replay(run_id))
        run_failed = [e for e in events if e.type == EventType.RUN_FAILED]
        assert len(run_failed) == 1
        assert run_failed[0].payload["tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_execute_goal_emits_task_assigned(self, queen_bee, ar):
        """タスク実行時にTaskAssignedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "ok"},
        ):
            run_id = "test-run-006"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        events = list(ar.replay(run_id))
        task_assigned = [e for e in events if e.type == EventType.TASK_ASSIGNED]
        assert len(task_assigned) == 1
        assert "worker_id" in task_assigned[0].payload

    @pytest.mark.asyncio
    async def test_execute_goal_emits_task_completed(self, queen_bee, ar):
        """タスク成功時にTaskCompletedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "output"},
        ):
            run_id = "test-run-007"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        events = list(ar.replay(run_id))
        task_completed = [e for e in events if e.type == EventType.TASK_COMPLETED]
        assert len(task_completed) == 1

    @pytest.mark.asyncio
    async def test_execute_goal_emits_task_failed(self, queen_bee, ar):
        """タスク失敗時にTaskFailedイベントが発行される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "failed", "reason": "テスト失敗"},
        ):
            run_id = "test-run-008"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        events = list(ar.replay(run_id))
        task_failed = [e for e in events if e.type == EventType.TASK_FAILED]
        assert len(task_failed) == 1
        assert "テスト失敗" in task_failed[0].payload["reason"]


# =========================================================================
# フルチェーン統合テスト
# =========================================================================


class TestFullChainIntegration:
    """Beekeeper → Queen Bee → Worker Bee のフルチェーン統合テスト"""

    @pytest.mark.asyncio
    async def test_delegate_to_queen_creates_queen_and_executes(self, beekeeper, ar):
        """delegate_to_queenでQueen Beeが作成されタスクが実行される

        BeekeeperがQueen Beeを動的に作成し、タスクを委譲する。
        Worker Bee実行はモック。全イベントがARに記録される。
        """
        # Arrange: Worker BeeのLLM実行をモック
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "実装完了",
                "llm_output": "Hello Worldを作成しました",
            },
        ):
            # Act
            result = await beekeeper._delegate_to_queen(
                colony_id="colony-test",
                task="Hello Worldプログラムを作成",
            )

        # Assert: 結果文字列にタスク完了が含まれる
        assert "タスク完了" in result

        # Assert: Queen Beeが作成された
        assert "colony-test" in beekeeper._queens

    @pytest.mark.asyncio
    async def test_delegate_to_queen_records_events_in_ar(self, beekeeper, ar):
        """delegate_to_queen経由で全ライフサイクルイベントがARに記録される

        RunStarted → ColonyStarted → TaskCreated → TaskAssigned → TaskCompleted → RunCompleted
        の順でイベントが記録されることを検証。
        """
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "done",
                "llm_output": "ok",
            },
        ):
            # Act
            await beekeeper._delegate_to_queen(
                colony_id="colony-events",
                task="テストタスク",
            )

        # Assert: Queen Beeが使用したrun_idでイベントをリプレイ
        queen = beekeeper._queens["colony-events"]
        run_id = queen._current_run_id
        assert run_id is not None

        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        # 全ライフサイクルイベントが順序通りに記録されている
        assert EventType.RUN_STARTED in event_types
        assert EventType.COLONY_STARTED in event_types
        assert EventType.TASK_CREATED in event_types
        assert EventType.TASK_ASSIGNED in event_types
        assert EventType.TASK_COMPLETED in event_types
        assert EventType.RUN_COMPLETED in event_types

        # 順序の検証: RunStartedがRunCompletedより前
        run_started_idx = event_types.index(EventType.RUN_STARTED)
        run_completed_idx = event_types.index(EventType.RUN_COMPLETED)
        assert run_started_idx < run_completed_idx

    @pytest.mark.asyncio
    async def test_full_chain_hive_colony_delegate(self, beekeeper, ar):
        """Hive作成 → Colony作成 → タスク委譲のフルチェーン

        内部ツールを順番に呼び出し、全体の流れが正しく動作することを検証。
        """
        # Arrange: Worker BeeのLLM実行をモック
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={
                "status": "completed",
                "result": "ログインページ完成",
                "llm_output": "ログインフォームを作成しました",
            },
        ):
            # Step 1: Hive作成
            hive_result = await beekeeper._internal_create_hive(
                name="ECサイト", goal="ECサイトのログインページを作成"
            )
            assert "Hive作成完了" in hive_result

            # hive_idを抽出
            hive_id = hive_result.split("hive_id=")[1].split(",")[0]

            # Step 2: Colony作成
            colony_result = await beekeeper._internal_create_colony(
                hive_id=hive_id, name="フロントエンド", domain="UI構築"
            )
            assert "Colony作成完了" in colony_result

            # colony_idを抽出
            colony_id = colony_result.split("colony_id=")[1].split(",")[0]

            # Step 3: タスク委譲
            delegate_result = await beekeeper._delegate_to_queen(
                colony_id=colony_id,
                task="ログインフォームを実装",
            )
            assert "タスク完了" in delegate_result

        # Assert: Hive一覧にHiveが存在
        list_result = await beekeeper._internal_list_hives()
        assert "ECサイト" in list_result

        # Assert: Queen Beeが作成されている
        assert colony_id in beekeeper._queens

    @pytest.mark.asyncio
    async def test_delegate_failure_records_run_failed(self, beekeeper, ar):
        """タスク失敗時にRunFailedイベントがARに記録される"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "failed", "reason": "コンパイルエラー"},
        ):
            # Act
            result = await beekeeper._delegate_to_queen(
                colony_id="colony-fail",
                task="失敗するタスク",
            )

        # Assert
        assert "一部タスク完了" in result or "タスク失敗" in result

        # イベント検証
        queen = beekeeper._queens["colony-fail"]
        run_id = queen._current_run_id
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        assert EventType.RUN_STARTED in event_types
        assert EventType.RUN_FAILED in event_types
        assert EventType.TASK_FAILED in event_types

    @pytest.mark.asyncio
    async def test_delegate_reuses_existing_queen(self, beekeeper, ar):
        """同じColony IDへの2回目の委譲はQueen Beeを再利用する"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "done", "llm_output": "ok"},
        ):
            # Act: 1回目
            await beekeeper._delegate_to_queen(
                colony_id="colony-reuse",
                task="タスク1",
            )
            queen_first = beekeeper._queens["colony-reuse"]

            # Act: 2回目
            await beekeeper._delegate_to_queen(
                colony_id="colony-reuse",
                task="タスク2",
            )
            queen_second = beekeeper._queens["colony-reuse"]

        # Assert: 同じQueen Beeインスタンスが使われる
        assert queen_first is queen_second


# =========================================================================
# イベント順序・完全性の検証
# =========================================================================


class TestEventCompleteness:
    """イベントの完全性（全ライフサイクルが記録される）"""

    @pytest.mark.asyncio
    async def test_successful_run_event_sequence(self, queen_bee, ar):
        """成功Runでのイベントシーケンスが完全であること

        期待イベント順:
        1. RunStarted
        2. ColonyStarted
        3. TaskCreated
        4. TaskAssigned
        5. TaskCompleted
        6. RunCompleted
        """
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            run_id = "test-sequence-001"

            # Act
            result = await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert
        assert result["status"] == "completed"
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        expected_sequence = [
            EventType.RUN_STARTED,
            EventType.COLONY_STARTED,
            EventType.TASK_CREATED,
            EventType.TASK_ASSIGNED,
            EventType.TASK_COMPLETED,
            EventType.RUN_COMPLETED,
        ]

        # 全てのイベントが存在する
        for expected in expected_sequence:
            assert expected in event_types, f"{expected} が見つかりません"

        # 順序の検証
        for i in range(len(expected_sequence) - 1):
            idx_current = event_types.index(expected_sequence[i])
            idx_next = event_types.index(expected_sequence[i + 1])
            assert idx_current < idx_next, (
                f"{expected_sequence[i]} が {expected_sequence[i + 1]} より後"
            )

    @pytest.mark.asyncio
    async def test_failed_run_event_sequence(self, queen_bee, ar):
        """失敗Runでのイベントシーケンスが完全であること

        期待イベント順:
        1. RunStarted
        2. ColonyStarted
        3. TaskCreated
        4. TaskAssigned
        5. TaskFailed
        6. RunFailed
        """
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "failed", "reason": "エラー"},
        ):
            run_id = "test-sequence-002"

            # Act
            result = await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "失敗タスク"})

        # Assert
        assert result["status"] == "partial"
        events = list(ar.replay(run_id))
        event_types = [e.type for e in events]

        expected_sequence = [
            EventType.RUN_STARTED,
            EventType.COLONY_STARTED,
            EventType.TASK_CREATED,
            EventType.TASK_ASSIGNED,
            EventType.TASK_FAILED,
            EventType.RUN_FAILED,
        ]

        for expected in expected_sequence:
            assert expected in event_types, f"{expected} が見つかりません"

    @pytest.mark.asyncio
    async def test_all_events_have_consistent_run_id(self, queen_bee, ar):
        """全イベントが同一のrun_idを持つ"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            run_id = "test-consistency-001"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert: 全イベントのrun_idが一致
        events = list(ar.replay(run_id))
        assert len(events) >= 4  # 最低でもRunStarted, ColonyStarted, TaskCreated, TaskAssigned
        for event in events:
            assert event.run_id == run_id

    @pytest.mark.asyncio
    async def test_all_events_have_queen_actor(self, queen_bee, ar):
        """Queen Beeが発行する全イベントのactorが正しい"""
        # Arrange
        with patch(
            "hiveforge.worker_bee.server.WorkerBeeMCPServer.execute_task_with_llm",
            new_callable=AsyncMock,
            return_value={"status": "completed", "result": "ok", "llm_output": "done"},
        ):
            run_id = "test-actor-001"

            # Act
            await queen_bee.handle_execute_goal({"run_id": run_id, "goal": "テスト"})

        # Assert: Queen Beeのactorがcolony-idを含む
        events = list(ar.replay(run_id))
        queen_events = [e for e in events if e.actor == f"queen-{queen_bee.colony_id}"]
        assert len(queen_events) >= 4  # RunStarted, ColonyStarted, TaskCreated, TaskAssigned
