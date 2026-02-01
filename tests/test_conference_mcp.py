"""
Conference MCP テスト

Conference MCPハンドラーのテスト。
"""

from unittest.mock import MagicMock

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.state.conference import ConferenceStore
from hiveforge.mcp_server.handlers.conference import ConferenceHandlers


@pytest.fixture
def ar(tmp_path):
    """テスト用Akashic Record"""
    return AkashicRecord(tmp_path)


@pytest.fixture
def store():
    """テスト用ConferenceStore"""
    return ConferenceStore()


@pytest.fixture
def handlers(ar, store):
    """テスト用ConferenceHandlers"""
    # モックサーバーを作成
    mock_server = MagicMock()
    mock_server._get_ar.return_value = ar
    return ConferenceHandlers(mock_server, store)


class TestConferenceMCP:
    """Conference MCPハンドラーのテスト"""

    @pytest.mark.asyncio
    async def test_start_conference(self, handlers: ConferenceHandlers):
        """会議を開始できる

        Arrange: 有効なパラメータ
        Act: handle_start_conference
        Assert: 会議が作成される
        """
        # Arrange
        args = {
            "hive_id": "hive-001",
            "topic": "設計会議",
            "participants": ["ui-colony", "api-colony"],
        }

        # Act
        result = await handlers.handle_start_conference(args)

        # Assert
        assert "conference_id" in result
        assert result["hive_id"] == "hive-001"
        assert result["topic"] == "設計会議"
        assert result["state"] == "active"

    @pytest.mark.asyncio
    async def test_start_conference_requires_hive_id(self, handlers: ConferenceHandlers):
        """hive_idは必須

        Arrange: hive_idなし
        Act: handle_start_conference
        Assert: エラー
        """
        # Act
        result = await handlers.handle_start_conference({"topic": "テスト"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_start_conference_requires_topic(self, handlers: ConferenceHandlers):
        """topicは必須

        Arrange: topicなし
        Act: handle_start_conference
        Assert: エラー
        """
        # Act
        result = await handlers.handle_start_conference({"hive_id": "hive-001"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_end_conference(self, handlers: ConferenceHandlers):
        """会議を終了できる

        Arrange: アクティブな会議
        Act: handle_end_conference
        Assert: 会議が終了する
        """
        # Arrange
        start_result = await handlers.handle_start_conference(
            {
                "hive_id": "hive-001",
                "topic": "終了テスト",
            }
        )
        conference_id = start_result["conference_id"]

        # Act
        result = await handlers.handle_end_conference(
            {
                "conference_id": conference_id,
                "summary": "決定まとめ",
            }
        )

        # Assert
        assert result["state"] == "ended"
        assert result["summary"] == "決定まとめ"

    @pytest.mark.asyncio
    async def test_end_conference_not_found(self, handlers: ConferenceHandlers):
        """存在しない会議の終了はエラー

        Arrange: 存在しないID
        Act: handle_end_conference
        Assert: エラー
        """
        # Act
        result = await handlers.handle_end_conference({"conference_id": "nonexistent"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_conferences(self, handlers: ConferenceHandlers):
        """会議一覧を取得できる

        Arrange: 複数の会議
        Act: handle_list_conferences
        Assert: 全会議が取得される
        """
        # Arrange
        for topic in ["会議A", "会議B"]:
            await handlers.handle_start_conference(
                {
                    "hive_id": "hive-001",
                    "topic": topic,
                }
            )

        # Act
        result = await handlers.handle_list_conferences({})

        # Assert
        assert result["count"] == 2
        assert len(result["conferences"]) == 2

    @pytest.mark.asyncio
    async def test_list_conferences_by_hive(self, handlers: ConferenceHandlers):
        """Hive IDでフィルタできる

        Arrange: 異なるHiveの会議
        Act: handle_list_conferences with hive_id
        Assert: 指定Hiveの会議のみ
        """
        # Arrange
        await handlers.handle_start_conference({"hive_id": "hive-001", "topic": "A"})
        await handlers.handle_start_conference({"hive_id": "hive-002", "topic": "B"})

        # Act
        result = await handlers.handle_list_conferences({"hive_id": "hive-001"})

        # Assert
        assert result["count"] == 1
        assert result["conferences"][0]["hive_id"] == "hive-001"

    @pytest.mark.asyncio
    async def test_get_conference(self, handlers: ConferenceHandlers):
        """会議詳細を取得できる

        Arrange: 会議を作成
        Act: handle_get_conference
        Assert: 詳細が取得される
        """
        # Arrange
        start_result = await handlers.handle_start_conference(
            {
                "hive_id": "hive-001",
                "topic": "詳細テスト",
            }
        )
        conference_id = start_result["conference_id"]

        # Act
        result = await handlers.handle_get_conference({"conference_id": conference_id})

        # Assert
        assert result["conference_id"] == conference_id
        assert result["topic"] == "詳細テスト"

    @pytest.mark.asyncio
    async def test_get_conference_not_found(self, handlers: ConferenceHandlers):
        """存在しない会議の取得はエラー

        Arrange: 存在しないID
        Act: handle_get_conference
        Assert: エラー
        """
        # Act
        result = await handlers.handle_get_conference({"conference_id": "nonexistent"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_active_only(self, handlers: ConferenceHandlers):
        """アクティブな会議のみ取得できる

        Arrange: アクティブと終了済みの会議
        Act: handle_list_conferences with active_only
        Assert: アクティブのみ
        """
        # Arrange
        active = await handlers.handle_start_conference(
            {
                "hive_id": "hive-001",
                "topic": "アクティブ",
            }
        )
        ended = await handlers.handle_start_conference(
            {
                "hive_id": "hive-001",
                "topic": "終了済み",
            }
        )
        await handlers.handle_end_conference({"conference_id": ended["conference_id"]})

        # Act
        result = await handlers.handle_list_conferences({"active_only": True})

        # Assert
        assert result["count"] == 1
        assert result["conferences"][0]["conference_id"] == active["conference_id"]
