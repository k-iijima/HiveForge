"""LLMモジュールのテスト"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.llm.client import (
    LLMClient,
    LLMResponse,
    Message,
    ToolCall,
    _build_litellm_model_name,
)
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
        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Act
        result = await read_file_handler(str(test_file))
        data = json.loads(result)

        # Assert
        assert data["content"] == "Hello, World!"

        # Cleanup
        set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """存在しないファイルはエラー"""
        result = await read_file_handler("/nonexistent/file.txt")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_read_file_general_exception(self, tmp_path):
        """read_text中の例外がerrorとして返される

        ファイルは存在するがread_textで失敗する場合（パーミッションエラー等）、
        一般例外ハンドラがエラーメッセージを返す。
        """
        from pathlib import Path
        from unittest.mock import patch

        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Act: read_textで例外を発生させる
        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            result = await read_file_handler(str(test_file))
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Access denied" in data["error"]

        # Cleanup
        set_workspace_root(Path.cwd())


class TestWriteFileHandler:
    """write_file ハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        """ファイルを書き込める"""
        from hiveforge.llm.tools import set_workspace_root

        set_workspace_root(tmp_path)
        test_file = tmp_path / "output.txt"

        result = await write_file_handler(str(test_file), "New content")
        data = json.loads(result)

        assert data["success"] is True
        assert test_file.read_text() == "New content"

        set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, tmp_path):
        """親ディレクトリを作成する"""
        from hiveforge.llm.tools import set_workspace_root

        set_workspace_root(tmp_path)
        test_file = tmp_path / "subdir" / "deep" / "file.txt"

        result = await write_file_handler(str(test_file), "Content")
        data = json.loads(result)

        assert data["success"] is True
        assert test_file.exists()

        set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_write_file_general_exception(self, tmp_path):
        """write_text中の例外がerrorとして返される"""
        from pathlib import Path
        from unittest.mock import patch

        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)
        test_file = tmp_path / "output.txt"

        # Act: write_textで例外を発生させる
        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            result = await write_file_handler(str(test_file), "content")
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Disk full" in data["error"]

        set_workspace_root(Path.cwd())


class TestListDirectoryHandler:
    """list_directory ハンドラのテスト"""

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        """ディレクトリ内容を一覧表示できる"""
        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        (tmp_path / "subdir").mkdir()

        # Act
        result = await list_directory_handler(str(tmp_path))
        data = json.loads(result)

        # Assert
        assert len(data["entries"]) == 3

        set_workspace_root(Path.cwd())

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self):
        """存在しないディレクトリはエラー"""
        result = await list_directory_handler("/nonexistent/dir")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_list_directory_general_exception(self, tmp_path):
        """iterdir中の例外がerrorとして返される"""
        from pathlib import Path
        from unittest.mock import patch

        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)

        # Act: iterdir()で例外を発生させる
        with patch.object(Path, "iterdir", side_effect=PermissionError("No access")):
            result = await list_directory_handler(str(tmp_path))
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "No access" in data["error"]

        set_workspace_root(Path.cwd())


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
        from hiveforge.llm.tools import set_workspace_root

        # Arrange: ワークスペースをtmp_pathに設定
        set_workspace_root(tmp_path)

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

        # Cleanup
        set_workspace_root(Path.cwd())

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
# ======================================================================
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


# ==================== LLMClient テスト =============
def _make_mock_model_response(
    content="Hello!",
    tool_calls=None,
    finish_reason="stop",
    prompt_tokens=10,
    completion_tokens=5,
):
    """litellm.ModelResponse互換のモックを生成するヘルパー"""
    mock_response = MagicMock()

    # choice.message
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = tool_calls

    # choice
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = finish_reason

    mock_response.choices = [mock_choice]

    # usage
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = prompt_tokens
    mock_usage.completion_tokens = completion_tokens
    mock_usage.total_tokens = prompt_tokens + completion_tokens
    mock_response.usage = mock_usage

    return mock_response


def _make_mock_tool_call(tc_id="tc-1", name="read_file", arguments='{"path": "test.txt"}'):
    """litellm互換のツール呼び出しモックを生成するヘルパー"""
    mock_tc = MagicMock()
    mock_tc.id = tc_id
    mock_tc.function = MagicMock()
    mock_tc.function.name = name
    mock_tc.function.arguments = arguments
    return mock_tc


class TestBuildLiteLLMModelName:
    """_build_litellm_model_name のテスト"""

    def test_openai_adds_prefix(self):
        """OpenAIプロバイダーはopenai/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4o")
        assert _build_litellm_model_name(config) == "openai/gpt-4o"

    def test_anthropic_adds_prefix(self):
        """Anthropicプロバイダーはanthropic/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="anthropic", model="claude-3-5-sonnet-20241022")
        assert _build_litellm_model_name(config) == "anthropic/claude-3-5-sonnet-20241022"

    def test_ollama_chat_adds_prefix(self):
        """Ollama chatプロバイダーはollama_chat/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="ollama_chat", model="qwen3-coder")
        assert _build_litellm_model_name(config) == "ollama_chat/qwen3-coder"

    def test_ollama_adds_prefix(self):
        """Ollamaプロバイダーはollama/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="ollama", model="llama3.1")
        assert _build_litellm_model_name(config) == "ollama/llama3.1"

    def test_model_with_existing_prefix_kept(self):
        """既にprefix/model形式の場合はそのまま"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="openai", model="openai/gpt-4o-mini")
        assert _build_litellm_model_name(config) == "openai/gpt-4o-mini"

    def test_litellm_proxy_no_prefix(self):
        """litellm_proxyはプレフィックスを付与しない"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="litellm_proxy", model="my-model")
        assert _build_litellm_model_name(config) == "my-model"

    def test_groq_adds_prefix(self):
        """Groqプロバイダーはgroq/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="groq", model="llama-3.1-70b-versatile")
        assert _build_litellm_model_name(config) == "groq/llama-3.1-70b-versatile"

    def test_deepseek_adds_prefix(self):
        """DeepSeekプロバイダーはdeepseek/プレフィックスを付与"""
        from hiveforge.core.config import LLMConfig

        config = LLMConfig(provider="deepseek", model="deepseek-chat")
        assert _build_litellm_model_name(config) == "deepseek/deepseek-chat"


class TestLLMClient:
    """LLMClient統合テスト（LiteLLMモック）"""

    @pytest.fixture
    def llm_config(self):
        """テスト用LLM設定"""
        from hiveforge.core.config import LLMConfig

        return LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key_env="TEST_API_KEY",
            max_tokens=1024,
            temperature=0.5,
        )

    @pytest.fixture
    def mock_rate_limiter(self):
        """モックレートリミッター"""
        limiter = AsyncMock()
        limiter.wait = AsyncMock()
        limiter.acquire = AsyncMock()
        # context manager をモック
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        limiter.acquire.return_value = ctx
        limiter.handle_429 = AsyncMock()
        return limiter

    @pytest.fixture
    def client(self, llm_config, mock_rate_limiter):
        """テスト用LLMClient"""
        return LLMClient(config=llm_config, rate_limiter=mock_rate_limiter)

    def test_get_api_key_success(self, client, monkeypatch):
        """環境変数からAPIキーを取得できる"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test-12345")

        # Act
        api_key = client._get_api_key()

        # Assert
        assert api_key == "sk-test-12345"

    def test_get_api_key_missing(self, client, monkeypatch):
        """環境変数が未設定の場合エラー"""
        # Arrange
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        # Act & Assert
        with pytest.raises(ValueError, match="TEST_API_KEY"):
            client._get_api_key()

    def test_get_api_key_ollama_returns_none(self, monkeypatch):
        """Ollamaプロバイダーの場合APIキーはNone"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(provider="ollama", model="llama3.1")
        client = LLMClient(config=config)

        # Act
        api_key = client._get_api_key()

        # Assert
        assert api_key is None

    @pytest.mark.asyncio
    async def test_close_is_noop(self, client):
        """close()は互換性のため存在するが何もしない"""
        # Act - 例外が出ないこと
        await client.close()

    @pytest.mark.asyncio
    async def test_chat_openai(self, client, monkeypatch):
        """OpenAI APIをLiteLLM経由で正しく呼び出す"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        mock_response = _make_mock_model_response(content="Hello!")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [Message(role="user", content="Hi")]
            response = await client.chat(messages)

            # Assert
            assert response.content == "Hello!"
            assert response.finish_reason == "stop"
            assert response.usage["prompt_tokens"] == 10
            assert response.usage["completion_tokens"] == 5
            assert response.tool_calls == []
            mock_acomp.assert_called_once()
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["model"] == "openai/gpt-4o"
            assert call_kwargs["api_key"] == "sk-test"

    @pytest.mark.asyncio
    async def test_chat_openai_with_tool_calls(self, client, monkeypatch):
        """OpenAI APIのツール呼び出しレスポンスをパースできる"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        mock_tc = _make_mock_tool_call()
        mock_response = _make_mock_model_response(
            content=None, tool_calls=[mock_tc], finish_reason="tool_calls"
        )

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [Message(role="user", content="Read test.txt")]
            response = await client.chat(messages)

            # Assert
            assert response.content is None
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].name == "read_file"
            assert response.tool_calls[0].arguments == {"path": "test.txt"}
            assert response.has_tool_calls

    @pytest.mark.asyncio
    async def test_chat_anthropic(self, client, monkeypatch):
        """Anthropic APIをLiteLLM経由で正しく呼び出す"""
        # Arrange
        client.config = client.config.model_copy(
            update={
                "provider": "anthropic",
                "api_key_env": "TEST_API_KEY",
                "model": "claude-3-5-sonnet-20241022",
            }
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")
        mock_response = _make_mock_model_response(content="Bonjour!")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [
                Message(role="system", content="You are helpful."),
                Message(role="user", content="Hi"),
            ]
            response = await client.chat(messages)

            # Assert
            assert response.content == "Bonjour!"
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20241022"

    @pytest.mark.asyncio
    async def test_chat_anthropic_with_tool_calls(self, client, monkeypatch):
        """Anthropic APIのツール呼び出しレスポンスをパースできる"""
        # Arrange
        client.config = client.config.model_copy(
            update={
                "provider": "anthropic",
                "api_key_env": "TEST_API_KEY",
                "model": "claude-3-5-sonnet-20241022",
            }
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")
        mock_tc = _make_mock_tool_call()
        mock_response = _make_mock_model_response(
            content="Let me read that.", tool_calls=[mock_tc], finish_reason="tool_use"
        )

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [Message(role="user", content="Read test.txt")]
            response = await client.chat(messages)

            # Assert
            assert response.content == "Let me read that."
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].name == "read_file"

    @pytest.mark.asyncio
    async def test_chat_with_tools_and_tool_choice(self, client, monkeypatch):
        """tools/tool_choiceパラメータがLiteLLMに渡される"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        mock_response = _make_mock_model_response(content="OK")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            tools = [{"function": {"name": "test", "parameters": {}}}]
            tool_choice = "auto"
            await client.chat(
                [Message(role="user", content="Hi")],
                tools=tools,
                tool_choice=tool_choice,
            )

            # Assert
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["tools"] == tools
            assert call_kwargs["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_chat_message_with_tool_call_id(self, client, monkeypatch):
        """tool_call_idを含むメッセージが正しく変換される"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        mock_response = _make_mock_model_response(content="Done")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [
                Message(role="user", content="Do something"),
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCall(id="tc-1", name="test", arguments={"a": 1})],
                ),
                Message(role="tool", content="result", tool_call_id="tc-1"),
            ]
            await client.chat(messages)

            # Assert
            call_kwargs = mock_acomp.call_args[1]
            openai_msgs = call_kwargs["messages"]
            tool_msg = [m for m in openai_msgs if m.get("tool_call_id") == "tc-1"]
            assert len(tool_msg) == 1

    @pytest.mark.asyncio
    async def test_chat_ollama(self, monkeypatch, mock_rate_limiter):
        """OllamaプロバイダーをLiteLLM経由で呼び出す（APIキー不要）"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(
            provider="ollama_chat",
            model="qwen3-coder",
            api_base="http://localhost:11434",
            max_tokens=2048,
        )
        client = LLMClient(config=config, rate_limiter=mock_rate_limiter)
        mock_response = _make_mock_model_response(content="Hello from Ollama!")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [Message(role="user", content="Hi")]
            response = await client.chat(messages)

            # Assert
            assert response.content == "Hello from Ollama!"
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["model"] == "ollama_chat/qwen3-coder"
            assert call_kwargs["api_base"] == "http://localhost:11434"
            assert "api_key" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_litellm_proxy(self, monkeypatch, mock_rate_limiter):
        """LiteLLM Proxy経由でモデルを呼び出す"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(
            provider="litellm_proxy",
            model="my-custom-model",
            api_base="http://litellm-proxy:4000",
            api_key_env="LITELLM_PROXY_KEY",
        )
        client = LLMClient(config=config, rate_limiter=mock_rate_limiter)
        monkeypatch.setenv("LITELLM_PROXY_KEY", "sk-proxy")
        mock_response = _make_mock_model_response(content="Proxy response")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            messages = [Message(role="user", content="Hi")]
            response = await client.chat(messages)

            # Assert
            assert response.content == "Proxy response"
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["model"] == "my-custom-model"
            assert call_kwargs["api_base"] == "http://litellm-proxy:4000"
            assert call_kwargs["api_key"] == "sk-proxy"

    @pytest.mark.asyncio
    async def test_chat_with_fallback_models(self, client, monkeypatch):
        """フォールバックモデルが設定されている場合にfallbacksパラメータが渡される"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        client.config = client.config.model_copy(
            update={"fallback_models": ["anthropic/claude-3-haiku-20240307"]}
        )
        mock_response = _make_mock_model_response(content="OK")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            await client.chat([Message(role="user", content="Hi")])

            # Assert
            call_kwargs = mock_acomp.call_args[1]
            assert "fallbacks" in call_kwargs
            assert call_kwargs["fallbacks"] == [{"model": "anthropic/claude-3-haiku-20240307"}]

    @pytest.mark.asyncio
    async def test_chat_authentication_error(self, client, monkeypatch):
        """LiteLLM認証エラーがValueErrorに変換される"""
        import litellm

        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "invalid-key")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.side_effect = litellm.exceptions.AuthenticationError(
                message="Invalid API key",
                model="openai/gpt-4o",
                llm_provider="openai",
            )

            # Act & Assert
            with pytest.raises(ValueError, match="認証エラー"):
                await client.chat([Message(role="user", content="Hi")])

    @pytest.mark.asyncio
    async def test_chat_num_retries_passed(self, client, monkeypatch):
        """num_retriesパラメータがLiteLLMに渡される"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        client.config = client.config.model_copy(update={"num_retries": 5})
        mock_response = _make_mock_model_response(content="OK")

        with patch(
            "hiveforge.llm.client.litellm.acompletion", new_callable=AsyncMock
        ) as mock_acomp:
            mock_acomp.return_value = mock_response

            # Act
            await client.chat([Message(role="user", content="Hi")])

            # Assert
            call_kwargs = mock_acomp.call_args[1]
            assert call_kwargs["num_retries"] == 5

    def test_check_api_key_returns_true_when_set(self, client, monkeypatch):
        """APIキーが設定されている場合check_api_keyがTrueを返す"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test-12345")

        # Act
        result = client.check_api_key()

        # Assert
        assert result is True

    def test_check_api_key_returns_false_when_unset(self, client, monkeypatch):
        """APIキーが未設定の場合check_api_keyがFalseを返す"""
        # Arrange
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        # Act
        result = client.check_api_key()

        # Assert
        assert result is False

    def test_check_api_key_returns_false_when_empty(self, client, monkeypatch):
        """APIキーが空文字の場合check_api_keyがFalseを返す"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "")

        # Act
        result = client.check_api_key()

        # Assert
        assert result is False

    def test_check_api_key_ollama_always_true(self):
        """Ollamaプロバイダーでは常にTrueを返す"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(provider="ollama", model="llama3")
        client = LLMClient(config=config)

        # Act & Assert
        assert client.check_api_key() is True

    def test_check_api_key_ollama_chat_always_true(self):
        """Ollama chatプロバイダーでは常にTrueを返す"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(provider="ollama_chat", model="qwen3-coder")
        client = LLMClient(config=config)

        # Act & Assert
        assert client.check_api_key() is True

    @pytest.mark.asyncio
    async def test_build_messages_basic(self, client):
        """基本的なメッセージがOpenAI互換形式に変換される"""
        # Arrange
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hi"),
        ]

        # Act
        result = client._build_messages(messages)

        # Assert
        assert len(result) == 2
        assert result[0] == {"role": "system", "content": "You are helpful"}
        assert result[1] == {"role": "user", "content": "Hi"}

    @pytest.mark.asyncio
    async def test_build_messages_with_tool_calls(self, client):
        """ツール呼び出し付きメッセージが正しく変換される"""
        # Arrange
        messages = [
            Message(
                role="assistant",
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="test", arguments={"x": 1})],
            ),
        ]

        # Act
        result = client._build_messages(messages)

        # Assert
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert len(result[0]["tool_calls"]) == 1
        assert result[0]["tool_calls"][0]["function"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_build_messages_with_tool_result(self, client):
        """ツール結果メッセージが正しく変換される"""
        # Arrange
        messages = [
            Message(role="tool", content='{"result": "ok"}', tool_call_id="tc-1"),
        ]

        # Act
        result = client._build_messages(messages)

        # Assert
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tc-1"

    @pytest.mark.asyncio
    async def test_parse_response_no_tool_calls(self, client):
        """ツール呼び出しなしのレスポンスをパースできる"""
        # Arrange
        mock_response = _make_mock_model_response(content="OK", finish_reason="stop")

        # Act
        result = client._parse_response(mock_response)

        # Assert
        assert result.content == "OK"
        assert result.tool_calls == []
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_parse_response_with_tool_calls(self, client):
        """ツール呼び出しありのレスポンスをパースできる"""
        # Arrange
        mock_tc = _make_mock_tool_call(
            tc_id="tc-1", name="read_file", arguments='{"path": "x.txt"}'
        )
        mock_response = _make_mock_model_response(
            content=None, tool_calls=[mock_tc], finish_reason="tool_calls"
        )

        # Act
        result = client._parse_response(mock_response)

        # Assert
        assert result.has_tool_calls
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "x.txt"}

    @pytest.mark.asyncio
    async def test_parse_response_arguments_already_dict(self, client):
        """引数が既にdictの場合もパースできる"""
        # Arrange
        mock_tc = _make_mock_tool_call()
        mock_tc.function.arguments = {"path": "test.txt"}  # dictで渡される場合
        mock_response = _make_mock_model_response(
            content=None, tool_calls=[mock_tc], finish_reason="tool_calls"
        )

        # Act
        result = client._parse_response(mock_response)

        # Assert
        assert result.tool_calls[0].arguments == {"path": "test.txt"}


# ==================== run_command_handler テスト =============
class TestRunCommandHandler:
    """run_command_handlerのテスト"""

    @pytest.mark.asyncio
    async def test_run_simple_command(self):
        """許可リスト内のシンプルなコマンドを実行できる"""
        from hiveforge.llm.tools import run_command_handler

        # Act: 'ls'は許可リストに含まれる
        result_str = await run_command_handler("ls -la")
        result = json.loads(result_str)

        # Assert
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_run_failing_command(self):
        """許可リスト外のコマンドはブロックされる"""
        from hiveforge.llm.tools import run_command_handler

        # Act: 'false'は許可リストに含まれない
        result_str = await run_command_handler("false")
        result = json.loads(result_str)

        # Assert
        assert "error" in result
        assert "not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_list_directory_not_dir(self, tmp_path):
        """ファイルをディレクトリとして開けない"""
        from hiveforge.llm.tools import set_workspace_root

        # Arrange
        set_workspace_root(tmp_path)
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")

        # Act
        result_str = await list_directory_handler(str(file_path))
        result = json.loads(result_str)

        # Assert
        assert "error" in result
        assert "ディレクトリではありません" in result["error"]

        set_workspace_root(Path.cwd())


# =============================================================================
# AgentRunner ツール呼び出し必須モード (require_tool_use)
# ======================================================================
class TestAgentRunnerRequireToolUse:
    """require_tool_use=True 時のツール呼び出し必須モードのテスト"""

    @pytest.fixture
    def mock_client(self):
        """モックLLMクライアント"""
        client = MagicMock(spec=LLMClient)
        client.chat = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_require_tool_use_retries_when_no_tool_call(self, mock_client, tmp_path):
        """require_tool_use=True でツール未使用の応答が返った場合、
        再試行プロンプトを送り、LLMにツール呼び出しを促す

        1回目: テキストのみ応答 → 再試行
        2回目: ツール呼び出し → 成功
        """
        # Arrange: 1回目テキストのみ、2回目ツール呼び出し、3回目最終応答
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello!")

        mock_client.chat.side_effect = [
            LLMResponse(
                content="コマンドを実行します",
                tool_calls=[],
                finish_reason="stop",
            ),
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc-1", name="read_file", arguments={"path": str(test_file)})
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="ファイルの内容は Hello! です",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        runner = AgentRunner(mock_client, require_tool_use=True)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("ファイルを読んで")

        # Assert: 再試行後にツールが使われ成功
        assert result.success is True
        assert result.tool_calls_made == 1
        assert mock_client.chat.call_count == 3  # 初回 + 再試行 + 最終

    @pytest.mark.asyncio
    async def test_require_tool_use_fails_after_max_retries(self, mock_client):
        """require_tool_use=True で再試行回数を超えてもツール未使用なら失敗

        LLMが何度もテキストのみ応答を返す場合、再試行上限後に失敗する。
        """
        # Arrange: 常にテキストのみ応答
        mock_client.chat.return_value = LLMResponse(
            content="やりました（嘘）",
            tool_calls=[],
            finish_reason="stop",
        )

        runner = AgentRunner(
            mock_client,
            require_tool_use=True,
            tool_use_retries=2,
        )
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("コマンドを実行して")

        # Assert: 失敗し、エラーメッセージにツール未使用が記録される
        assert result.success is False
        assert result.tool_calls_made == 0
        assert "ツール" in result.error

    @pytest.mark.asyncio
    async def test_require_tool_use_false_allows_text_only(self, mock_client):
        """require_tool_use=False (デフォルト) ではテキスト応答で正常終了

        従来の動作が壊れないことを確認。
        """
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="了解しました",
            tool_calls=[],
            finish_reason="stop",
        )

        runner = AgentRunner(mock_client, require_tool_use=False)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("hello")

        # Assert: 従来通り成功
        assert result.success is True
        assert result.output == "了解しました"
        assert result.tool_calls_made == 0

    @pytest.mark.asyncio
    async def test_require_tool_use_succeeds_on_first_try(self, mock_client, tmp_path):
        """require_tool_use=True でも初回からツールが使われれば通常通り成功

        再試行ロジックが不要に発火しないことを確認。
        """
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
            LLMResponse(
                content="完了",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        runner = AgentRunner(mock_client, require_tool_use=True)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        result = await runner.run("ファイルを読んで")

        # Assert
        assert result.success is True
        assert result.tool_calls_made == 1
        assert mock_client.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_require_tool_use_no_tools_registered_skips_retry(self, mock_client):
        """ツール未登録時はrequire_tool_use=Trueでも再試行しない

        ツールがそもそも存在しない場合、再試行しても無意味なのでスキップ。
        """
        # Arrange
        mock_client.chat.return_value = LLMResponse(
            content="ツールがないので回答します",
            tool_calls=[],
            finish_reason="stop",
        )

        runner = AgentRunner(mock_client, require_tool_use=True)
        # ツール未登録

        # Act
        result = await runner.run("何かして")

        # Assert: ツールなしなので通常終了
        assert result.success is True
        assert mock_client.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_prompt_is_sent_to_llm(self, mock_client, tmp_path):
        """再試行時に「ツールを使え」という指示メッセージがLLMに渡される

        再試行プロンプトの内容を検証。
        """
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("data")

        mock_client.chat.side_effect = [
            LLMResponse(
                content="テキスト応答",
                tool_calls=[],
                finish_reason="stop",
            ),
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="tc-1", name="read_file", arguments={"path": str(test_file)})
                ],
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="Done",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        runner = AgentRunner(mock_client, require_tool_use=True)
        runner.register_tool(READ_FILE_TOOL)

        # Act
        await runner.run("ファイルを読んで")

        # Assert: 2回目のchat呼び出しのメッセージに再試行指示が含まれる
        second_call_messages = mock_client.chat.call_args_list[1][1]["messages"]
        # 末尾のメッセージに再試行プロンプトがある
        retry_messages = [
            m for m in second_call_messages if m.role == "user" and "ツール" in m.content
        ]
        assert len(retry_messages) >= 1, (
            f"再試行プロンプトが見つからない: {[(m.role, m.content[:50]) for m in second_call_messages]}"
        )
