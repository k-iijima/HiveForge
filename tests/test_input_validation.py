"""入力バリデーション強化テスト

M5-1b: MCPハンドラーとAPIエンドポイントの入力検証の強化。

MCPハンドラー:
- 空文字列の拒否（title, description, goal, key等の必須フィールド）
- 数値範囲の検証（progress: 0-100, max_depth: 1-100）
- 不正な列挙値の拒否（direction）

APIエンドポイント:
- クエリパラメータの上下限（limit, max_depth）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hiveforge.api.helpers import clear_active_runs, set_ar
from hiveforge.api.server import app
from hiveforge.core import AkashicRecord


# =============================================
# MCPハンドラー バリデーションテスト
# =============================================


@pytest.fixture
def mcp_server(tmp_path):
    """テスト用MCPサーバー（Runアクティブ状態）"""
    from hiveforge.mcp_server.server import HiveForgeMCPServer

    with patch("hiveforge.mcp_server.server.get_settings") as mock_settings:
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = tmp_path / "Vault"
        mock_settings.return_value = mock_s

        server = HiveForgeMCPServer()

        # ハンドラーへのショートカット
        server.run_handler = server._run_handlers
        server.task_handler = server._task_handlers
        server.decision_handler = server._decision_handlers
        server.requirement_handler = server._requirement_handlers
        server.lineage_handler = server._lineage_handlers

        yield server


async def _start_run(mcp_server) -> str:
    """テスト用: Runを開始して run_id を返す"""
    result = await mcp_server.run_handler.handle_start_run({"goal": "test goal"})
    return result["run_id"]


class TestMCPRunValidation:
    """MCP Run ハンドラーのバリデーションテスト"""

    @pytest.mark.asyncio
    async def test_start_run_empty_goal_rejected(self, mcp_server):
        """空のgoalは拒否される"""
        # Act
        result = await mcp_server.run_handler.handle_start_run({"goal": ""})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_start_run_whitespace_goal_rejected(self, mcp_server):
        """空白のみのgoalは拒否される"""
        # Act
        result = await mcp_server.run_handler.handle_start_run({"goal": "   "})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_start_run_missing_goal_rejected(self, mcp_server):
        """goalなしは拒否される"""
        # Act
        result = await mcp_server.run_handler.handle_start_run({})

        # Assert
        assert "error" in result


class TestMCPTaskValidation:
    """MCP Task ハンドラーのバリデーションテスト"""

    @pytest.mark.asyncio
    async def test_create_task_empty_title_rejected(self, mcp_server):
        """空のtitleは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.task_handler.handle_create_task({"title": ""})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_task_missing_title_rejected(self, mcp_server):
        """titleなしは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.task_handler.handle_create_task({})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_out_of_range_rejected(self, mcp_server):
        """0-100の範囲外のprogressは拒否される"""
        # Arrange
        await _start_run(mcp_server)
        task_result = await mcp_server.task_handler.handle_create_task({"title": "test task"})
        task_id = task_result["task_id"]

        # Act: 101は範囲外
        result = await mcp_server.task_handler.handle_report_progress(
            {"task_id": task_id, "progress": 101}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_negative_rejected(self, mcp_server):
        """負のprogressは拒否される"""
        # Arrange
        await _start_run(mcp_server)
        task_result = await mcp_server.task_handler.handle_create_task({"title": "test task"})
        task_id = task_result["task_id"]

        # Act
        result = await mcp_server.task_handler.handle_report_progress(
            {"task_id": task_id, "progress": -1}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_report_progress_valid_range(self, mcp_server):
        """0-100の範囲内のprogressは受け入れられる"""
        # Arrange
        await _start_run(mcp_server)
        task_result = await mcp_server.task_handler.handle_create_task({"title": "test task"})
        task_id = task_result["task_id"]

        # Act: 0, 50, 100 は有効
        for progress_val in [0, 50, 100]:
            result = await mcp_server.task_handler.handle_report_progress(
                {"task_id": task_id, "progress": progress_val}
            )

            # Assert
            assert "error" not in result


class TestMCPDecisionValidation:
    """MCP Decision ハンドラーのバリデーションテスト"""

    @pytest.mark.asyncio
    async def test_record_decision_empty_key_rejected(self, mcp_server):
        """空のkeyは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.decision_handler.handle_record_decision(
            {"key": "", "title": "test", "selected": "A"}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_record_decision_empty_title_rejected(self, mcp_server):
        """空のtitleは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.decision_handler.handle_record_decision(
            {"key": "D1", "title": "", "selected": "A"}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_record_decision_empty_selected_rejected(self, mcp_server):
        """空のselectedは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.decision_handler.handle_record_decision(
            {"key": "D1", "title": "test", "selected": ""}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_record_decision_missing_required_fields_rejected(self, mcp_server):
        """必須フィールド欠落は拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.decision_handler.handle_record_decision({})

        # Assert
        assert "error" in result


class TestMCPRequirementValidation:
    """MCP Requirement ハンドラーのバリデーションテスト"""

    @pytest.mark.asyncio
    async def test_create_requirement_empty_description_rejected(self, mcp_server):
        """空のdescriptionは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.requirement_handler.handle_create_requirement({"description": ""})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_requirement_missing_description_rejected(self, mcp_server):
        """descriptionなしは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.requirement_handler.handle_create_requirement({})

        # Assert
        assert "error" in result


class TestMCPLineageValidation:
    """MCP Lineage ハンドラーのバリデーションテスト"""

    @pytest.mark.asyncio
    async def test_lineage_invalid_direction_rejected(self, mcp_server):
        """不正なdirectionは拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.lineage_handler.handle_get_lineage(
            {"event_id": "test-id", "direction": "invalid"}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_lineage_max_depth_too_large_rejected(self, mcp_server):
        """max_depthが大きすぎる場合は拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.lineage_handler.handle_get_lineage(
            {"event_id": "test-id", "max_depth": 1000}
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_lineage_max_depth_zero_rejected(self, mcp_server):
        """max_depth=0は拒否される"""
        # Arrange
        await _start_run(mcp_server)

        # Act
        result = await mcp_server.lineage_handler.handle_get_lineage(
            {"event_id": "test-id", "max_depth": 0}
        )

        # Assert
        assert "error" in result


# =============================================
# API エンドポイント バリデーションテスト
# =============================================


@pytest.fixture
def api_client(tmp_path):
    """テスト用APIクライアント"""
    set_ar(None)
    clear_active_runs()

    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False
    mock_s.auth.enabled = False

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        patch("hiveforge.api.auth.get_settings", return_value=mock_s),
        TestClient(app) as client,
    ):
        yield client

    set_ar(None)
    clear_active_runs()


class TestAPIEventsValidation:
    """API Events エンドポイントのバリデーションテスト"""

    def test_events_limit_too_large(self, api_client):
        """limitが上限を超える場合は422"""
        # Arrange: Runを作成
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events?limit=10001")

        # Assert
        assert response.status_code == 422

    def test_events_limit_zero(self, api_client):
        """limit=0は422"""
        # Arrange
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events?limit=0")

        # Assert
        assert response.status_code == 422

    def test_events_limit_valid(self, api_client):
        """有効なlimitは200"""
        # Arrange
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events?limit=50")

        # Assert
        assert response.status_code == 200


class TestAPILineageValidation:
    """API Lineage エンドポイントのバリデーションテスト"""

    def test_lineage_invalid_direction(self, api_client):
        """不正なdirectionは422"""
        # Arrange
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events/fake-id/lineage?direction=invalid")

        # Assert
        assert response.status_code == 422

    def test_lineage_max_depth_too_large(self, api_client):
        """max_depthが上限を超える場合は422"""
        # Arrange
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events/fake-id/lineage?max_depth=1000")

        # Assert
        assert response.status_code == 422

    def test_lineage_max_depth_zero(self, api_client):
        """max_depth=0は422"""
        # Arrange
        response = api_client.post("/runs", json={"goal": "test"})
        run_id = response.json()["run_id"]

        # Act
        response = api_client.get(f"/runs/{run_id}/events/fake-id/lineage?max_depth=0")

        # Assert
        assert response.status_code == 422
