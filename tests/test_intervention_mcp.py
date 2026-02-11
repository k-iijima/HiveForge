"""
Direct Intervention MCP テスト

ユーザー直接介入、Queen直訴、BeekeeperフィードバックのMCPテスト。
"""

import tempfile
from unittest.mock import MagicMock

import pytest

from colonyforge.core import AkashicRecord
from colonyforge.core.intervention import InterventionStore
from colonyforge.mcp_server.handlers.intervention import InterventionHandlers


@pytest.fixture
def handlers():
    """テスト用InterventionHandlers（独立したストア付き）"""
    mock_server = MagicMock()
    store = InterventionStore(base_path=tempfile.mkdtemp())
    return InterventionHandlers(mock_server, store=store)


@pytest.fixture
def handlers_with_ar(tmp_path):
    """AR永続化検証用のInterventionHandlers"""
    ar = AkashicRecord(vault_path=tmp_path)
    mock_server = MagicMock()
    mock_server._get_ar.return_value = ar
    store = InterventionStore(base_path=tmp_path)
    return InterventionHandlers(mock_server, store=store), ar


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


class TestInterventionARPersistence:
    """Intervention系イベントのAR永続化テスト

    全てのInterventionイベントがAkashic Recordに永続化され、
    replay() で復元可能であることを検証する。
    """

    @pytest.mark.asyncio
    async def test_user_intervene_persists_to_ar(self, handlers_with_ar):
        """ユーザー直接介入イベントがARに永続化される

        InterventionStoreだけでなく、ARのイベントチェーンにも
        記録されることで因果リンクの構築が可能になる。
        """
        # Arrange
        handlers, ar = handlers_with_ar

        # Act: 介入を作成
        result = await handlers.handle_user_intervene(
            {
                "colony_id": "col-001",
                "instruction": "このアプローチで進めて",
                "reason": "緊急対応",
            }
        )

        # Assert: ARにイベントが永続化されている
        event_id = result["event_id"]
        stream_key = "intervention-col-001"
        events = list(ar.replay(stream_key))
        assert len(events) == 1
        assert events[0].id == event_id
        assert events[0].type.value == "intervention.user_direct"
        assert events[0].payload["colony_id"] == "col-001"
        assert events[0].payload["instruction"] == "このアプローチで進めて"

    @pytest.mark.asyncio
    async def test_queen_escalate_persists_to_ar(self, handlers_with_ar):
        """Queen直訴イベントがARに永続化される

        エスカレーションイベントがARに記録されることで、
        後から問題の因果関係を追跡できる。
        """
        # Arrange
        handlers, ar = handlers_with_ar

        # Act: エスカレーションを作成
        result = await handlers.handle_queen_escalate(
            {
                "colony_id": "col-002",
                "escalation_type": "resource_shortage",
                "summary": "リソース不足",
                "details": "Worker数が足りない",
            }
        )

        # Assert: ARにイベントが永続化されている
        event_id = result["event_id"]
        stream_key = "intervention-col-002"
        events = list(ar.replay(stream_key))
        assert len(events) == 1
        assert events[0].id == event_id
        assert events[0].type.value == "intervention.queen_escalation"
        assert events[0].payload["escalation_type"] == "resource_shortage"
        assert events[0].payload["summary"] == "リソース不足"

    @pytest.mark.asyncio
    async def test_beekeeper_feedback_persists_to_ar(self, handlers_with_ar):
        """BeekeeperフィードバックイベントがARに永続化される

        フィードバックがARに記録されることで、
        介入→フィードバックの因果チェーンが構築される。
        """
        # Arrange: 先に介入を作成（フィードバックの対象として必要）
        handlers, ar = handlers_with_ar

        intervene_result = await handlers.handle_user_intervene(
            {
                "colony_id": "col-003",
                "instruction": "テスト介入",
            }
        )
        escalation_id = intervene_result["event_id"]

        # Act: フィードバックを作成
        result = await handlers.handle_beekeeper_feedback(
            {
                "escalation_id": escalation_id,
                "resolution": "対応完了",
                "lesson_learned": "早期介入が効果的",
            }
        )

        # Assert: ARにフィードバックイベントが永続化されている
        feedback_event_id = result["event_id"]
        stream_key = "intervention-col-003"
        events = list(ar.replay(stream_key))
        # 介入 + フィードバック の2イベント
        assert len(events) >= 2
        feedback_events = [e for e in events if e.id == feedback_event_id]
        assert len(feedback_events) == 1
        assert feedback_events[0].type.value == "intervention.beekeeper_feedback"
        assert feedback_events[0].payload["resolution"] == "対応完了"
