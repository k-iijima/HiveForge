"""Beekeeper Send Message → LLM → ツール呼び出しチェーンのE2Eテスト

send_message → run_with_llm → AgentRunner.run() → LLMClient.chat()
の統合フローをモックLLMで検証する。

CLI `colonyforge chat "..."` の裏で動くパイプライン全体の正当性を担保する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from colonyforge.beekeeper import BeekeeperMCPServer
from colonyforge.core import AkashicRecord
from colonyforge.llm.client import LLMResponse, ToolCall


@pytest.fixture
def ar(tmp_path):
    return AkashicRecord(vault_path=tmp_path)


def _make_text_response(content: str) -> LLMResponse:
    """ツール呼び出しなしのテキスト応答を生成"""
    return LLMResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )


def _make_tool_call_response(
    tool_name: str,
    arguments: dict,
    call_id: str = "call_001",
) -> LLMResponse:
    """ツール呼び出しを含むLLM応答を生成"""
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=tool_name, arguments=arguments)],
        finish_reason="tool_calls",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )


def _inject_mock_llm(beekeeper: BeekeeperMCPServer, responses: list[LLMResponse]):
    """モックLLMClientをBeekeeperに注入する

    AgentRunner → LLMClient.chat() が呼ばれるたびに
    responses リストから順番に返す。
    """
    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=responses)
    mock_client.close = AsyncMock()
    beekeeper._llm_client = mock_client
    return mock_client


class TestChatChainSimple:
    """send_message → run_with_llm の基本フロー"""

    @pytest.mark.asyncio
    async def test_simple_text_response(self, ar):
        """LLMがツール呼び出しなしでテキストを返す場合

        最もシンプルなパス: message → LLM → テキスト応答 → 結果返却。
        ツール呼び出しループに入らず1回のchatで完了する。
        """
        # Arrange: モックLLMを注入（テキスト応答のみ）
        beekeeper = BeekeeperMCPServer(ar=ar)
        mock_client = _inject_mock_llm(
            beekeeper,
            [
                _make_text_response("こんにちは！お手伝いします。"),
            ],
        )

        # Act: send_messageを呼ぶ
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "こんにちは",
                "context": {"working_directory": "/tmp"},
            },
        )

        # Assert: 成功レスポンスが返る
        assert result["status"] == "success"
        assert result["response"] == "こんにちは！お手伝いします。"
        assert result["actions_taken"] == 0
        assert "session_id" in result

        # LLMは1回だけ呼ばれた
        assert mock_client.chat.call_count == 1

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_session_created_on_first_message(self, ar):
        """初回メッセージでセッションが作成される

        send_message時にcurrent_sessionがなければ自動作成される。
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)
        _inject_mock_llm(
            beekeeper,
            [
                _make_text_response("OK"),
            ],
        )
        assert beekeeper.current_session is None

        # Act
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "test",
            },
        )

        # Assert: セッションが作成された
        assert result["status"] == "success"
        assert beekeeper.current_session is not None
        assert result["session_id"] == beekeeper.current_session.session_id

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_llm_error_returns_error_status(self, ar):
        """LLMClient.chat()が例外を投げた場合エラーが返る

        APIキー不正やネットワーク障害等を想定。
        セッションはactive状態に戻る。
        """
        # Arrange: chatが例外を投げるモック
        beekeeper = BeekeeperMCPServer(ar=ar)
        mock_client = MagicMock()
        mock_client.chat = AsyncMock(side_effect=RuntimeError("API key invalid"))
        mock_client.close = AsyncMock()
        beekeeper._llm_client = mock_client

        # Act
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "test",
            },
        )

        # Assert: エラーが返るがクラッシュしない
        assert result["status"] == "error"
        assert "API key invalid" in result["error"]

        await beekeeper.close()


class TestChatChainWithToolCalls:
    """LLMがツール呼び出しを返すケースの統合テスト"""

    @pytest.mark.asyncio
    async def test_create_hive_via_llm(self, ar):
        """LLMがcreate_hiveツールを呼び出してHiveを作成する

        LLM応答1: create_hiveツール呼び出し
        LLM応答2: ツール結果を受けてテキスト応答
        """
        # Arrange: LLMが create_hive を呼んでから結果をまとめる
        beekeeper = BeekeeperMCPServer(ar=ar)
        _inject_mock_llm(
            beekeeper,
            [
                _make_tool_call_response(
                    "create_hive",
                    {
                        "name": "EC Site",
                        "goal": "ECサイトを構築",
                    },
                ),
                _make_text_response("Hive 'EC Site' を作成しました！"),
            ],
        )

        # Act
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "ECサイトのプロジェクトを始めたい",
            },
        )

        # Assert: create_hiveが実行されHiveが作成された
        assert result["status"] == "success"
        assert result["response"] == "Hive 'EC Site' を作成しました！"
        assert result["actions_taken"] == 1  # 1回のツール呼び出し

        # Hive が HiveStore に永続化されている
        assert beekeeper.hive_store is not None
        hives = beekeeper.hive_store.list_hives()
        assert len(hives) >= 1  # Hive作成イベント

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_list_hives_via_llm(self, ar):
        """LLMがlist_hivesツールを呼び出してHive一覧を取得する

        事前にHiveを直接作成しておき、LLMがlist_hivesで一覧取得。
        """
        # Arrange: Hiveを事前作成
        beekeeper = BeekeeperMCPServer(ar=ar)

        await beekeeper.dispatch_tool(
            "create_hive",
            {
                "name": "Test Hive",
                "goal": "Testing",
            },
        )

        _inject_mock_llm(
            beekeeper,
            [
                _make_tool_call_response("list_hives", {}),
                _make_text_response("現在1つのHiveがあります: Test Hive"),
            ],
        )

        # Act
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "Hive一覧を見せて",
            },
        )

        # Assert
        assert result["status"] == "success"
        assert "Test Hive" in result["response"]
        assert result["actions_taken"] == 1

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(self, ar):
        """LLMが複数のツールを順次呼び出す

        LLM応答1: create_hive
        LLM応答2: get_hive_status
        LLM応答3: テキスト応答（まとめ）
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)
        _inject_mock_llm(
            beekeeper,
            [
                _make_tool_call_response(
                    "create_hive",
                    {
                        "name": "Multi Tool Test",
                        "goal": "複数ツールテスト",
                    },
                    call_id="call_001",
                ),
                _make_tool_call_response("list_hives", {}, call_id="call_002"),
                _make_text_response("Hiveを作成し、一覧を確認しました。"),
            ],
        )

        # Act
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "新しいHiveを作って一覧を確認して",
            },
        )

        # Assert: 2回のツール呼び出し
        assert result["status"] == "success"
        assert result["actions_taken"] == 2

        await beekeeper.close()


class TestChatChainWithDelegation:
    """LLMがQueen Beeへタスク委譲するケースのテスト"""

    @pytest.mark.asyncio
    async def test_delegate_to_queen_via_llm(self, ar):
        """LLMがdelegate_to_queenを呼び出してQueen Beeにタスクを委譲する

        LLM応答1: create_hive → Hive作成
        LLM応答2: create_colony → Colony作成
        LLM応答3: delegate_to_queen → Queen Beeに委譲
        LLM応答4: テキスト応答（結果まとめ）

        Queen Beeの内部LLMもモックして、ツール実行なしで完了応答を返す。
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)

        # Hive/Colony を事前作成（LLMループ外）
        hive_result = await beekeeper.dispatch_tool(
            "create_hive",
            {
                "name": "Login Project",
                "goal": "ログインページを作成",
            },
        )
        hive_id = hive_result["hive_id"]

        colony_result = await beekeeper.dispatch_tool(
            "create_colony",
            {
                "hive_id": hive_id,
                "name": "Frontend Colony",
                "domain": "frontend",
            },
        )
        colony_id = colony_result["colony_id"]

        # LLMモック: delegate_to_queen → テキスト応答
        _inject_mock_llm(
            beekeeper,
            [
                _make_tool_call_response(
                    "delegate_to_queen",
                    {
                        "colony_id": colony_id,
                        "task": "ログインフォームを作成",
                    },
                ),
                _make_text_response("ログインフォーム作成タスクをQueen Beeに委譲しました。"),
            ],
        )

        # Queen BeeのLLMもモック（Worker Beeの実行をシンプルにするため）
        with patch("colonyforge.queen_bee.server.QueenBeeMCPServer") as mock_queen_cls:
            mock_queen = AsyncMock()
            mock_queen.dispatch_tool = AsyncMock(
                return_value={
                    "status": "completed",
                    "results": [
                        {
                            "task_id": "task-001",
                            "status": "completed",
                            "result": "login.html created",
                            "llm_output": "ログインフォームをHTML/CSSで作成しました。",
                            "tool_calls_made": 3,
                        }
                    ],
                    "summary": {"total": 1, "completed": 1, "failed": 0},
                }
            )
            mock_queen.close = AsyncMock()
            mock_queen_cls.return_value = mock_queen

            # Act
            result = await beekeeper.dispatch_tool(
                "send_message",
                {
                    "message": "ログインフォームを作成して",
                },
            )

        # Assert: 委譲が成功
        assert result["status"] == "success"
        assert result["actions_taken"] >= 1

        await beekeeper.close()


class TestChatChainSessionState:
    """チャットチェーン中のセッション状態遷移テスト"""

    @pytest.mark.asyncio
    async def test_session_returns_to_active_after_success(self, ar):
        """成功時にセッションがACTIVEに戻る

        send_message処理中はBUSY、完了後はACTIVEに復帰する。
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)
        _inject_mock_llm(
            beekeeper,
            [
                _make_text_response("Done"),
            ],
        )

        # Act
        await beekeeper.dispatch_tool("send_message", {"message": "test"})

        # Assert: セッションはACTIVE
        from colonyforge.beekeeper.session import SessionState

        assert beekeeper.current_session.state == SessionState.ACTIVE

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_session_returns_to_active_after_error(self, ar):
        """エラー時にもセッションがACTIVEに戻る

        LLMエラーが起きてもセッションがBUSYのまま残らないことを確認。
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)
        mock_client = MagicMock()
        mock_client.chat = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_client.close = AsyncMock()
        beekeeper._llm_client = mock_client

        # Act
        await beekeeper.dispatch_tool("send_message", {"message": "test"})

        # Assert: エラーでもACTIVEに戻る
        from colonyforge.beekeeper.session import SessionState

        assert beekeeper.current_session.state == SessionState.ACTIVE

        await beekeeper.close()

    @pytest.mark.asyncio
    async def test_multiple_messages_same_session(self, ar):
        """連続メッセージが同一セッションで処理される

        チャットの会話継続をシミュレート。
        """
        # Arrange
        beekeeper = BeekeeperMCPServer(ar=ar)
        _inject_mock_llm(
            beekeeper,
            [
                _make_text_response("First response"),
                _make_text_response("Second response"),
            ],
        )

        # Act: 1回目
        result1 = await beekeeper.dispatch_tool("send_message", {"message": "first"})
        session_id_1 = result1["session_id"]

        # Act: 2回目
        result2 = await beekeeper.dispatch_tool("send_message", {"message": "second"})
        session_id_2 = result2["session_id"]

        # Assert: 同一セッション
        assert session_id_1 == session_id_2
        assert result1["response"] == "First response"
        assert result2["response"] == "Second response"

        await beekeeper.close()


class TestCLIChatIntegration:
    """CLI run_chat() の統合テスト"""

    @pytest.mark.asyncio
    async def test_run_chat_full_chain(self, tmp_path):
        """run_chat が全チェーンを通る統合テスト

        CLI → Beekeeper.dispatch_tool("send_message") →
        run_with_llm → AgentRunner.run → LLMClient.chat
        の全経路をモックLLMで検証。
        """
        # Arrange: BeekeeperにモックLLMを注入
        ar = AkashicRecord(tmp_path)
        beekeeper = BeekeeperMCPServer(ar=ar)

        mock_llm_response = _make_text_response("了解しました。ログインページの作成を開始します。")
        _inject_mock_llm(beekeeper, [mock_llm_response])

        # Act: send_message をCLIと同じ引数で呼ぶ
        result = await beekeeper.dispatch_tool(
            "send_message",
            {
                "message": "ECサイトのログインページを作成して",
                "context": {"working_directory": str(tmp_path)},
            },
        )

        # Assert
        assert result["status"] == "success"
        assert "ログインページ" in result["response"]
        assert result["actions_taken"] == 0

        await beekeeper.close()
