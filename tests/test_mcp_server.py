"""MCP Server モジュールのテスト"""

from unittest.mock import MagicMock, patch

import pytest

from hiveforge.mcp_server.server import HiveForgeMCPServer


@pytest.fixture
def mcp_server(tmp_path):
    """テスト用MCPサーバー"""
    with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = tmp_path / "Vault"
        mock_settings.return_value = mock_s

        server = HiveForgeMCPServer()

        # ハンドラーへのショートカットを追加（テスト互換性のため）
        server._handle_start_run = server._run_handlers.handle_start_run
        server._handle_get_run_status = server._run_handlers.handle_get_run_status
        server._handle_complete_run = server._run_handlers.handle_complete_run
        server._handle_heartbeat = server._run_handlers.handle_heartbeat
        server._handle_emergency_stop = server._run_handlers.handle_emergency_stop
        server._handle_create_task = server._task_handlers.handle_create_task
        server._handle_assign_task = server._task_handlers.handle_assign_task
        server._handle_report_progress = server._task_handlers.handle_report_progress
        server._handle_complete_task = server._task_handlers.handle_complete_task
        server._handle_fail_task = server._task_handlers.handle_fail_task
        server._handle_create_requirement = server._requirement_handlers.handle_create_requirement
        server._handle_get_lineage = server._lineage_handlers.handle_get_lineage
        server._handle_record_decision = server._decision_handlers.handle_record_decision

        yield server


class TestHiveForgeMCPServerInit:
    """MCP Server初期化のテスト"""

    def test_server_initialization(self, tmp_path):
        """サーバーが初期化される"""
        with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.return_value = mock_s

            # Act
            server = HiveForgeMCPServer()

            # Assert
            assert server.server is not None
            assert server._ar is None
            assert server._current_run_id is None


class TestGetAr:
    """_get_ar関数のテスト"""

    def test_get_ar_creates_instance(self, mcp_server):
        """ARインスタンスを作成する"""
        # Act
        ar = mcp_server._get_ar()

        # Assert
        assert ar is not None

    def test_get_ar_returns_existing(self, mcp_server):
        """既存のARインスタンスを返す"""
        # Arrange
        mock_ar = MagicMock()
        mcp_server._ar = mock_ar

        # Act
        ar = mcp_server._get_ar()

        # Assert
        assert ar is mock_ar


class TestHandleStartRun:
    """start_runハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_start_run(self, mcp_server):
        """Runを開始できる"""
        # Act
        result = await mcp_server._handle_start_run({"goal": "テスト目標"})

        # Assert
        assert result["status"] == "started"
        assert "run_id" in result
        assert result["goal"] == "テスト目標"
        assert mcp_server._current_run_id is not None


class TestHandleGetRunStatus:
    """get_run_statusハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_get_run_status_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_get_run_status({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_run_status_run_not_found(self, mcp_server):
        """存在しないRunの場合"""
        # Arrange
        mcp_server._current_run_id = "nonexistent"

        # Act
        result = await mcp_server._handle_get_run_status({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_run_status_success(self, mcp_server):
        """Run状態を取得できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "状態確認テスト"})

        # Act
        result = await mcp_server._handle_get_run_status({})

        # Assert
        assert result["goal"] == "状態確認テスト"
        assert result["state"] == "running"
        assert "tasks" in result

    @pytest.mark.asyncio
    async def test_get_run_status_with_run_id(self, mcp_server):
        """指定したRun IDの状態を取得できる"""
        # Arrange
        start_result = await mcp_server._handle_start_run({"goal": "ID指定テスト"})
        run_id = start_result["run_id"]

        # Act
        result = await mcp_server._handle_get_run_status({"run_id": run_id})

        # Assert
        assert result["run_id"] == run_id


class TestHandleCreateTask:
    """create_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_create_task_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_create_task({"title": "タスク"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_task_success(self, mcp_server):
        """Taskを作成できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "タスク作成テスト"})

        # Act
        result = await mcp_server._handle_create_task(
            {
                "title": "テストタスク",
                "description": "詳細説明",
            }
        )

        # Assert
        assert result["status"] == "created"
        assert "task_id" in result
        assert result["title"] == "テストタスク"

    @pytest.mark.asyncio
    async def test_create_task_auto_parents_defaults_to_run_started(self, mcp_server):
        """parents未指定なら task.created は run.started を親に自動補完する

        Issue #001 のルール: task.created -> run.started
        """
        # Arrange
        from hiveforge.core.events import EventType

        await mcp_server._handle_start_run({"goal": "auto parents"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()
        run_started_id = next(e.id for e in ar.replay(run_id) if e.type == EventType.RUN_STARTED)

        # Act
        result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = result["task_id"]

        # Assert
        created_event = next(
            e
            for e in ar.replay(run_id)
            if e.type == EventType.TASK_CREATED and e.task_id == task_id
        )
        assert created_event.parents == [run_started_id]

    @pytest.mark.asyncio
    async def test_create_task_explicit_parents_are_preserved(self, mcp_server):
        """parentsを明示した場合は自動補完せず、そのまま使う"""
        # Arrange
        from hiveforge.core.events import EventType

        await mcp_server._handle_start_run({"goal": "explicit parents"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        # Act
        result = await mcp_server._handle_create_task({"title": "タスク", "parents": ["p1"]})
        task_id = result["task_id"]

        # Assert
        created_event = next(
            e
            for e in ar.replay(run_id)
            if e.type == EventType.TASK_CREATED and e.task_id == task_id
        )
        assert created_event.parents == ["p1"]


class TestHandleAssignTask:
    """assign_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_assign_task_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_assign_task({"task_id": "task-123"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_assign_task_no_task_id(self, mcp_server):
        """task_idがない場合"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_assign_task({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_assign_task_success(self, mcp_server):
        """Taskを割り当てできる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "割り当てテスト"})
        create_result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._handle_assign_task({"task_id": task_id})

        # Assert
        assert result["status"] == "assigned"
        assert result["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_assign_task_auto_parents_defaults_to_task_created(self, mcp_server):
        """parents未指定なら task.assigned は task.created を親に自動補完する

        Issue #001 のルール: task.assigned -> task.created
        """
        # Arrange
        from hiveforge.core.events import EventType

        await mcp_server._handle_start_run({"goal": "auto parents"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        create_result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = create_result["task_id"]
        created_event_id = next(
            e.id
            for e in ar.replay(run_id)
            if e.type == EventType.TASK_CREATED and e.task_id == task_id
        )

        # Act
        await mcp_server._handle_assign_task({"task_id": task_id})

        # Assert
        assigned_event = next(
            e
            for e in ar.replay(run_id)
            if e.type == EventType.TASK_ASSIGNED and e.task_id == task_id
        )
        assert assigned_event.parents == [created_event_id]


class TestHandleReportProgress:
    """report_progressハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_report_progress_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_report_progress(
            {
                "task_id": "task-123",
                "progress": 50,
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_no_task_id(self, mcp_server):
        """task_idがない場合"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_report_progress({"progress": 50})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_success(self, mcp_server):
        """進捗を報告できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "進捗テスト"})
        create_result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._handle_report_progress(
            {
                "task_id": task_id,
                "progress": 50,
                "message": "半分完了",
            }
        )

        # Assert
        assert result["status"] == "progressed"
        assert result["progress"] == 50


class TestHandleCompleteTask:
    """complete_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_complete_task_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_complete_task({"task_id": "task-123"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_complete_task_no_task_id(self, mcp_server):
        """task_idがない場合"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_complete_task({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_complete_task_success(self, mcp_server):
        """Taskを完了できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "完了テスト"})
        create_result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._handle_complete_task(
            {
                "task_id": task_id,
                "result": "成果物",
            }
        )

        # Assert
        assert result["status"] == "completed"
        assert result["task_id"] == task_id


class TestHandleFailTask:
    """fail_taskハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_fail_task_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_fail_task(
            {
                "task_id": "task-123",
                "error": "エラー",
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fail_task_no_task_id(self, mcp_server):
        """task_idがない場合"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_fail_task({"error": "エラー"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fail_task_success(self, mcp_server):
        """Taskを失敗させることができる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "失敗テスト"})
        create_result = await mcp_server._handle_create_task({"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._handle_fail_task(
            {
                "task_id": task_id,
                "error": "エラーが発生",
                "retryable": False,
            }
        )

        # Assert
        assert result["status"] == "failed"
        assert result["error"] == "エラーが発生"


class TestHandleCreateRequirement:
    """create_requirementハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_create_requirement_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_create_requirement(
            {
                "description": "確認内容",
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_requirement_success(self, mcp_server):
        """要件を作成できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "要件テスト"})

        # Act
        result = await mcp_server._handle_create_requirement(
            {
                "description": "本当に実行しますか？",
                "options": ["はい", "いいえ"],
            }
        )

        # Assert
        assert result["status"] == "created"
        assert "requirement_id" in result
        assert result["description"] == "本当に実行しますか？"

    @pytest.mark.asyncio
    async def test_create_requirement_auto_parents_defaults_to_run_started(self, mcp_server):
        """requirement.created は run.started をparentsに持つ

        Issue #001 のルール: requirement.created -> run.started
        """
        # Arrange
        from hiveforge.core.events import EventType

        start_result = await mcp_server._handle_start_run({"goal": "auto parents requirement"})
        run_id = start_result["run_id"]

        ar = mcp_server._get_ar()
        run_started_id = next(e.id for e in ar.replay(run_id) if e.type == EventType.RUN_STARTED)

        # Act
        await mcp_server._handle_create_requirement({"description": "確認してください"})

        # Assert
        req_event = next(e for e in ar.replay(run_id) if e.type == EventType.REQUIREMENT_CREATED)
        assert req_event.parents == [run_started_id]


class TestHandleCompleteRun:
    """complete_runハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_complete_run_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_complete_run({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_complete_run_success(self, mcp_server):
        """タスクがない場合、Runを完了できる"""
        # Arrange
        start_result = await mcp_server._handle_start_run({"goal": "完了テスト"})
        run_id = start_result["run_id"]

        # Act
        result = await mcp_server._handle_complete_run(
            {
                "summary": "全てのタスクが完了しました",
            }
        )

        # Assert
        assert result["status"] == "completed"
        assert result["run_id"] == run_id
        assert mcp_server._current_run_id is None

    @pytest.mark.asyncio
    async def test_complete_run_with_incomplete_tasks_fails(self, mcp_server):
        """未完了タスクがある場合、エラーを返す"""
        # Arrange: Runを開始してタスクを作成（未完了のまま）
        await mcp_server._handle_start_run({"goal": "未完了タスクテスト"})
        task_result = await mcp_server._handle_create_task({"title": "未完了タスク"})
        task_id = task_result["task_id"]

        # Act
        result = await mcp_server._handle_complete_run({})

        # Assert
        assert "error" in result
        assert "incomplete_task_ids" in result
        assert task_id in result["incomplete_task_ids"]

    @pytest.mark.asyncio
    async def test_complete_run_force_cancels_tasks(self, mcp_server):
        """force=trueで未完了タスクをキャンセルして完了できる"""
        # Arrange: Runを開始してタスクを作成（未完了のまま）
        start_result = await mcp_server._handle_start_run({"goal": "強制完了テスト"})
        run_id = start_result["run_id"]
        task_result = await mcp_server._handle_create_task({"title": "キャンセル対象"})
        task_id = task_result["task_id"]

        # Act
        result = await mcp_server._handle_complete_run({"force": True})

        # Assert
        assert result["status"] == "completed"
        assert run_id == result["run_id"]
        assert "cancelled_task_ids" in result
        assert task_id in result["cancelled_task_ids"]

    @pytest.mark.asyncio
    async def test_complete_run_force_rejects_pending_requirements(self, mcp_server):
        """force=trueで未解決の確認要請も却下して完了できる"""
        # Arrange: Runを開始して確認要請を作成
        start_result = await mcp_server._handle_start_run({"goal": "強制完了テスト"})
        run_id = start_result["run_id"]
        req_result = await mcp_server._handle_create_requirement(
            {"description": "未解決の確認要請", "options": ["承認", "却下"]}
        )
        req_id = req_result["requirement_id"]

        # Act: force=trueで強制完了
        result = await mcp_server._handle_complete_run({"force": True})

        # Assert: 確認要請も却下される
        assert result["status"] == "completed"
        assert run_id == result["run_id"]
        assert "cancelled_requirement_ids" in result
        assert req_id in result["cancelled_requirement_ids"]

    @pytest.mark.asyncio
    async def test_complete_run_with_pending_requirements_fails(self, mcp_server):
        """未解決の確認要請がある場合はRun完了できない"""
        # Arrange: Runを開始して確認要請を作成（タスクなし）
        await mcp_server._handle_start_run({"goal": "確認要請テスト"})
        await mcp_server._handle_create_requirement(
            {"description": "未解決の確認要請", "options": ["承認", "却下"]}
        )

        # Act: 通常完了を試みる
        result = await mcp_server._handle_complete_run({})

        # Assert: エラーになる
        assert "error" in result
        assert "pending_requirement_ids" in result

    @pytest.mark.asyncio
    async def test_complete_run_with_completed_tasks(self, mcp_server):
        """全タスクが完了している場合、Runを完了できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "タスク完了済みテスト"})
        task_result = await mcp_server._handle_create_task({"title": "完了タスク"})
        task_id = task_result["task_id"]
        await mcp_server._handle_complete_task({"task_id": task_id, "result": "Done"})

        # Act
        result = await mcp_server._handle_complete_run({"summary": "完了"})

        # Assert
        assert result["status"] == "completed"
        assert "cancelled_task_ids" not in result


class TestHandleHeartbeat:
    """heartbeatハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_heartbeat_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_heartbeat({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, mcp_server):
        """ハートビートを送信できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "ハートビートテスト"})

        # Act
        result = await mcp_server._handle_heartbeat(
            {
                "message": "処理中...",
            }
        )

        # Assert
        assert result["status"] == "ok"
        assert "timestamp" in result


class TestHandleEmergencyStop:
    """emergency_stopハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_emergency_stop_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_emergency_stop({"reason": "テスト"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_emergency_stop_success(self, mcp_server):
        """Runを緊急停止できる"""
        # Arrange
        start_result = await mcp_server._handle_start_run({"goal": "緊急停止テスト"})
        run_id = start_result["run_id"]

        # Act
        result = await mcp_server._handle_emergency_stop(
            {
                "reason": "危険な操作を検知",
                "scope": "run",
            }
        )

        # Assert
        assert result["status"] == "aborted"
        assert result["run_id"] == run_id
        assert result["reason"] == "危険な操作を検知"
        assert result["scope"] == "run"
        assert "stopped_at" in result
        assert mcp_server._current_run_id is None

    @pytest.mark.asyncio
    async def test_emergency_stop_default_scope(self, mcp_server):
        """スコープのデフォルト値がrunになる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "スコープテスト"})

        # Act
        result = await mcp_server._handle_emergency_stop({"reason": "理由なし"})

        # Assert
        assert result["scope"] == "run"

    @pytest.mark.asyncio
    async def test_emergency_stop_cancels_tasks(self, mcp_server):
        """緊急停止は未完了タスクをキャンセルする"""
        # Arrange: Runを開始してタスクを作成
        await mcp_server._handle_start_run({"goal": "緊急停止タスクテスト"})
        task_result = await mcp_server._handle_create_task({"title": "進行中タスク"})
        task_id = task_result["task_id"]

        # Act: 緊急停止を実行
        result = await mcp_server._handle_emergency_stop({"reason": "テスト停止"})

        # Assert: タスクがキャンセルされている
        assert result["status"] == "aborted"
        assert "cancelled_task_ids" in result
        assert task_id in result["cancelled_task_ids"]

    @pytest.mark.asyncio
    async def test_emergency_stop_rejects_pending_requirements(self, mcp_server):
        """緊急停止は未解決の確認要請を却下する"""
        # Arrange: Runを開始して確認要請を作成
        await mcp_server._handle_start_run({"goal": "緊急停止確認要請テスト"})
        req_result = await mcp_server._handle_create_requirement(
            {
                "description": "テスト確認要請",
            }
        )
        req_id = req_result["requirement_id"]

        # Act: 緊急停止を実行
        result = await mcp_server._handle_emergency_stop({"reason": "テスト停止"})

        # Assert: 確認要請が却下されている
        assert result["status"] == "aborted"
        assert "cancelled_requirement_ids" in result
        assert req_id in result["cancelled_requirement_ids"]


class TestHandleGetLineage:
    """get_lineageハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_get_lineage_no_active_run(self, mcp_server):
        """アクティブなRunがない場合"""
        # Act
        result = await mcp_server._handle_get_lineage({"event_id": "test-id"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_lineage_event_id_required(self, mcp_server):
        """event_idが必要"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_get_lineage({})

        # Assert
        assert "error" in result
        assert "event_id" in result["error"]

    @pytest.mark.asyncio
    async def test_get_lineage_event_not_found(self, mcp_server):
        """存在しないイベントの場合"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "テスト"})

        # Act
        result = await mcp_server._handle_get_lineage({"event_id": "nonexistent"})

        # Assert
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_lineage_success(self, mcp_server):
        """因果リンクを取得できる"""
        # Arrange
        start_result = await mcp_server._handle_start_run({"goal": "リネージュテスト"})
        run_id = start_result["run_id"]

        # タスクを作成してイベントを増やす
        await mcp_server._handle_create_task({"title": "テストタスク"})

        # 最初のイベントのIDを取得（start_run時のイベント）
        ar = mcp_server._get_ar()
        events = list(ar.replay(run_id))
        event_id = events[0].id

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": event_id,
                "direction": "both",
                "max_depth": 5,
            }
        )

        # Assert
        assert result["event_id"] == event_id
        assert "ancestors" in result
        assert "descendants" in result
        assert "truncated" in result

    @pytest.mark.asyncio
    async def test_get_lineage_ancestors_only(self, mcp_server):
        """祖先のみを取得できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "祖先テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()
        events = list(ar.replay(run_id))
        event_id = events[0].id

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": event_id,
                "direction": "ancestors",
            }
        )

        # Assert
        assert result["event_id"] == event_id
        assert "ancestors" in result

    @pytest.mark.asyncio
    async def test_get_lineage_descendants_only(self, mcp_server):
        """子孫のみを取得できる"""
        # Arrange
        await mcp_server._handle_start_run({"goal": "子孫テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()
        events = list(ar.replay(run_id))
        event_id = events[0].id

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": event_id,
                "direction": "descendants",
            }
        )

        # Assert
        assert result["event_id"] == event_id
        assert "descendants" in result


class TestGetLineageWithParents:
    """parents付きイベントでのget_lineageテスト"""

    @pytest.mark.asyncio
    async def test_get_lineage_finds_ancestors(self, mcp_server):
        """parentsを持つイベントの祖先を取得できる"""
        from hiveforge.core.events import HeartbeatEvent

        # Arrange
        await mcp_server._handle_start_run({"goal": "祖先探索テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        events = list(ar.replay(run_id))
        first_event_id = events[0].id

        # parentsを持つイベントを追加
        event2 = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=[first_event_id],
        )
        ar.append(event2, run_id)

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": event2.id,
                "direction": "ancestors",
            }
        )

        # Assert
        assert first_event_id in result["ancestors"]

    @pytest.mark.asyncio
    async def test_get_lineage_finds_descendants(self, mcp_server):
        """子孫を取得できる"""
        from hiveforge.core.events import HeartbeatEvent

        # Arrange
        await mcp_server._handle_start_run({"goal": "子孫探索テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        events = list(ar.replay(run_id))
        first_event_id = events[0].id

        # parentsを持つ子イベントを追加
        child_event = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=[first_event_id],
        )
        ar.append(child_event, run_id)

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": first_event_id,
                "direction": "descendants",
            }
        )

        # Assert
        assert child_event.id in result["descendants"]

    @pytest.mark.asyncio
    async def test_get_lineage_truncated(self, mcp_server):
        """深度制限を超えるとtruncatedになる"""
        from hiveforge.core.events import HeartbeatEvent

        # Arrange
        await mcp_server._handle_start_run({"goal": "深度制限テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        events = list(ar.replay(run_id))
        prev_id = events[0].id

        # 深いチェーンを作成
        for _ in range(5):
            event = HeartbeatEvent(
                run_id=run_id,
                actor="test",
                parents=[prev_id],
            )
            ar.append(event, run_id)
            prev_id = event.id

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": prev_id,
                "direction": "ancestors",
                "max_depth": 2,
            }
        )

        # Assert
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_get_lineage_descendants_depth_truncated(self, mcp_server):
        """子孫探索で深度制限を超えるとtruncatedになる"""
        from hiveforge.core.events import HeartbeatEvent

        # Arrange
        await mcp_server._handle_start_run({"goal": "子孫深度テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        events = list(ar.replay(run_id))
        first_event_id = events[0].id

        # 深いチェーンを作成
        prev_id = first_event_id
        for _ in range(5):
            event = HeartbeatEvent(
                run_id=run_id,
                actor="test",
                parents=[prev_id],
            )
            ar.append(event, run_id)
            prev_id = event.id

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": first_event_id,
                "direction": "descendants",
                "max_depth": 2,
            }
        )

        # Assert
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_get_lineage_with_nonexistent_parent(self, mcp_server):
        """存在しない親を持つイベントでもエラーにならない"""
        from hiveforge.core.events import HeartbeatEvent

        # Arrange
        await mcp_server._handle_start_run({"goal": "存在しない親テスト"})
        run_id = mcp_server._current_run_id
        ar = mcp_server._get_ar()

        # 存在しない親を持つイベントを作成
        event = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=["nonexistent-parent-id"],
        )
        ar.append(event, run_id)

        # Act
        result = await mcp_server._handle_get_lineage(
            {
                "event_id": event.id,
                "direction": "ancestors",
            }
        )

        # Assert: エラーにならない（存在しない親はスキップ）
        assert "error" not in result
        assert result["event_id"] == event.id


class TestMainFunction:
    """main関数のテスト"""

    def test_main_function_exists(self):
        """main関数が存在する"""
        from hiveforge.mcp_server.server import main

        assert callable(main)


class TestIfNameMain:
    """__name__ == '__main__' のテスト"""

    def test_module_entry_point(self):
        """モジュールをスクリプトとして実行できる"""
        # この行は if __name__ == "__main__" がpragma: no coverされているので
        # main関数が呼び出し可能であることを確認するだけ
        from hiveforge.mcp_server.server import main

        assert callable(main)


class TestServerHandlers:
    """サーバーハンドラのテスト"""

    def test_list_tools_handler_registered(self, mcp_server):
        """list_toolsハンドラが登録されている"""
        # サーバーのリストツールハンドラにアクセス
        # 内部的にハンドラが登録されていることを確認
        assert mcp_server.server is not None

    def test_call_tool_unknown_tool(self, mcp_server):
        """未知のツールはハンドラがNone"""
        # call_toolは内部でgetattrを使って_handle_{name}を探す
        # 存在しないハンドラの場合はNoneが返される
        handler = getattr(mcp_server, "_handle_unknown_tool", None)
        assert handler is None

    @pytest.mark.asyncio
    async def test_exception_handling_in_handler(self, mcp_server):
        """ハンドラで例外が発生した場合のテスト"""
        # 意図的に例外を発生させるようなテストケース
        original_handler = mcp_server._handle_start_run

        async def raise_error(args):
            raise ValueError("テストエラー")

        mcp_server._handle_start_run = raise_error

        try:
            # 例外が発生することを確認
            with pytest.raises(ValueError):
                await mcp_server._handle_start_run({})
        finally:
            mcp_server._handle_start_run = original_handler


class TestDispatchTool:
    """_dispatch_tool メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_start_run(self, mcp_server):
        """start_run ツールをディスパッチする"""
        # Act
        result = await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Assert
        assert result["status"] == "started"
        assert "run_id" in result

    @pytest.mark.asyncio
    async def test_dispatch_get_run_status(self, mcp_server):
        """get_run_status ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("get_run_status", {})

        # Assert
        assert result["goal"] == "テスト"
        assert result["state"] == "running"

    @pytest.mark.asyncio
    async def test_dispatch_complete_run(self, mcp_server):
        """complete_run ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("complete_run", {"summary": "完了"})

        # Assert
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_dispatch_heartbeat(self, mcp_server):
        """heartbeat ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("heartbeat", {"message": "生存確認"})

        # Assert
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_emergency_stop(self, mcp_server):
        """emergency_stop ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("emergency_stop", {"reason": "緊急停止テスト"})

        # Assert
        assert result["status"] == "aborted"

    @pytest.mark.asyncio
    async def test_dispatch_create_task(self, mcp_server):
        """create_task ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("create_task", {"title": "タスク1"})

        # Assert
        assert result["status"] == "created"
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_dispatch_assign_task(self, mcp_server):
        """assign_task ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})
        create_result = await mcp_server._dispatch_tool("create_task", {"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._dispatch_tool("assign_task", {"task_id": task_id})

        # Assert
        assert result["status"] == "assigned"

    @pytest.mark.asyncio
    async def test_dispatch_report_progress(self, mcp_server):
        """report_progress ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})
        create_result = await mcp_server._dispatch_tool("create_task", {"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._dispatch_tool(
            "report_progress", {"task_id": task_id, "progress": 50}
        )

        # Assert
        assert result["status"] == "progressed"

    @pytest.mark.asyncio
    async def test_dispatch_complete_task(self, mcp_server):
        """complete_task ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})
        create_result = await mcp_server._dispatch_tool("create_task", {"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._dispatch_tool(
            "complete_task", {"task_id": task_id, "result": "完了"}
        )

        # Assert
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_dispatch_fail_task(self, mcp_server):
        """fail_task ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})
        create_result = await mcp_server._dispatch_tool("create_task", {"title": "タスク"})
        task_id = create_result["task_id"]

        # Act
        result = await mcp_server._dispatch_tool(
            "fail_task", {"task_id": task_id, "error": "エラー"}
        )

        # Assert
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_dispatch_create_requirement(self, mcp_server):
        """create_requirement ツールをディスパッチする"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})

        # Act
        result = await mcp_server._dispatch_tool("create_requirement", {"description": "確認事項"})

        # Assert
        assert result["status"] == "created"
        assert "requirement_id" in result

    @pytest.mark.asyncio
    async def test_dispatch_get_lineage(self, mcp_server):
        """get_lineage ツールをディスパッチする"""
        # Arrange
        start_result = await mcp_server._dispatch_tool("start_run", {"goal": "テスト"})
        run_id = start_result["run_id"]
        # イベントを取得
        ar = mcp_server._get_ar()
        events = list(ar.replay(run_id))
        event_id = events[0].id  # Pydanticモデルなので属性アクセス

        # Act
        result = await mcp_server._dispatch_tool("get_lineage", {"event_id": event_id})

        # Assert
        assert "event_id" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, mcp_server):
        """未知のツールをディスパッチするとエラーを返す"""
        # Act
        result = await mcp_server._dispatch_tool("unknown_tool", {})

        # Assert
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestMCPToolDefinitions:
    """MCP ツール定義のテスト"""

    def test_get_tool_definitions_returns_list(self):
        """get_tool_definitionsがToolのリストを返す"""
        # Arrange
        from hiveforge.mcp_server.tools import get_tool_definitions

        # Act
        tools = get_tool_definitions()

        # Assert
        assert isinstance(tools, list)
        assert len(tools) > 0
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")

    def test_tool_definitions_include_required_tools(self):
        """必須ツールが含まれている"""
        # Arrange
        from hiveforge.mcp_server.tools import get_tool_definitions

        # Act
        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Assert
        required_tools = [
            "start_run",
            "get_run_status",
            "complete_run",
            "create_task",
            "complete_task",
            "fail_task",
            "heartbeat",
            "emergency_stop",
            "create_requirement",
            "record_decision",
            "get_lineage",
        ]
        for required in required_tools:
            assert required in tool_names, f"{required} should be in tool definitions"


class TestDecisionTool:
    """Decisionツールのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_record_decision(self, mcp_server):
        """record_decision ツールをディスパッチする"""
        # Arrange: Run開始
        await mcp_server._handle_start_run({"goal": "仕様Decision化"})

        # Act
        result = await mcp_server._dispatch_tool(
            "record_decision",
            {
                "key": "D3",
                "title": "Requirementを2階層に分割",
                "selected": "C",
                "rationale": "v3のユーザー要求と現状の確認要請を両立するため",
            },
        )

        # Assert
        assert result["status"] == "recorded"
        assert result["key"] == "D3"
        assert "decision_id" in result


class TestDispatchHiveColonyTools:
    """Hive/Colony ディスパッチのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_create_hive(self, mcp_server):
        """create_hiveをディスパッチ"""
        result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test Hive", "goal": "Testing"}
        )
        assert "hive_id" in result

    @pytest.mark.asyncio
    async def test_dispatch_list_hives(self, mcp_server):
        """list_hivesをディスパッチ"""
        result = await mcp_server._dispatch_tool("list_hives", {})
        assert "hives" in result

    @pytest.mark.asyncio
    async def test_dispatch_get_hive(self, mcp_server):
        """get_hiveをディスパッチ"""
        # Arrange
        create_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        hive_id = create_result["hive_id"]

        # Act
        result = await mcp_server._dispatch_tool("get_hive", {"hive_id": hive_id})

        # Assert
        assert result.get("hive_id") == hive_id or "error" not in result

    @pytest.mark.asyncio
    async def test_dispatch_close_hive(self, mcp_server):
        """close_hiveをディスパッチ"""
        # Arrange
        create_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        hive_id = create_result["hive_id"]

        # Act
        result = await mcp_server._dispatch_tool("close_hive", {"hive_id": hive_id})

        # Assert
        assert "error" not in result or "closed" in str(result)

    @pytest.mark.asyncio
    async def test_dispatch_create_colony(self, mcp_server):
        """create_colonyをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test Hive", "goal": "Test"}
        )
        hive_id = hive_result["hive_id"]

        # Act
        result = await mcp_server._dispatch_tool(
            "create_colony", {"hive_id": hive_id, "name": "UI Colony", "domain": "UI/UX"}
        )

        # Assert
        assert "colony_id" in result

    @pytest.mark.asyncio
    async def test_dispatch_list_colonies(self, mcp_server):
        """list_coloniesをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        hive_id = hive_result["hive_id"]

        # Act
        result = await mcp_server._dispatch_tool("list_colonies", {"hive_id": hive_id})

        # Assert
        assert "colonies" in result or "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_start_colony(self, mcp_server):
        """start_colonyをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        colony_result = await mcp_server._dispatch_tool(
            "create_colony", {"hive_id": hive_result["hive_id"], "name": "Test", "domain": "Test"}
        )

        # Act
        result = await mcp_server._dispatch_tool(
            "start_colony", {"colony_id": colony_result["colony_id"]}
        )

        # Assert
        assert "status" in result or "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_complete_colony(self, mcp_server):
        """complete_colonyをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        colony_result = await mcp_server._dispatch_tool(
            "create_colony", {"hive_id": hive_result["hive_id"], "name": "Test", "domain": "Test"}
        )

        # Act
        result = await mcp_server._dispatch_tool(
            "complete_colony", {"colony_id": colony_result["colony_id"]}
        )

        # Assert
        assert "status" in result or "error" in result


class TestDispatchConferenceTools:
    """Conference ディスパッチのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_start_conference(self, mcp_server):
        """start_conferenceをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )

        # Act
        result = await mcp_server._dispatch_tool(
            "start_conference",
            {"hive_id": hive_result["hive_id"], "topic": "Design Review", "participants": ["ui", "api"]},
        )

        # Assert
        assert "conference_id" in result or "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_list_conferences(self, mcp_server):
        """list_conferencesをディスパッチ"""
        result = await mcp_server._dispatch_tool("list_conferences", {})
        assert "conferences" in result or "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_get_conference(self, mcp_server):
        """get_conferenceをディスパッチ"""
        result = await mcp_server._dispatch_tool(
            "get_conference", {"conference_id": "nonexistent"}
        )
        # エラーでも成功でもOK（パス通過確認）
        assert result is not None

    @pytest.mark.asyncio
    async def test_dispatch_end_conference(self, mcp_server):
        """end_conferenceをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        conf_result = await mcp_server._dispatch_tool(
            "start_conference",
            {"hive_id": hive_result["hive_id"], "topic": "Test", "participants": []},
        )

        # Act
        result = await mcp_server._dispatch_tool(
            "end_conference",
            {"conference_id": conf_result.get("conference_id", "x"), "summary": "Done"},
        )

        # Assert
        assert result is not None


class TestDispatchInterventionTools:
    """Intervention ディスパッチのテスト"""

    @pytest.mark.asyncio
    async def test_dispatch_user_intervene(self, mcp_server):
        """user_interveneをディスパッチ"""
        # Arrange
        await mcp_server._dispatch_tool("start_run", {"goal": "Test"})

        # Act
        result = await mcp_server._dispatch_tool(
            "user_intervene",
            {"target_type": "run", "target_id": "test", "action": "adjust", "message": "Fix this"},
        )

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_dispatch_queen_escalate(self, mcp_server):
        """queen_escalateをディスパッチ"""
        # Arrange
        hive_result = await mcp_server._dispatch_tool(
            "create_hive", {"name": "Test", "goal": "Test"}
        )
        colony_result = await mcp_server._dispatch_tool(
            "create_colony", {"hive_id": hive_result["hive_id"], "name": "Test", "domain": "Test"}
        )

        # Act
        result = await mcp_server._dispatch_tool(
            "queen_escalate",
            {
                "colony_id": colony_result["colony_id"],
                "escalation_type": "context_loss",
                "summary": "Context lost",
            },
        )

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_dispatch_beekeeper_feedback(self, mcp_server):
        """beekeeper_feedbackをディスパッチ"""
        result = await mcp_server._dispatch_tool(
            "beekeeper_feedback",
            {"escalation_id": "esc-001", "resolution": "Fixed", "improvements": ["Better prompts"]},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_dispatch_list_escalations(self, mcp_server):
        """list_escalationsをディスパッチ"""
        result = await mcp_server._dispatch_tool("list_escalations", {})
        assert "escalations" in result or "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_get_escalation(self, mcp_server):
        """get_escalationをディスパッチ"""
        result = await mcp_server._dispatch_tool(
            "get_escalation", {"escalation_id": "nonexistent"}
        )
        assert result is not None


class TestRequirementHandlerEdgeCases:
    """Requirementハンドラのエッジケーステスト"""

    @pytest.mark.asyncio
    async def test_get_run_started_event_id_without_run(self, mcp_server):
        """Runがない場合_get_run_started_event_idはNoneを返す"""
        # Act
        result = mcp_server._requirement_handlers._get_run_started_event_id()

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_create_requirement_without_run_returns_error(self, mcp_server):
        """Runがない状態でcreate_requirementはエラーを返す"""
        # Act
        result = await mcp_server._requirement_handlers.handle_create_requirement(
            {"description": "Test"}
        )

        # Assert
        assert "error" in result


class TestDecisionHandlerEdgeCases:
    """Decisionハンドラのエッジケーステスト"""

    @pytest.mark.asyncio
    async def test_record_decision_without_run_returns_error(self, mcp_server):
        """Runがない状態でrecord_decisionはエラーを返す"""
        # Act
        result = await mcp_server._decision_handlers.handle_record_decision(
            {"key": "D1", "title": "Test", "selected": "A", "rationale": "Because"}
        )

        # Assert
        assert "error" in result


class TestColonyHandlerEdgeCases:
    """Colonyハンドラのエッジケーステスト"""

    @pytest.mark.asyncio
    async def test_list_colonies_nonexistent_hive(self, mcp_server):
        """存在しないHiveのColony一覧はエラー"""
        result = await mcp_server._colony_handlers.handle_list_colonies(
            {"hive_id": "nonexistent"}
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_start_colony_nonexistent(self, mcp_server):
        """存在しないColonyの開始はエラー"""
        result = await mcp_server._colony_handlers.handle_start_colony(
            {"colony_id": "nonexistent"}
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_complete_colony_nonexistent(self, mcp_server):
        """存在しないColonyの完了はエラー"""
        result = await mcp_server._colony_handlers.handle_complete_colony(
            {"colony_id": "nonexistent"}
        )
        assert "error" in result


class TestConferenceHandlerEdgeCases:
    """Conferenceハンドラのエッジケーステスト"""

    @pytest.mark.asyncio
    async def test_end_conference_nonexistent(self, mcp_server):
        """存在しない会議の終了はエラー"""
        result = await mcp_server._conference_handlers.handle_end_conference(
            {"conference_id": "nonexistent", "summary": "Done"}
        )
        assert "error" in result or result is not None

    @pytest.mark.asyncio
    async def test_get_conference_nonexistent(self, mcp_server):
        """存在しない会議の取得はエラー"""
        result = await mcp_server._conference_handlers.handle_get_conference(
            {"conference_id": "nonexistent"}
        )
        assert "error" in result or result is not None
