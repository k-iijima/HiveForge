"""MCP ハンドラー未カバーパステスト

カバレッジギャップを埋める:
- handlers/conference.py: topic 未指定、conference_id未指定、already ended、active_only
- handlers/colony.py: colony_id未指定、colony未発見
- handlers/github.py: 汎用Exception re-raise
- handlers/requirement.py: description空文字列、_get_run_started_event_id の None パス
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from colonyforge.core import AkashicRecord
from colonyforge.core.state.conference import ConferenceProjection, ConferenceState, ConferenceStore
from colonyforge.mcp_server.handlers.colony import ColonyHandlers
from colonyforge.mcp_server.handlers.conference import ConferenceHandlers
from colonyforge.mcp_server.handlers.github import GitHubHandlers
from colonyforge.mcp_server.handlers.requirement import RequirementHandlers

# =========================================================================
# Conference ハンドラーの未カバーパス
# =========================================================================


@pytest.fixture
def conf_ar(tmp_path):
    return AkashicRecord(tmp_path)


@pytest.fixture
def conf_store():
    return ConferenceStore()


@pytest.fixture
def conf_handlers(conf_ar, conf_store):
    mock_server = MagicMock()
    mock_server._get_ar.return_value = conf_ar
    return ConferenceHandlers(mock_server, conf_store)


class TestConferenceHandlersGaps:
    """Conference ハンドラーの未カバーブランチ"""

    @pytest.mark.asyncio
    async def test_start_conference_missing_topic(self, conf_handlers: ConferenceHandlers):
        """topic が未指定の場合エラーを返す"""
        # Act
        result = await conf_handlers.handle_start_conference({"hive_id": "h1"})

        # Assert
        assert "error" in result
        assert "topic" in result["error"]

    @pytest.mark.asyncio
    async def test_end_conference_missing_conference_id(self, conf_handlers: ConferenceHandlers):
        """conference_id が未指定の場合エラーを返す"""
        # Act
        result = await conf_handlers.handle_end_conference({})

        # Assert
        assert "error" in result
        assert "conference_id" in result["error"]

    @pytest.mark.asyncio
    async def test_end_conference_not_found(self, conf_handlers: ConferenceHandlers):
        """存在しない conference_id でエラーを返す"""
        # Act
        result = await conf_handlers.handle_end_conference({"conference_id": "nonexistent"})

        # Assert
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_end_conference_already_ended(
        self, conf_handlers: ConferenceHandlers, conf_store: ConferenceStore
    ):
        """既に終了した会議を再終了しようとするとエラーを返す"""
        # Arrange: 終了済みの会議を追加
        projection = ConferenceProjection(
            conference_id="conf-ended",
            hive_id="hive-1",
            topic="終了済み会議",
            participants=[],
            initiated_by="user",
            state=ConferenceState.ENDED,
        )
        conf_store.add(projection)

        # Act
        result = await conf_handlers.handle_end_conference({"conference_id": "conf-ended"})

        # Assert
        assert "error" in result
        assert "already ended" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_end_conference_without_started_at(
        self, conf_handlers: ConferenceHandlers, conf_store: ConferenceStore, conf_ar
    ):
        """started_at が None の会議を終了すると duration_seconds=0 になる"""
        # Arrange: started_at=None の会議
        projection = ConferenceProjection(
            conference_id="conf-no-start",
            hive_id="hive-1",
            topic="開始時刻なし会議",
            participants=[],
            initiated_by="user",
            state=ConferenceState.ACTIVE,
            started_at=None,
        )
        conf_store.add(projection)

        # Act
        result = await conf_handlers.handle_end_conference({"conference_id": "conf-no-start"})

        # Assert
        assert result["duration_seconds"] == 0

    @pytest.mark.asyncio
    async def test_list_conferences_active_only(
        self, conf_handlers: ConferenceHandlers, conf_store: ConferenceStore
    ):
        """active_only=True でアクティブな会議のみ返す"""
        # Arrange
        active_conf = ConferenceProjection(
            conference_id="conf-active",
            hive_id="hive-1",
            topic="アクティブ会議",
            participants=[],
            initiated_by="user",
            state=ConferenceState.ACTIVE,
        )
        ended_conf = ConferenceProjection(
            conference_id="conf-done",
            hive_id="hive-1",
            topic="終了会議",
            participants=[],
            initiated_by="user",
            state=ConferenceState.ENDED,
        )
        conf_store.add(active_conf)
        conf_store.add(ended_conf)

        # Act
        result = await conf_handlers.handle_list_conferences({"active_only": True})

        # Assert
        ids = [c["conference_id"] for c in result["conferences"]]
        assert "conf-active" in ids
        assert "conf-done" not in ids

    @pytest.mark.asyncio
    async def test_get_conference_missing_id(self, conf_handlers: ConferenceHandlers):
        """conference_id が未指定の場合エラーを返す"""
        # Act
        result = await conf_handlers.handle_get_conference({})

        # Assert
        assert "error" in result
        assert "conference_id" in result["error"]

    @pytest.mark.asyncio
    async def test_get_conference_not_found(self, conf_handlers: ConferenceHandlers):
        """存在しない conference_id でエラーを返す"""
        # Act
        result = await conf_handlers.handle_get_conference({"conference_id": "missing"})

        # Assert
        assert "error" in result
        assert "not found" in result["error"].lower()


# =========================================================================
# Colony ハンドラーの未カバーパス
# =========================================================================


class TestColonyHandlersGaps:
    """Colony ハンドラーの未カバーブランチ"""

    @pytest.fixture
    def colony_handlers(self, tmp_path):
        mock_server = MagicMock()
        mock_server._get_ar.return_value = AkashicRecord(tmp_path)

        from colonyforge.core.ar.hive_storage import HiveStore

        store = HiveStore(tmp_path / "hives")
        mock_server._get_hive_store.return_value = store

        handler = ColonyHandlers(mock_server)
        return handler

    @pytest.mark.asyncio
    async def test_start_colony_missing_colony_id(self, colony_handlers: ColonyHandlers):
        """colony_id が空の場合エラーを返す"""
        # Act
        result = await colony_handlers.handle_start_colony({})

        # Assert
        assert "error" in result
        assert "colony_id" in result["error"]

    @pytest.mark.asyncio
    async def test_start_colony_not_found(self, colony_handlers: ColonyHandlers):
        """存在しない colony_id でエラーを返す"""
        # Act
        result = await colony_handlers.handle_start_colony({"colony_id": "nonexistent"})

        # Assert
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_complete_colony_missing_colony_id(self, colony_handlers: ColonyHandlers):
        """colony_id が空の場合エラーを返す"""
        # Act
        result = await colony_handlers.handle_complete_colony({})

        # Assert
        assert "error" in result
        assert "colony_id" in result["error"]

    @pytest.mark.asyncio
    async def test_complete_colony_not_found(self, colony_handlers: ColonyHandlers):
        """存在しない colony_id でエラーを返す"""
        # Act
        result = await colony_handlers.handle_complete_colony({"colony_id": "nonexistent"})

        # Assert
        assert "error" in result
        assert "not found" in result["error"].lower()


# =========================================================================
# GitHub ハンドラーの未カバーパス
# =========================================================================


class TestGitHubHandlersGaps:
    """GitHub ハンドラーの未カバーブランチ"""

    @pytest.fixture
    def gh_handler(self):
        mock_server = MagicMock()
        mock_server._current_run_id = "run-active"
        return GitHubHandlers(mock_server)

    @pytest.mark.asyncio
    async def test_sync_generic_exception_raises_runtime_error(self, gh_handler: GitHubHandlers):
        """batch_apply で予期しない例外が発生した場合 RuntimeError に変換して re-raise"""
        # Arrange
        mock_ar = MagicMock()
        from colonyforge.core.events.base import BaseEvent
        from colonyforge.core.events.types import EventType

        events = [BaseEvent(type=EventType.RUN_STARTED, run_id="run-1", payload={"goal": "test"})]
        mock_ar.replay.return_value = iter(events)
        gh_handler._server._get_ar = MagicMock(return_value=mock_ar)

        mock_projection = MagicMock()
        mock_projection.batch_apply = AsyncMock(side_effect=ValueError("unexpected"))
        gh_handler._projection = mock_projection

        # Act & Assert
        with pytest.raises(RuntimeError, match="GitHub sync failed"):
            await gh_handler.handle_sync_run_to_github({"run_id": "run-1"})


# =========================================================================
# Requirement ハンドラーの未カバーパス
# =========================================================================


class TestRequirementHandlersGaps:
    """Requirement ハンドラーの未カバーブランチ"""

    @pytest.fixture
    def req_handler(self, tmp_path):
        mock_server = MagicMock()
        mock_server._current_run_id = None
        mock_server._get_ar.return_value = AkashicRecord(tmp_path)
        return RequirementHandlers(mock_server)

    @pytest.mark.asyncio
    async def test_get_run_started_event_id_no_active_run(self, req_handler: RequirementHandlers):
        """アクティブな run がない場合 None を返す"""
        # Act
        result = req_handler._get_run_started_event_id()

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_create_requirement_empty_description(self, req_handler: RequirementHandlers):
        """description が空文字列の場合エラーを返す"""
        # Arrange: run_id を設定
        req_handler._server._current_run_id = "run-1"

        # Act
        result = await req_handler.handle_create_requirement({"description": "   "})

        # Assert
        assert "error" in result
        assert "description" in result["error"]

    @pytest.mark.asyncio
    async def test_get_run_started_event_id_no_matching_event(
        self, req_handler: RequirementHandlers, tmp_path
    ):
        """run_id はあるが RUN_STARTED イベントがない場合 None を返す"""
        # Arrange
        req_handler._server._current_run_id = "run-no-start"

        # Act
        result = req_handler._get_run_started_event_id()

        # Assert
        assert result is None
