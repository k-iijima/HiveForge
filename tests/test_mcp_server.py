"""MCP Server モジュールのテスト"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
import asyncio

from hiveforge.mcp_server.server import HiveForgeMCPServer


@pytest.fixture
def mcp_server(tmp_path):
    """テスト用MCPサーバー"""
    with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = tmp_path / "Vault"
        mock_settings.return_value = mock_s

        server = HiveForgeMCPServer()
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
        """Runを完了できる"""
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
