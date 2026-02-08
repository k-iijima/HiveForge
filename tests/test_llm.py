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

    @pytest.mark.asyncio
    async def test_read_file_general_exception(self, tmp_path):
        """read_text中の例外がerrorとして返される

        ファイルは存在するがread_textで失敗する場合（パーミッションエラー等）、
        一般例外ハンドラがエラーメッセージを返す。
        """
        from pathlib import Path
        from unittest.mock import patch

        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Act: read_textで例外を発生させる
        with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            result = await read_file_handler(str(test_file))
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Access denied" in data["error"]


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

    @pytest.mark.asyncio
    async def test_write_file_general_exception(self, tmp_path):
        """write_text中の例外がerrorとして返される"""
        from pathlib import Path
        from unittest.mock import patch

        # Arrange
        test_file = tmp_path / "output.txt"

        # Act: write_textで例外を発生させる
        with patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            result = await write_file_handler(str(test_file), "content")
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "Disk full" in data["error"]


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

    @pytest.mark.asyncio
    async def test_list_directory_general_exception(self, tmp_path):
        """iterdir中の例外がerrorとして返される"""
        from pathlib import Path
        from unittest.mock import patch

        # Act: iterdir()で例外を発生させる
        with patch.object(Path, "iterdir", side_effect=PermissionError("No access")):
            result = await list_directory_handler(str(tmp_path))
            data = json.loads(result)

        # Assert
        assert "error" in data
        assert "No access" in data["error"]


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


# ==================== LLMClient テスト ====================


class TestLLMClient:
    """LLMClient統合テスト（HTTPモック）"""

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

    @pytest.mark.asyncio
    async def test_close_with_client(self, client):
        """HTTPクライアントを閉じる"""
        # Arrange: httpクライアント作成
        mock_http = AsyncMock()
        client._http_client = mock_http

        # Act
        await client.close()

        # Assert
        mock_http.aclose.assert_called_once()
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self, client):
        """クライアント未作成時はcloseしても安全"""
        # Arrange
        assert client._http_client is None

        # Act - 例外が出ないこと
        await client.close()

        # Assert
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_get_client_creates_once(self, client):
        """HTTPクライアントは1回だけ作成される"""
        # Act
        client1 = await client._get_client()
        client2 = await client._get_client()

        # Assert
        assert client1 is client2

        # Cleanup
        await client.close()

    @pytest.mark.asyncio
    async def test_chat_openai(self, client, monkeypatch):
        """OpenAI APIを正しく呼び出す"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hello!", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Hi")]
        response = await client.chat(messages)

        # Assert
        assert response.content == "Hello!"
        assert response.finish_reason == "stop"
        assert response.usage == {"prompt_tokens": 10, "completion_tokens": 5}
        assert response.tool_calls == []
        mock_http.post.assert_called_once()
        call_url = mock_http.post.call_args[0][0]
        assert "openai" in call_url

    @pytest.mark.asyncio
    async def test_chat_openai_with_tool_calls(self, client, monkeypatch):
        """OpenAI APIのツール呼び出しレスポンスをパースできる"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "tc-1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path": "test.txt"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

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
        """Anthropic APIを正しく呼び出す"""
        # Arrange
        client.config = client.config.model_copy(
            update={"provider": "anthropic", "api_key_env": "TEST_API_KEY"}
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Bonjour!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi"),
        ]
        response = await client.chat(messages)

        # Assert
        assert response.content == "Bonjour!"
        assert response.finish_reason == "end_turn"
        call_url = mock_http.post.call_args[0][0]
        assert "anthropic" in call_url

    @pytest.mark.asyncio
    async def test_chat_anthropic_with_tool_calls(self, client, monkeypatch):
        """Anthropic APIのツール呼び出しレスポンスをパースできる"""
        # Arrange
        client.config = client.config.model_copy(
            update={"provider": "anthropic", "api_key_env": "TEST_API_KEY"}
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "Let me read that."},
                {
                    "type": "tool_use",
                    "id": "tc-1",
                    "name": "read_file",
                    "input": {"path": "test.txt"},
                },
            ],
            "stop_reason": "tool_use",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Read test.txt")]
        response = await client.chat(messages)

        # Assert
        assert response.content == "Let me read that."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "read_file"

    @pytest.mark.asyncio
    async def test_chat_anthropic_tool_result_message(self, client, monkeypatch):
        """Anthropicでtoolロールメッセージが正しく変換される"""
        # Arrange
        client.config = client.config.model_copy(
            update={"provider": "anthropic", "api_key_env": "TEST_API_KEY"}
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Got it."}],
            "stop_reason": "end_turn",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act: tool結果メッセージを含めて呼び出す
        messages = [
            Message(role="user", content="Read file"),
            Message(
                role="assistant",
                content="Reading...",
                tool_calls=[ToolCall(id="tc-1", name="read_file", arguments={"path": "a.txt"})],
            ),
            Message(role="tool", content='{"content": "hello"}', tool_call_id="tc-1"),
        ]
        response = await client.chat(messages)

        # Assert
        assert response.content == "Got it."
        # リクエストボディを検証
        call_body = mock_http.post.call_args[1]["json"]
        # toolメッセージはuserロールに変換される
        tool_msg = [
            m
            for m in call_body["messages"]
            if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        assert len(tool_msg) == 1

    @pytest.mark.asyncio
    async def test_chat_anthropic_with_tools_definition(self, client, monkeypatch):
        """Anthropicでツール定義が正しく変換される"""
        # Arrange
        client.config = client.config.model_copy(
            update={"provider": "anthropic", "api_key_env": "TEST_API_KEY"}
        )
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act
        tools = [
            {
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
                }
            }
        ]
        await client.chat([Message(role="user", content="Hi")], tools=tools)

        # Assert
        call_body = mock_http.post.call_args[1]["json"]
        assert "tools" in call_body
        assert call_body["tools"][0]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_chat_unsupported_provider(self, client, monkeypatch):
        """未サポートのプロバイダーでエラー"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        # providerを無理やり変更（Pydanticバリデーション回避）
        object.__setattr__(client.config, "provider", "unknown")

        # Act & Assert
        with pytest.raises(ValueError, match="未サポート"):
            await client.chat([Message(role="user", content="Hi")])

    @pytest.mark.asyncio
    async def test_chat_openai_with_tools_and_tool_choice(self, client, monkeypatch):
        """OpenAI APIにtools/tool_choiceを渡せる"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "OK", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act
        tools = [{"function": {"name": "test", "parameters": {}}}]
        tool_choice = "auto"
        await client.chat(
            [Message(role="user", content="Hi")],
            tools=tools,
            tool_choice=tool_choice,
        )

        # Assert
        call_body = mock_http.post.call_args[1]["json"]
        assert "tools" in call_body
        assert call_body["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_chat_openai_message_with_tool_call_id(self, client, monkeypatch):
        """tool_call_idを含むメッセージが正しく変換される"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Done", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

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
        call_body = mock_http.post.call_args[1]["json"]
        tool_msg = [m for m in call_body["messages"] if m.get("tool_call_id") == "tc-1"]
        assert len(tool_msg) == 1

    @pytest.mark.asyncio
    async def test_chat_openai_429_retry(self, client, mock_rate_limiter, monkeypatch):
        """OpenAI API 429→レートリミットハンドル→リトライ（L193-197）"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        # 1回目: 429, 2回目: 200
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.raise_for_status = MagicMock()
        mock_200.json.return_value = {
            "choices": [
                {
                    "message": {"content": "OK", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[mock_429, mock_200])
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Hi")]
        response = await client.chat(messages)

        # Assert: 429処理後にリトライして成功
        assert response.content == "OK"
        mock_rate_limiter.handle_429.assert_awaited_once_with(1.0)
        assert mock_http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_anthropic_429_retry(self, monkeypatch, mock_rate_limiter):
        """Anthropic API 429→レートリミットハンドル→リトライ（L311-314）"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key_env="TEST_API_KEY",
            max_tokens=1024,
        )
        client = LLMClient(config=config, rate_limiter=mock_rate_limiter)
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        # 1回目: 429, 2回目: 200
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "2"}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.raise_for_status = MagicMock()
        mock_200.json.return_value = {
            "content": [{"type": "text", "text": "Retried OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[mock_429, mock_200])
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Hi")]
        response = await client.chat(messages)

        # Assert
        assert response.content == "Retried OK"
        mock_rate_limiter.handle_429.assert_awaited_once_with(2.0)
        assert mock_http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_anthropic_assistant_no_content_with_tool_calls(
        self, monkeypatch, mock_rate_limiter
    ):
        """Anthropic: assistantメッセージのcontent=NoneでもTool呼び出しが送信される（L257->259）"""
        from hiveforge.core.config import LLMConfig

        # Arrange
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key_env="TEST_API_KEY",
            max_tokens=1024,
        )
        client = LLMClient(config=config, rate_limiter=mock_rate_limiter)
        monkeypatch.setenv("TEST_API_KEY", "sk-ant-test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Done"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        # Act: content=None + tool_callsのassistantメッセージを含む
        messages = [
            Message(role="user", content="Call a tool"),
            Message(
                role="assistant",
                content=None,
                tool_calls=[ToolCall(id="tc-1", name="test_tool", arguments={"x": 1})],
            ),
            Message(role="tool", content="tool result", tool_call_id="tc-1"),
            Message(role="user", content="Continue"),
        ]
        await client.chat(messages)

        # Assert: textブロックなし、tool_useブロックのみのassistantメッセージ
        call_body = mock_http.post.call_args[1]["json"]
        assistant_msgs = [m for m in call_body["messages"] if m.get("role") == "assistant"]
        assert len(assistant_msgs) == 1
        # content=Noneなのでtextブロックは含まれない
        text_blocks = [b for b in assistant_msgs[0]["content"] if b["type"] == "text"]
        assert len(text_blocks) == 0

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

    @pytest.mark.asyncio
    async def test_request_with_retry_5xx_retry_then_success(
        self, client, mock_rate_limiter, monkeypatch
    ):
        """5xxエラー時に指数バックオフでリトライし成功する"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.headers = {}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.raise_for_status = MagicMock()
        mock_200.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Recovered", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[mock_500, mock_200])
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Hi")]
        response = await client.chat(messages)

        # Assert: 5xx後にリトライして成功
        assert response.content == "Recovered"
        assert mock_http.post.call_count == 2

    @pytest.mark.asyncio
    async def test_request_with_retry_5xx_exhaust_retries(
        self, client, mock_rate_limiter, monkeypatch
    ):
        """5xxエラーがリトライ上限を超えるとHTTPStatusErrorが発生する"""
        import httpx

        from hiveforge.llm.client import MAX_SERVER_ERROR_RETRIES

        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_request = MagicMock()

        def make_5xx():
            resp = MagicMock()
            resp.status_code = 503
            resp.headers = {}
            resp.request = mock_request
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503 Service Unavailable", request=mock_request, response=resp
            )
            return resp

        # MAX_SERVER_ERROR_RETRIES + 1回すべて503
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=[make_5xx() for _ in range(MAX_SERVER_ERROR_RETRIES + 1)]
        )
        client._http_client = mock_http

        # Act & Assert
        with pytest.raises(httpx.HTTPStatusError):
            messages = [Message(role="user", content="Hi")]
            await client.chat(messages)

        # リトライ回数 = MAX_SERVER_ERROR_RETRIES + 1（初回 + リトライ回数）
        assert mock_http.post.call_count == MAX_SERVER_ERROR_RETRIES + 1

    @pytest.mark.asyncio
    async def test_request_with_retry_429_exhaust_retries(
        self, client, mock_rate_limiter, monkeypatch
    ):
        """429エラーがリトライ上限を超えるとHTTPStatusErrorが発生する"""
        import httpx

        from hiveforge.llm.client import MAX_429_RETRIES

        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_request = MagicMock()

        def make_429():
            resp = MagicMock()
            resp.status_code = 429
            resp.headers = {"Retry-After": "1"}
            resp.request = mock_request
            return resp

        # MAX_429_RETRIES + 1回すべて429
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[make_429() for _ in range(MAX_429_RETRIES + 1)])
        client._http_client = mock_http

        # Act & Assert
        with pytest.raises(httpx.HTTPStatusError, match="429リトライ上限超過"):
            messages = [Message(role="user", content="Hi")]
            await client.chat(messages)

        assert mock_http.post.call_count == MAX_429_RETRIES + 1

    @pytest.mark.asyncio
    async def test_request_with_retry_mixed_429_and_5xx(
        self, client, mock_rate_limiter, monkeypatch
    ):
        """429と5xxが混在してもそれぞれ独立したカウンターでリトライする"""
        # Arrange
        monkeypatch.setenv("TEST_API_KEY", "sk-test")

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}

        mock_502 = MagicMock()
        mock_502.status_code = 502
        mock_502.headers = {}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.raise_for_status = MagicMock()
        mock_200.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Finally OK", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
        }

        # 429 → 502 → 200
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=[mock_429, mock_502, mock_200])
        client._http_client = mock_http

        # Act
        messages = [Message(role="user", content="Hi")]
        response = await client.chat(messages)

        # Assert: 429とサーバーエラーを経ても最終的に成功
        assert response.content == "Finally OK"
        assert mock_http.post.call_count == 3
        mock_rate_limiter.handle_429.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_with_retry_retryable_status_codes(
        self, client, mock_rate_limiter, monkeypatch
    ):
        """500, 502, 503, 529がリトライ対象のステータスコードである"""
        from hiveforge.llm.client import _RETRYABLE_STATUS_CODES

        # Assert: リトライ対象のステータスコードが正しく定義されている
        assert {500, 502, 503, 529} == _RETRYABLE_STATUS_CODES


# ==================== run_command_handler テスト ====================


class TestRunCommandHandler:
    """run_command_handlerのテスト"""

    @pytest.mark.asyncio
    async def test_run_simple_command(self):
        """シンプルなコマンドを実行できる"""
        from hiveforge.llm.tools import run_command_handler

        # Act
        result_str = await run_command_handler("echo hello")
        result = json.loads(result_str)

        # Assert
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_run_failing_command(self):
        """失敗するコマンドの結果を取得できる"""
        from hiveforge.llm.tools import run_command_handler

        # Act
        result_str = await run_command_handler("false")
        result = json.loads(result_str)

        # Assert
        assert result["exit_code"] != 0

    @pytest.mark.asyncio
    async def test_list_directory_not_dir(self, tmp_path):
        """ファイルをディレクトリとして開けない"""
        # Arrange
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")

        # Act
        result_str = await list_directory_handler(str(file_path))
        result = json.loads(result_str)

        # Assert
        assert "error" in result
        assert "ディレクトリではありません" in result["error"]
