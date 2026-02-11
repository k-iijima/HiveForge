"""ActivityBusとAgentRunner/各サーバーの統合テスト

AgentRunnerのrun()/_execute_tool()でActivityBusイベントが
正しく発行されることを検証する。
AAAパターン（Arrange-Act-Assert）を使用。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hiveforge.core.activity_bus import (
    ActivityBus,
    ActivityEvent,
    ActivityType,
    AgentInfo,
    AgentRole,
)
from hiveforge.llm.client import LLMClient, LLMResponse, ToolCall
from hiveforge.llm.runner import AgentRunner, ToolDefinition

# =============================================================================
# フィクスチャ
# =============================================================================


@pytest.fixture(autouse=True)
def reset_activity_bus():
    """各テストでActivityBusをリセット"""
    ActivityBus.reset()
    yield
    ActivityBus.reset()


@pytest.fixture
def mock_client():
    """モックLLMクライアント"""
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def agent_info():
    """テスト用AgentInfo"""
    return AgentInfo(
        agent_id="worker-1",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-1",
        colony_id="colony-1",
    )


@pytest.fixture
def collected_events():
    """発行されたイベントを収集するリスト"""
    events: list[ActivityEvent] = []
    return events


@pytest.fixture
def event_collector(collected_events):
    """ActivityBusにイベント収集ハンドラーを登録"""
    bus = ActivityBus.get_instance()

    async def _collector(event: ActivityEvent) -> None:
        collected_events.append(event)

    bus.subscribe(_collector)
    return _collector


# =============================================================================
# AgentRunner + ActivityBus 統合テスト
# =============================================================================


class TestAgentRunnerActivityEmission:
    """AgentRunnerがActivityBusにイベントを発行するテスト"""

    @pytest.mark.asyncio
    async def test_run_emits_llm_request_event(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """run()がLLMリクエスト時にLLM_REQUESTイベントを発行する"""
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )
        runner = AgentRunner(mock_client, agent_info=agent_info)

        # Act
        await runner.run("Say hello")

        # Assert: LLM_REQUESTイベントが発行されている
        llm_requests = [e for e in collected_events if e.activity_type == ActivityType.LLM_REQUEST]
        assert len(llm_requests) >= 1
        assert llm_requests[0].agent == agent_info

    @pytest.mark.asyncio
    async def test_run_emits_llm_response_event(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """run()がLLMレスポンス受信時にLLM_RESPONSEイベントを発行する"""
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )
        runner = AgentRunner(mock_client, agent_info=agent_info)

        # Act
        await runner.run("Say hello")

        # Assert: LLM_RESPONSEイベントが発行されている
        llm_responses = [
            e for e in collected_events if e.activity_type == ActivityType.LLM_RESPONSE
        ]
        assert len(llm_responses) >= 1
        assert llm_responses[0].agent == agent_info

    @pytest.mark.asyncio
    async def test_run_emits_llm_response_with_content_summary(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """LLM_RESPONSEイベントにレスポンスの概要が含まれる"""
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="This is the answer.", tool_calls=[], finish_reason="stop"
        )
        runner = AgentRunner(mock_client, agent_info=agent_info)

        # Act
        await runner.run("Question?")

        # Assert: 概要にコンテンツが含まれる
        llm_responses = [
            e for e in collected_events if e.activity_type == ActivityType.LLM_RESPONSE
        ]
        assert len(llm_responses) >= 1
        assert "This is the answer" in llm_responses[0].summary

    @pytest.mark.asyncio
    async def test_tool_execution_emits_mcp_tool_call(
        self, mock_client, agent_info, collected_events, event_collector, tmp_path
    ):
        """ツール実行時にMCP_TOOL_CALLイベントを発行する"""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc-1", name="read_file", arguments={"path": str(test_file)})
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Done", tool_calls=[], finish_reason="stop"),
        ]

        async def dummy_handler(**kwargs):
            return "file content"

        tool = ToolDefinition(
            name="read_file",
            description="Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=dummy_handler,
        )

        runner = AgentRunner(mock_client, agent_info=agent_info)
        runner.register_tool(tool)

        # Act
        await runner.run("Read test.txt")

        # Assert: MCP_TOOL_CALLイベントが発行されている
        tool_calls = [e for e in collected_events if e.activity_type == ActivityType.MCP_TOOL_CALL]
        assert len(tool_calls) == 1
        assert "read_file" in tool_calls[0].summary

    @pytest.mark.asyncio
    async def test_tool_execution_emits_mcp_tool_result(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """ツール実行後にMCP_TOOL_RESULTイベントを発行する"""
        # Arrange
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="my_tool", arguments={"x": "1"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Done", tool_calls=[], finish_reason="stop"),
        ]

        async def dummy_handler(**kwargs):
            return "result data"

        tool = ToolDefinition(
            name="my_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            handler=dummy_handler,
        )

        runner = AgentRunner(mock_client, agent_info=agent_info)
        runner.register_tool(tool)

        # Act
        await runner.run("Use my_tool")

        # Assert: MCP_TOOL_RESULTイベントが発行されている
        tool_results = [
            e for e in collected_events if e.activity_type == ActivityType.MCP_TOOL_RESULT
        ]
        assert len(tool_results) == 1

    @pytest.mark.asyncio
    async def test_tool_error_emits_mcp_tool_result_with_error(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """ツールエラー時もMCP_TOOL_RESULTイベントにエラーが含まれる"""
        # Arrange
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="fail_tool", arguments={})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Error handled", tool_calls=[], finish_reason="stop"),
        ]

        async def failing_handler(**kwargs):
            raise RuntimeError("Tool failed!")

        tool = ToolDefinition(
            name="fail_tool",
            description="A tool that fails",
            parameters={"type": "object", "properties": {}},
            handler=failing_handler,
        )

        runner = AgentRunner(mock_client, agent_info=agent_info)
        runner.register_tool(tool)

        # Act
        await runner.run("Use fail_tool")

        # Assert: エラー情報を含むMCP_TOOL_RESULTイベント
        tool_results = [
            e for e in collected_events if e.activity_type == ActivityType.MCP_TOOL_RESULT
        ]
        assert len(tool_results) == 1
        assert "error" in tool_results[0].detail

    @pytest.mark.asyncio
    async def test_run_without_agent_info_no_events(
        self, mock_client, collected_events, event_collector
    ):
        """agent_info未設定ではActivityBusにイベントを発行しない（後方互換性）"""
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )
        runner = AgentRunner(mock_client)  # agent_info=None

        # Act
        await runner.run("Say hello")

        # Assert: イベントは発行されない
        assert len(collected_events) == 0

    @pytest.mark.asyncio
    async def test_llm_error_propagates_exception(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """LLMエラー時に例外がそのまま伝搬する（フォールバックしない）"""
        # Arrange
        mock_client.chat.side_effect = RuntimeError("LLM connection failed")
        runner = AgentRunner(mock_client, agent_info=agent_info)

        # Act & Assert: 例外が伝搬する
        with pytest.raises(RuntimeError, match="LLM connection failed"):
            await runner.run("Say hello")

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_emit_multiple_events(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """複数ツール呼び出しで複数のMCPイベントが発行される"""
        # Arrange
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc-1", name="tool_a", arguments={}),
                    ToolCall(id="tc-2", name="tool_b", arguments={}),
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Done", tool_calls=[], finish_reason="stop"),
        ]

        async def handler_a(**kwargs):
            return "result_a"

        async def handler_b(**kwargs):
            return "result_b"

        runner = AgentRunner(mock_client, agent_info=agent_info)
        runner.register_tool(
            ToolDefinition(
                name="tool_a",
                description="Tool A",
                parameters={"type": "object", "properties": {}},
                handler=handler_a,
            )
        )
        runner.register_tool(
            ToolDefinition(
                name="tool_b",
                description="Tool B",
                parameters={"type": "object", "properties": {}},
                handler=handler_b,
            )
        )

        # Act
        await runner.run("Use both tools")

        # Assert: 各ツールにTOOL_CALL + TOOL_RESULT
        tool_calls = [e for e in collected_events if e.activity_type == ActivityType.MCP_TOOL_CALL]
        tool_results = [
            e for e in collected_events if e.activity_type == ActivityType.MCP_TOOL_RESULT
        ]
        assert len(tool_calls) == 2
        assert len(tool_results) == 2

    @pytest.mark.asyncio
    async def test_event_order_is_correct(
        self, mock_client, agent_info, collected_events, event_collector
    ):
        """イベントの発行順序が正しい: LLM_REQUEST → LLM_RESPONSE → TOOL_CALL → TOOL_RESULT → LLM_REQUEST → LLM_RESPONSE"""
        # Arrange
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="my_tool", arguments={})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Done", tool_calls=[], finish_reason="stop"),
        ]

        async def dummy_handler(**kwargs):
            return "result"

        runner = AgentRunner(mock_client, agent_info=agent_info)
        runner.register_tool(
            ToolDefinition(
                name="my_tool",
                description="Test",
                parameters={"type": "object", "properties": {}},
                handler=dummy_handler,
            )
        )

        # Act
        await runner.run("Test")

        # Assert: 順序チェック
        types = [e.activity_type for e in collected_events]
        assert types == [
            ActivityType.LLM_REQUEST,
            ActivityType.LLM_RESPONSE,
            ActivityType.MCP_TOOL_CALL,
            ActivityType.MCP_TOOL_RESULT,
            ActivityType.LLM_REQUEST,
            ActivityType.LLM_RESPONSE,
        ]


# =============================================================================
# AgentInfo生成ヘルパーテスト
# =============================================================================


class TestAgentRunnerAgentInfo:
    """AgentRunnerのagent_info設定テスト"""

    def test_agent_info_default_is_none(self, mock_client):
        """デフォルトではagent_infoはNone"""
        runner = AgentRunner(mock_client)
        assert runner.agent_info is None

    def test_agent_info_can_be_set(self, mock_client, agent_info):
        """agent_infoを設定できる"""
        runner = AgentRunner(mock_client, agent_info=agent_info)
        assert runner.agent_info == agent_info
        assert runner.agent_info.role == AgentRole.WORKER_BEE
