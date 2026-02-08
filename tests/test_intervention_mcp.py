"""
Direct Intervention MCP テスト

ユーザー直接介入、Queen直訴、BeekeeperフィードバックのMCPテスト。
"""

import tempfile
from unittest.mock import MagicMock

import pytest

from hiveforge.core.intervention import InterventionStore
from hiveforge.mcp_server.handlers.intervention import InterventionHandlers


@pytest.fixture
def handlers():
    """テスト用InterventionHandlers（独立したストア付き）"""
    mock_server = MagicMock()
    store = InterventionStore(base_path=tempfile.mkdtemp())
    return InterventionHandlers(mock_server, store=store)


class TestUserInterveneMCP:
    """ユーザー直接介入MCPのテスト"""

    @pytest.mark.asyncio
    async def test_user_intervene(self, handlers: InterventionHandlers):
        """介入を作成できる

        Arrange: 有効なパラメータ
        Act: handle_user_intervene
        Assert: 介入情報が返る
        """
        # Arrange
        args = {
            "colony_id": "col-001",
            "instruction": "このアプローチで進めて",
            "reason": "緊急対応",
        }

        # Act
        result = await handlers.handle_user_intervene(args)

        # Assert
        assert "event_id" in result
        assert result["colony_id"] == "col-001"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_user_intervene_requires_colony_id(self, handlers: InterventionHandlers):
        """colony_idは必須

        Arrange: colony_idなし
        Act: handle_user_intervene
        Assert: エラー
        """
        # Act
        result = await handlers.handle_user_intervene({"instruction": "テスト"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_user_intervene_requires_instruction(self, handlers: InterventionHandlers):
        """instructionは必須

        Arrange: instructionなし
        Act: handle_user_intervene
        Assert: エラー
        """
        # Act
        result = await handlers.handle_user_intervene({"colony_id": "col-001"})

        # Assert
        assert "error" in result


class TestQueenEscalateMCP:
    """Queen直訴MCPのテスト"""

    @pytest.mark.asyncio
    async def test_queen_escalate(self, handlers: InterventionHandlers):
        """エスカレーションを作成できる

        Arrange: 有効なパラメータ
        Act: handle_queen_escalate
        Assert: エスカレーション情報が返る
        """
        # Arrange
        args = {
            "colony_id": "col-001",
            "escalation_type": "beekeeper_conflict",
            "summary": "設計方針の見解相違",
            "details": "詳細説明",
            "suggested_actions": ["案A", "案B"],
        }

        # Act
        result = await handlers.handle_queen_escalate(args)

        # Assert
        assert "event_id" in result
        assert result["colony_id"] == "col-001"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_queen_escalate_requires_colony_id(self, handlers: InterventionHandlers):
        """colony_idは必須

        Arrange: colony_idなし
        Act: handle_queen_escalate
        Assert: エラー
        """
        # Act
        result = await handlers.handle_queen_escalate(
            {
                "escalation_type": "technical_blocker",
                "summary": "テスト",
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_queen_escalate_requires_escalation_type(self, handlers: InterventionHandlers):
        """escalation_typeは必須

        Arrange: escalation_typeなし
        Act: handle_queen_escalate
        Assert: エラー
        """
        # Act
        result = await handlers.handle_queen_escalate(
            {
                "colony_id": "col-001",
                "summary": "テスト",
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_queen_escalate_invalid_type(self, handlers: InterventionHandlers):
        """無効なエスカレーションタイプはエラー

        Arrange: 無効なタイプ
        Act: handle_queen_escalate
        Assert: エラー
        """
        # Act
        result = await handlers.handle_queen_escalate(
            {
                "colony_id": "col-001",
                "escalation_type": "invalid_type",
                "summary": "テスト",
            }
        )

        # Assert
        assert "error" in result


class TestBeekeeperFeedbackMCP:
    """BeekeeperフィードバックMCPのテスト"""

    @pytest.mark.asyncio
    async def test_beekeeper_feedback(self, handlers: InterventionHandlers):
        """フィードバックを作成できる

        Arrange: エスカレーションを先に作成
        Act: handle_beekeeper_feedback
        Assert: フィードバック情報が返る
        """
        # Arrange
        esc_result = await handlers.handle_queen_escalate(
            {
                "colony_id": "col-001",
                "escalation_type": "beekeeper_conflict",
                "summary": "テスト問題",
            }
        )
        escalation_id = esc_result["event_id"]

        # Act
        result = await handlers.handle_beekeeper_feedback(
            {
                "escalation_id": escalation_id,
                "resolution": "案Aで解決",
                "beekeeper_adjustment": {"priority": "high"},
            }
        )

        # Assert
        assert "event_id" in result
        assert result["escalation_id"] == escalation_id
        assert "message" in result

    @pytest.mark.asyncio
    async def test_beekeeper_feedback_not_found(self, handlers: InterventionHandlers):
        """存在しないエスカレーションはエラー

        Arrange: 存在しないID
        Act: handle_beekeeper_feedback
        Assert: エラー
        """
        # Act
        result = await handlers.handle_beekeeper_feedback(
            {
                "escalation_id": "nonexistent",
                "resolution": "テスト",
            }
        )

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_beekeeper_feedback_requires_escalation_id(self, handlers: InterventionHandlers):
        """escalation_idは必須

        Arrange: escalation_idなし
        Act: handle_beekeeper_feedback
        Assert: エラー
        """
        # Act
        result = await handlers.handle_beekeeper_feedback({"resolution": "テスト"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_beekeeper_feedback_requires_resolution(self, handlers: InterventionHandlers):
        """resolutionは必須

        Arrange: resolutionなし
        Act: handle_beekeeper_feedback
        Assert: エラー
        """
        # Act
        result = await handlers.handle_beekeeper_feedback({"escalation_id": "evt-001"})

        # Assert
        assert "error" in result


class TestListEscalationsMCP:
    """エスカレーション一覧MCPのテスト"""

    @pytest.mark.asyncio
    async def test_list_escalations(self, handlers: InterventionHandlers):
        """エスカレーション一覧を取得できる

        Arrange: 複数のエスカレーション
        Act: handle_list_escalations
        Assert: 一覧が返る
        """
        # Arrange
        await handlers.handle_queen_escalate(
            {
                "colony_id": "col-001",
                "escalation_type": "technical_blocker",
                "summary": "問題A",
            }
        )
        await handlers.handle_queen_escalate(
            {
                "colony_id": "col-002",
                "escalation_type": "resource_shortage",
                "summary": "問題B",
            }
        )

        # Act
        result = await handlers.handle_list_escalations({})

        # Assert
        assert "escalations" in result
        assert result["count"] >= 2

    @pytest.mark.asyncio
    async def test_list_escalations_by_colony(self, handlers: InterventionHandlers):
        """Colony IDでフィルタできる

        Arrange: 異なるColonyのエスカレーション
        Act: handle_list_escalations with colony_id
        Assert: 指定Colonyのみ
        """
        # Arrange
        await handlers.handle_queen_escalate(
            {
                "colony_id": "col-filter-a",
                "escalation_type": "technical_blocker",
                "summary": "A",
            }
        )
        await handlers.handle_queen_escalate(
            {
                "colony_id": "col-filter-b",
                "escalation_type": "technical_blocker",
                "summary": "B",
            }
        )

        # Act
        result = await handlers.handle_list_escalations({"colony_id": "col-filter-a"})

        # Assert
        for esc in result["escalations"]:
            assert esc["colony_id"] == "col-filter-a"

    @pytest.mark.asyncio
    async def test_list_escalations_by_status(self, handlers: InterventionHandlers):
        """ステータスでフィルタできる

        Arrange: pendingとresolvedのエスカレーション
        Act: handle_list_escalations with status
        Assert: 指定ステータスのみ
        """
        # Arrange: pending
        await handlers.handle_queen_escalate(
            {
                "colony_id": "col-status",
                "escalation_type": "technical_blocker",
                "summary": "pending問題",
            }
        )

        # Act
        result = await handlers.handle_list_escalations({"status": "pending"})

        # Assert
        for esc in result["escalations"]:
            assert esc["status"] == "pending"


class TestGetEscalationMCP:
    """エスカレーション詳細MCPのテスト"""

    @pytest.mark.asyncio
    async def test_get_escalation(self, handlers: InterventionHandlers):
        """エスカレーション詳細を取得できる

        Arrange: エスカレーションを作成
        Act: handle_get_escalation
        Assert: 詳細が返る
        """
        # Arrange
        create_result = await handlers.handle_queen_escalate(
            {
                "colony_id": "col-get",
                "escalation_type": "priority_dispute",
                "summary": "優先順位問題",
            }
        )
        escalation_id = create_result["event_id"]

        # Act
        result = await handlers.handle_get_escalation({"escalation_id": escalation_id})

        # Assert
        assert result["event_id"] == escalation_id
        assert result["summary"] == "優先順位問題"

    @pytest.mark.asyncio
    async def test_get_escalation_not_found(self, handlers: InterventionHandlers):
        """存在しないエスカレーションはエラー

        Arrange: 存在しないID
        Act: handle_get_escalation
        Assert: エラー
        """
        # Act
        result = await handlers.handle_get_escalation({"escalation_id": "nonexistent"})

        # Assert
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_escalation_requires_id(self, handlers: InterventionHandlers):
        """escalation_idは必須

        Arrange: IDなし
        Act: handle_get_escalation
        Assert: エラー
        """
        # Act
        result = await handlers.handle_get_escalation({})

        # Assert
        assert "error" in result
