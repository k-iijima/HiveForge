"""GitHub MCP ハンドラーテスト

sync_run_to_github / get_github_sync_status の MCP ツールテスト。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.core.config import GitHubConfig
from hiveforge.core.events.base import BaseEvent
from hiveforge.core.events.types import EventType
from hiveforge.mcp_server.handlers.github import GitHubHandlers

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_server() -> MagicMock:
    """モック HiveForgeMCPServer"""
    server = MagicMock()
    server._current_run_id = "01HACTIVE_RUN"
    return server


@pytest.fixture
def handler(mock_server: MagicMock) -> GitHubHandlers:
    """テスト用 GitHubHandlers"""
    return GitHubHandlers(mock_server)


def _make_test_events(run_id: str = "01HTEST") -> list[BaseEvent]:
    """テスト用イベントリスト"""
    return [
        BaseEvent(type=EventType.RUN_STARTED, run_id=run_id, payload={"goal": "test"}),
        BaseEvent(
            type=EventType.TASK_COMPLETED, run_id=run_id, task_id="T1", payload={"result": "done"}
        ),
        BaseEvent(type=EventType.RUN_COMPLETED, run_id=run_id, payload={"summary": "all done"}),
    ]


# ---------------------------------------------------------------------------
# sync_run_to_github
# ---------------------------------------------------------------------------


class TestSyncRunToGitHub:
    """sync_run_to_github ハンドラーテスト"""

    @pytest.mark.asyncio
    async def test_sync_success(self, handler: GitHubHandlers) -> None:
        """正常にRunをGitHubに同期できること

        ARからイベントを replay し、GitHubProjection で射影する。
        """
        # Arrange
        events = _make_test_events("01HTEST")
        mock_ar = MagicMock()
        mock_ar.replay.return_value = iter(events)
        handler._server._get_ar = MagicMock(return_value=mock_ar)

        mock_projection = MagicMock()
        mock_projection.batch_apply = AsyncMock()
        mock_projection.get_issue_number.return_value = 42
        mock_projection.sync_state.last_synced_event_id = events[-1].id
        mock_projection.sync_state.synced_event_ids = {e.id for e in events}
        handler._projection = mock_projection

        # Act
        result = await handler.handle_sync_run_to_github({"run_id": "01HTEST"})

        # Assert
        assert result["status"] == "synced"
        assert result["events_processed"] == 3
        assert result["issue_number"] == 42
        mock_projection.batch_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_uses_current_run_if_no_run_id(self, handler: GitHubHandlers) -> None:
        """run_id 省略時に現在のRun IDを使用すること"""
        # Arrange
        events = _make_test_events("01HACTIVE_RUN")
        mock_ar = MagicMock()
        mock_ar.replay.return_value = iter(events)
        handler._server._get_ar = MagicMock(return_value=mock_ar)

        mock_projection = MagicMock()
        mock_projection.batch_apply = AsyncMock()
        mock_projection.get_issue_number.return_value = 10
        mock_projection.sync_state.last_synced_event_id = events[-1].id
        mock_projection.sync_state.synced_event_ids = {e.id for e in events}
        handler._projection = mock_projection

        # Act
        result = await handler.handle_sync_run_to_github({})

        # Assert
        assert result["status"] == "synced"
        mock_ar.replay.assert_called_once_with("01HACTIVE_RUN")

    @pytest.mark.asyncio
    async def test_sync_no_run_id_and_no_active_run(
        self, handler: GitHubHandlers, mock_server: MagicMock
    ) -> None:
        """run_id もアクティブRunもない場合エラーを返すこと"""
        # Arrange
        mock_server._current_run_id = None

        # Act
        result = await handler.handle_sync_run_to_github({})

        # Assert
        assert "error" in result
        assert "run_id" in result["error"]

    @pytest.mark.asyncio
    async def test_sync_no_events(self, handler: GitHubHandlers) -> None:
        """イベントが0件の場合 no_events を返すこと"""
        # Arrange
        mock_ar = MagicMock()
        mock_ar.replay.return_value = iter([])
        handler._server._get_ar = MagicMock(return_value=mock_ar)

        mock_projection = MagicMock()
        handler._projection = mock_projection

        # Act
        result = await handler.handle_sync_run_to_github({"run_id": "01HEMPTY"})

        # Assert
        assert result["status"] == "no_events"

    @pytest.mark.asyncio
    async def test_sync_github_disabled(self, handler: GitHubHandlers) -> None:
        """GitHub Projection が無効の場合エラーを返すこと"""
        # Arrange: _projection を None にして _get_projection でエラー発生
        handler._projection = None

        with patch.object(
            handler,
            "_get_github_config",
            return_value=GitHubConfig(enabled=False),
        ):
            # Act
            result = await handler.handle_sync_run_to_github({"run_id": "01HTEST"})

        # Assert
        assert "error" in result
        assert "not enabled" in result["error"]


# ---------------------------------------------------------------------------
# get_github_sync_status
# ---------------------------------------------------------------------------


class TestGetGitHubSyncStatus:
    """get_github_sync_status ハンドラーテスト"""

    @pytest.mark.asyncio
    async def test_status_with_active_projection(self, handler: GitHubHandlers) -> None:
        """同期状態を正しく返すこと"""
        # Arrange
        mock_projection = MagicMock()
        mock_projection.sync_state.last_synced_event_id = "EV-003"
        mock_projection.sync_state.synced_event_ids = {"EV-001", "EV-002", "EV-003"}
        mock_projection.sync_state.run_issue_map = {"RUN-1": 42}
        handler._projection = mock_projection

        # Act
        result = await handler.handle_get_github_sync_status({})

        # Assert
        assert result["status"] == "ok"
        assert result["enabled"] is True
        assert result["total_synced"] == 3
        assert result["run_issue_map"] == {"RUN-1": 42}

    @pytest.mark.asyncio
    async def test_status_when_disabled(self, handler: GitHubHandlers) -> None:
        """GitHub Projection 無効時にエラーを返すこと"""
        # Arrange
        handler._projection = None

        with patch.object(
            handler,
            "_get_github_config",
            return_value=GitHubConfig(enabled=False),
        ):
            # Act
            result = await handler.handle_get_github_sync_status({})

        # Assert
        assert "error" in result
        assert result["enabled"] is False
