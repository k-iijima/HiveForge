"""LLMモジュールのテスト"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiveforge.llm.client import LLMClient, LLMResponse, Message, ToolCall
from hiveforge.llm.prompts import WORKER_BEE_SYSTEM, get_system_prompt
from hiveforge.llm.runner import AgentContext, AgentRunner, RunResult
from hiveforge.llm.tools import (
    READ_FILE_TOOL,
    WRITE_FILE_TOOL,
    get_basic_tools,
    list_directory_handler,
    read_file_handler,
    write_file_handler,
)


class TestMessage:
    """Messageクラスのテスト"""

    def test_create_message(self):
        """メッセージを作成できる"""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_call_id is None
        assert msg.tool_calls is None

    def test_message_with_tool_calls(self):
        """ツール呼び出し付きメッセージを作成できる"""
        tool_call = ToolCall(id="tc-1", name="read_file", arguments={"path": "test.txt"})
        msg = Message(role="assistant", content="", tool_calls=[tool_call])

        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"


class TestToolCall:
    """ToolCallクラスのテスト"""

    def test_create_tool_call(self):
        """ツール呼び出しを作成できる"""
        tc = ToolCall(id="tc-1", name="write_file", arguments={"path": "a.txt", "content": "hello"})

        assert tc.id == "tc-1"
        assert tc.name == "write_file"
        assert tc.arguments["path"] == "a.txt"


class TestLLMResponse:
    """LLMResponseクラスのテスト"""

    def test_response_without_tool_calls(self):
        """ツール呼び出しなしの応答"""
        resp = LLMResponse(content="Done", tool_calls=[], finish_reason="stop")

        assert resp.content == "Done"
        assert resp.has_tool_calls is False

    def test_response_with_tool_calls(self):
        """ツール呼び出しありの応答"""
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "test.txt"})
        resp = LLMResponse(content=None, tool_calls=[tc], finish_reason="tool_calls")

        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1


class TestPrompts:
    """プロンプトのテスト"""

    def test_worker_bee_prompt_exists(self):
        """Worker Beeプロンプトが存在する"""
        prompt = get_system_prompt("worker_bee")

        assert "Worker Bee" in prompt
        assert len(prompt) > 100

    def test_queen_bee_prompt_exists(self):
        """Queen Beeプロンプトが存在する"""
        prompt = get_system_prompt("queen_bee")

        assert "Queen Bee" in prompt

    def test_beekeeper_prompt_exists(self):
        """Beekeeperプロンプトが存在する"""
        prompt = get_system_prompt("beekeeper")

        assert "Beekeeper" in prompt

    def test_unknown_agent_returns_worker_bee(self):
        """不明なエージェントタイプはWorker Beeを返す"""
        prompt = get_system_prompt("unknown")

        assert prompt == WORKER_BEE_SYSTEM


class TestToolDefinition:
    """ToolDefinitionクラスのテスト"""

    def test_to_openai_format(self):
        """OpenAI形式に変換できる"""
        tool = READ_FILE_TOOL
        openai_format = tool.to_openai_format()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "read_file"
        assert "path" in openai_format["function"]["parameters"]["properties"]


class TestBasicTools:
    """基本ツールのテスト"""

    def test_get_basic_tools(self):
        """基本ツールリストを取得できる"""
        tools = get_basic_tools()

        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_directory" in tool_names
        assert "run_command" in tool_names


class TestReadFileHandler:
    """read_file ハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        """存在するファイルを読み込める"""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Act
        result = await read_file_handler(str(test_file))
        data = json.loads(result)

        # Assert
        assert data["content"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """存在しないファイルはエラー"""
        result = await read_file_handler("/nonexistent/file.txt")
        data = json.loads(result)

        assert "error" in data


class TestWriteFileHandler:
    """write_file ハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        """ファイルを書き込める"""
        test_file = tmp_path / "output.txt"

        result = await write_file_handler(str(test_file), "New content")
        data = json.loads(result)

        assert data["success"] is True
        assert test_file.read_text() == "New content"

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, tmp_path):
        """親ディレクトリを作成する"""
        test_file = tmp_path / "subdir" / "deep" / "file.txt"

        result = await write_file_handler(str(test_file), "Content")
        data = json.loads(result)

        assert data["success"] is True
        assert test_file.exists()


class TestListDirectoryHandler:
    """list_directory ハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        """ディレクトリ内容を一覧表示できる"""
        # Arrange
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        (tmp_path / "subdir").mkdir()

        # Act
        result = await list_directory_handler(str(tmp_path))
        data = json.loads(result)

        # Assert
        assert len(data["entries"]) == 3

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self):
        """存在しないディレクトリはエラー"""
        result = await list_directory_handler("/nonexistent/dir")
        data = json.loads(result)

        assert "error" in data


class TestAgentRunner:
    """AgentRunnerクラスのテスト"""

    @pytest.fixture
    def mock_client(self):
        """モックLLMクライアント"""
        client = MagicMock(spec=LLMClient)
        client.chat = AsyncMock()
        client.close = AsyncMock()
        return client

    def test_register_tool(self, mock_client):
        """ツールを登録できる"""
        runner = AgentRunner(mock_client)
        runner.register_tool(READ_FILE_TOOL)

        assert "read_file" in runner.tools

    def test_get_tool_definitions(self, mock_client):
        """ツール定義リストを取得できる"""
        runner = AgentRunner(mock_client)
        runner.register_tool(READ_FILE_TOOL)
        runner.register_tool(WRITE_FILE_TOOL)

        defs = runner.get_tool_definitions()

        assert len(defs) == 2

    @pytest.mark.asyncio
    async def test_run_simple_response(self, mock_client):
        """シンプルな応答（ツール呼び出しなし）"""
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!",
            tool_calls=[],
            finish_reason="stop",
        )
        runner = AgentRunner(mock_client)

        # Act
        result = await runner.run("Say hello")

        # Assert
        assert result.success is True
        assert result.output == "Done!"
        assert result.tool_calls_made == 0

    @pytest.mark.asyncio
    async def test_run_with_tool_call(self, mock_client, tmp_path):
        """ツール呼び出しを含む実行"""
        # Arrange: ファイルを作成
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello!")

        # 1回目: ツール呼び出し
        # 2回目: 最終応答
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc-1", name="read_file", arguments={"path": str(test_file)})
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="ファイルの内容は 'Hello!' です",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        runner = AgentRunner(mock_client)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("ファイルを読んで")

        # Assert
        assert result.success is True
        assert result.tool_calls_made == 1
        assert "Hello!" in result.output

    @pytest.mark.asyncio
    async def test_run_max_iterations(self, mock_client):
        """最大反復回数に達した場合"""
        # Arrange: 常にツール呼び出しを返す
        mock_client.chat.return_value = LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc-1", name="read_file", arguments={"path": "test.txt"})],
            finish_reason="tool_calls",
        )

        runner = AgentRunner(mock_client, max_iterations=2)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("無限ループ")

        # Assert
        assert result.success is False
        assert "最大反復回数" in result.error

    @pytest.mark.asyncio
    async def test_run_unknown_tool(self, mock_client):
        """未知のツールが呼ばれた場合"""
        # Arrange
        mock_client.chat.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="unknown_tool", arguments={})],
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="Unknown tool error handled",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        runner = AgentRunner(mock_client)

        # Act
        result = await runner.run("Run unknown tool")

        # Assert
        assert result.success is True
        assert result.tool_calls_made == 1


class TestAgentContext:
    """AgentContextクラスのテスト"""

    def test_create_context(self):
        """コンテキストを作成できる"""
        ctx = AgentContext(run_id="run-1", task_id="task-1")

        assert ctx.run_id == "run-1"
        assert ctx.task_id == "task-1"

    def test_default_values(self):
        """デフォルト値が設定される"""
        ctx = AgentContext(run_id="run-1")

        assert ctx.working_directory == "."
        assert ctx.metadata == {}


class TestRunResult:
    """RunResultクラスのテスト"""

    def test_success_result(self):
        """成功結果"""
        result = RunResult(success=True, output="Done", tool_calls_made=3)

        assert result.success is True
        assert result.error is None

    def test_error_result(self):
        """エラー結果"""
        result = RunResult(success=False, output="", error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"


# =============================================================================
# AgentRunnerプロンプトYAML統合テスト
# =============================================================================


class TestAgentRunnerPromptIntegration:
    """AgentRunnerがYAMLプロンプト設定を使用するテスト"""

    @pytest.fixture
    def mock_client(self):
        """モックLLMクライアント"""
        client = MagicMock(spec=LLMClient)
        client.chat = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def temp_vault(self, tmp_path):
        """テスト用の一時Vaultディレクトリ"""
        vault = tmp_path / "Vault"
        vault.mkdir()
        return vault

    def test_init_with_prompt_context(self, mock_client, temp_vault):
        """vault_path等のプロンプトコンテキストを受け取れる

        AgentRunnerにvault_path, hive_id, colony_id, worker_nameを渡せること。
        """
        # Arrange & Act
        runner = AgentRunner(
            mock_client,
            agent_type="worker_bee",
            vault_path=str(temp_vault),
            hive_id="hive-1",
            colony_id="colony-1",
            worker_name="coder",
        )

        # Assert
        assert runner.vault_path == str(temp_vault)
        assert runner.hive_id == "hive-1"
        assert runner.colony_id == "colony-1"
        assert runner.worker_name == "coder"

    def test_init_without_prompt_context(self, mock_client):
        """プロンプトコンテキストなしでも初期化できる（後方互換）

        vault_path等のパラメータは全てオプション。
        """
        # Arrange & Act
        runner = AgentRunner(mock_client, agent_type="worker_bee")

        # Assert
        assert runner.vault_path is None
        assert runner.hive_id == "0"
        assert runner.colony_id == "0"
        assert runner.worker_name == "default"

    @pytest.mark.asyncio
    async def test_run_uses_yaml_prompt_when_config_exists(self, mock_client, temp_vault):
        """YAML設定ファイルが存在する場合、そのプロンプトを使用する

        Vault内にカスタムプロンプトYAMLがあれば、それがLLMに渡される。
        """
        # Arrange: カスタムプロンプトYAMLを配置
        custom_prompt = "あなたはカスタムWorker Beeです。テスト用。"
        colony_dir = temp_vault / "hives" / "hive-1" / "colonies" / "colony-1"
        colony_dir.mkdir(parents=True)
        (colony_dir / "default_worker_bee.yml").write_text(
            f"name: default\nprompt:\n  system: {custom_prompt}\n",
            encoding="utf-8",
        )

        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )

        runner = AgentRunner(
            mock_client,
            agent_type="worker_bee",
            vault_path=str(temp_vault),
            hive_id="hive-1",
            colony_id="colony-1",
        )

        # Act
        await runner.run("テストタスク")

        # Assert: LLMに渡されたシステムプロンプトがカスタムのもの
        call_args = mock_client.chat.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = [m for m in messages if m.role == "system"][0]
        assert system_msg.content == custom_prompt

    @pytest.mark.asyncio
    async def test_run_falls_back_to_default_when_no_config(self, mock_client, temp_vault):
        """YAML設定がない場合、デフォルトプロンプトにフォールバックする

        Vaultにファイルがなくても、パッケージ内デフォルトまたはハードコードデフォルトを使用。
        """
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )

        runner = AgentRunner(
            mock_client,
            agent_type="worker_bee",
            vault_path=str(temp_vault),  # Vaultは空
            hive_id="nonexistent-hive",
            colony_id="nonexistent-colony",
        )

        # Act
        await runner.run("テストタスク")

        # Assert: システムプロンプトが何かしら設定されている（空でない）
        call_args = mock_client.chat.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = [m for m in messages if m.role == "system"][0]
        assert len(system_msg.content) > 0
        # デフォルトプロンプト（パッケージ内YAMLまたはハードコード）が使われる
        assert "Worker Bee" in system_msg.content

    @pytest.mark.asyncio
    async def test_run_without_vault_uses_default(self, mock_client):
        """vault_pathが未指定の場合もデフォルトプロンプトを使用する

        後方互換: vault_pathなしでもAgentRunnerは動作する。
        """
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )
        runner = AgentRunner(mock_client, agent_type="beekeeper")

        # Act
        await runner.run("テストメッセージ")

        # Assert: beekeeperのデフォルトプロンプトが使用される
        call_args = mock_client.chat.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = [m for m in messages if m.role == "system"][0]
        assert "Beekeeper" in system_msg.content

    @pytest.mark.asyncio
    async def test_queen_bee_loads_custom_prompt(self, mock_client, temp_vault):
        """Queen Beeのカスタムプロンプトが読み込まれる"""
        # Arrange
        custom_prompt = "あなたはカスタムQueen Beeです。"
        colony_dir = temp_vault / "hives" / "h1" / "colonies" / "c1"
        colony_dir.mkdir(parents=True)
        (colony_dir / "queen_bee.yml").write_text(
            f"name: default\nprompt:\n  system: {custom_prompt}\nmax_workers: 5\ntask_assignment_strategy: round_robin\n",
            encoding="utf-8",
        )

        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )

        runner = AgentRunner(
            mock_client,
            agent_type="queen_bee",
            vault_path=str(temp_vault),
            hive_id="h1",
            colony_id="c1",
        )

        # Act
        await runner.run("タスクを分解して")

        # Assert
        call_args = mock_client.chat.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = [m for m in messages if m.role == "system"][0]
        assert system_msg.content == custom_prompt

    @pytest.mark.asyncio
    async def test_beekeeper_loads_custom_prompt(self, mock_client, temp_vault):
        """Beekeeperのカスタムプロンプトが読み込まれる"""
        # Arrange
        custom_prompt = "あなたはカスタムBeekeeperです。"
        hive_dir = temp_vault / "hives" / "h1"
        hive_dir.mkdir(parents=True)
        (hive_dir / "beekeeper.yml").write_text(
            f"name: default\nprompt:\n  system: {custom_prompt}\n",
            encoding="utf-8",
        )

        mock_client.chat.return_value = LLMResponse(
            content="Done!", tool_calls=[], finish_reason="stop"
        )

        runner = AgentRunner(
            mock_client,
            agent_type="beekeeper",
            vault_path=str(temp_vault),
            hive_id="h1",
        )

        # Act
        await runner.run("ユーザーメッセージ")

        # Assert
        call_args = mock_client.chat.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = [m for m in messages if m.role == "system"][0]
        assert system_msg.content == custom_prompt
