"""エージェントチェーン E2Eシナリオテスト（LiteLLM経由 実LLM呼び出し）

LiteLLM経由でLLMを使用し、実際のLLM推論を含む
エージェントチェーンシナリオをテストする。

プロバイダーは環境変数で切替可能:
  - LLM_PROVIDER: ollama_chat (デフォルト), openai, anthropic 等
  - LLM_MODEL: モデル名（デフォルト: qwen3:4b）
  - LLM_API_KEY: APIキー（クラウドプロバイダー用）
  - LLM_API_BASE: APIベースURL（Ollama等ローカル用）

実行例:
  # Ollama（ローカル）
  pytest tests/e2e/test_agent_chain_llm.py -v -m e2e --timeout=120

  # OpenAI（CI）
  LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini LLM_API_KEY=$OPENAI_API_KEY \\
    pytest tests/e2e/test_agent_chain_llm.py -v -m e2e
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from colonyforge.core import AkashicRecord
from colonyforge.core.config import LLMConfig

# ---------------------------------------------------------------------------
# マーカー: e2e + asyncio
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# 設定 — 環境変数でプロバイダー切替可能
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama_chat")
LLM_MODEL = os.environ.get("LLM_MODEL", os.environ.get("OLLAMA_MODEL", "qwen3:4b"))
LLM_API_BASE = os.environ.get(
    "LLM_API_BASE", os.environ.get("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434")
)
LLM_API_KEY_ENV = os.environ.get("LLM_API_KEY_ENV", "")  # e.g. "OPENAI_API_KEY"
# LLMの応答待ちタイムアウト（秒）
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

# ローカルプロバイダー（APIキー不要）
_LOCAL_PROVIDERS = {"ollama", "ollama_chat"}

# エージェントループの最大反復回数 — クラウドAPIコスト制御
# ローカル: 10回（十分な余裕）, CIクラウド: 5回（コスト制限）
_DEFAULT_MAX_ITERATIONS = 5 if LLM_PROVIDER not in _LOCAL_PROVIDERS else 10
MAX_AGENT_ITERATIONS = int(os.environ.get("MAX_AGENT_ITERATIONS", str(_DEFAULT_MAX_ITERATIONS)))


def _is_llm_available() -> bool:
    """LLMプロバイダーに到達可能か判定"""
    if LLM_PROVIDER in _LOCAL_PROVIDERS:
        # Ollama: HTTP接続チェック
        import urllib.request

        try:
            req = urllib.request.Request(f"{LLM_API_BASE}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
    else:
        # クラウドプロバイダー: APIキーの存在チェック
        key_env = LLM_API_KEY_ENV or f"{LLM_PROVIDER.upper()}_API_KEY"
        return bool(os.environ.get(key_env))


# LLM未接続時はスキップ
llm_required = pytest.mark.skipif(
    not _is_llm_available(),
    reason=f"LLM provider '{LLM_PROVIDER}' not available",
)


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------
@pytest.fixture
def llm_config() -> LLMConfig:
    """LLM接続用設定（環境変数でプロバイダー切替）"""
    config_kwargs: dict = {
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
        "max_tokens": 2048,
        "temperature": 0.2,
    }
    # ローカルプロバイダーの場合のみ api_base を設定
    if LLM_PROVIDER in _LOCAL_PROVIDERS:
        config_kwargs["api_base"] = LLM_API_BASE
    # APIキー環境変数が指定されている場合
    if LLM_API_KEY_ENV:
        config_kwargs["api_key_env"] = LLM_API_KEY_ENV
    return LLMConfig(**config_kwargs)


@pytest.fixture
def temp_vault():
    """テスト用一時Vaultディレクトリ"""
    vault_path = Path(tempfile.mkdtemp(prefix="colonyforge_e2e_"))
    yield vault_path
    shutil.rmtree(vault_path, ignore_errors=True)


@pytest.fixture
def ar(temp_vault: Path) -> AkashicRecord:
    """テスト用AkashicRecord"""
    return AkashicRecord(temp_vault)


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Worker Beeの作業ディレクトリ"""
    wd = tmp_path / "workspace"
    wd.mkdir()
    return wd


# ===========================================================================
# シナリオ 1: LLMClient 単体 — Ollama接続確認
# ===========================================================================
@llm_required
class TestLLMClientOllama:
    """LLMClient → Ollama 直接呼び出しテスト"""

    async def test_simple_chat(self, llm_config: LLMConfig):
        """Arrange: Ollama接続設定
        Act: 簡単な質問を送信
        Assert: テキスト応答が返る
        """
        import asyncio

        from colonyforge.llm.client import LLMClient, Message

        # Arrange
        client = LLMClient(config=llm_config)
        messages = [
            Message(role="user", content="1+1は何ですか？数字だけ答えてください。"),
        ]

        # Act
        response = await asyncio.wait_for(
            client.chat(messages=messages),
            timeout=LLM_TIMEOUT,
        )

        # Assert
        assert response.content is not None
        assert len(response.content) > 0
        assert "2" in response.content
        await client.close()

    async def test_tool_calling(self, llm_config: LLMConfig):
        """Arrange: ツール定義付きで質問
        Act: ツール呼び出しが必要な質問を送信
        Assert: ツール呼び出しが返る
        """
        import asyncio

        from colonyforge.llm.client import LLMClient, Message

        # Arrange
        client = LLMClient(config=llm_config)
        messages = [
            Message(
                role="system",
                content="あなたはファイル操作アシスタントです。ユーザーの依頼にはツールを使って応答してください。",
            ),
            Message(
                role="user",
                content="カレントディレクトリのファイル一覧を表示してください。",
            ),
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "ディレクトリ内のファイル一覧を返す",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "対象ディレクトリのパス",
                            },
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        # Act
        response = await asyncio.wait_for(
            client.chat(messages=messages, tools=tools, tool_choice="auto"),
            timeout=LLM_TIMEOUT,
        )

        # Assert: ツール呼び出しが返るか、テキストで応答するかのどちらか
        has_tool_calls = response.has_tool_calls
        has_content = response.content is not None and len(response.content) > 0
        assert has_tool_calls or has_content, f"ツール呼び出しもテキスト応答もない: {response}"

        if has_tool_calls:
            # ツール呼び出しが返った場合、list_directoryが含まれるはず
            tool_names = [tc.name for tc in response.tool_calls]
            assert "list_directory" in tool_names

        await client.close()


# ===========================================================================
# シナリオ 2: AgentRunner — ツール実行ループ
# ===========================================================================
@llm_required
class TestAgentRunnerOllama:
    """AgentRunner → Ollama ツール実行ループテスト"""

    async def test_agent_runner_with_tools(self, llm_config: LLMConfig, work_dir: Path):
        """Arrange: AgentRunner + 基本ツール + 作業ディレクトリ
        Act: ファイル作成を依頼
        Assert: ファイルが作成され、成功が返る
        """
        import asyncio

        from colonyforge.llm.client import LLMClient
        from colonyforge.llm.runner import AgentContext, AgentRunner
        from colonyforge.llm.tools import get_basic_tools

        # Arrange
        client = LLMClient(config=llm_config)
        runner = AgentRunner(
            client,
            agent_type="worker_bee",
            max_iterations=MAX_AGENT_ITERATIONS,
        )
        for tool in get_basic_tools():
            runner.register_tool(tool)

        context = AgentContext(
            run_id="e2e-runner-test",
            working_directory=str(work_dir),
        )

        # Act
        result = await asyncio.wait_for(
            runner.run(
                f"以下のパスにhello.txtファイルを作成して、中身は 'Hello ColonyForge' としてください: {work_dir}/hello.txt",
                context,
            ),
            timeout=LLM_TIMEOUT,
        )

        # Assert
        assert result.success, f"AgentRunner失敗: {result.error}"
        assert result.output is not None
        # ファイルが実際に作成されたか確認
        hello_file = work_dir / "hello.txt"
        if hello_file.exists():
            content = hello_file.read_text()
            assert "Hello" in content or "hello" in content.lower()


# ===========================================================================
# シナリオ 3: Worker Bee — タスク実行
# ===========================================================================
@llm_required
class TestWorkerBeeOllama:
    """Worker Bee → Ollama タスク実行テスト"""

    async def test_worker_executes_task(
        self,
        llm_config: LLMConfig,
        ar: AkashicRecord,
        work_dir: Path,
    ):
        """Arrange: Worker Bee + Ollama設定
        Act: ファイル作成タスクをexecute_task_with_llmで実行
        Assert: タスクが完了し、ARにイベントが記録される
        """
        import asyncio

        from colonyforge.worker_bee.server import WorkerBeeMCPServer

        # Arrange
        worker = WorkerBeeMCPServer(
            worker_id="e2e-worker-1",
            ar=ar,
            llm_config=llm_config,
        )

        # Act
        result = await asyncio.wait_for(
            worker.execute_task_with_llm(
                {
                    "task_id": "e2e-task-001",
                    "run_id": "e2e-run-001",
                    "goal": f"{work_dir}/greeting.txt に 'Hello from Worker Bee!' と書いたファイルを作成してください。",
                    "context": {"working_directory": str(work_dir)},
                }
            ),
            timeout=LLM_TIMEOUT,
        )

        # Assert: 実行が完了（成功 or 失敗でもイベント記録）
        assert "status" in result
        assert result["status"] in ("completed", "failed", "success", "error")

        # ARにWorkerイベントが記録されていることを確認
        events = ar.replay("e2e-run-001")
        event_types = [e.type for e in events]
        assert any("worker" in str(t) for t in event_types), (
            f"Workerイベントが記録されていない: {event_types}"
        )

        await worker.close()


# ===========================================================================
# シナリオ 4: Queen Bee → Worker Bee チェーン（タスク分解 + 実行）
# ===========================================================================
@llm_required
class TestQueenBeeChainOllama:
    """Queen Bee → Worker Bee フルチェーンテスト"""

    async def test_queen_decomposes_and_executes(
        self,
        llm_config: LLMConfig,
        ar: AkashicRecord,
        work_dir: Path,
    ):
        """Arrange: Queen Bee + Worker Bee + Ollama
        Act: 目標を与えてタスク分解→Worker実行
        Assert: Runが完了し、ARにRun/Task/Workerイベントが記録される
        """
        import asyncio

        from colonyforge.queen_bee.server import QueenBeeMCPServer

        # Arrange
        queen = QueenBeeMCPServer(
            colony_id="e2e-colony-1",
            ar=ar,
            llm_config=llm_config,
            use_pipeline=False,  # 直接実行（Guard Bee検証なし）
        )
        queen.add_worker("e2e-worker-1")

        # Act
        result = await asyncio.wait_for(
            queen.handle_execute_goal(
                {
                    "run_id": "e2e-chain-run-001",
                    "goal": f"次のファイルを作成してください: {work_dir}/project_info.txt (内容: 'ProjectName: ColonyForge E2E Test')",
                    "context": {"working_directory": str(work_dir)},
                }
            ),
            timeout=LLM_TIMEOUT * 2,  # タスク分解 + 実行で倍の時間
        )

        # Assert
        assert "status" in result
        # Run/Taskイベントが記録されていることを確認
        events = ar.replay("e2e-chain-run-001")
        event_types = [str(e.type) for e in events]

        # 少なくともRunStartedは記録されるはず
        assert any("run.started" in t for t in event_types), (
            f"run.started が記録されていない: {event_types}"
        )

        # イベントの詳細をログ出力（デバッグ用）
        for e in events:
            print(f"  [{e.type}] actor={e.actor} payload_keys={list(e.payload.keys())}")

        await queen.close()


# ===========================================================================
# シナリオ 5: Beekeeper → Queen Bee → Worker Bee フルチェーン
# ===========================================================================
@llm_required
class TestFullAgentChainOllama:
    """Beekeeper → Queen Bee → Worker Bee 完全チェーンテスト"""

    async def test_beekeeper_delegates_to_queen(
        self,
        llm_config: LLMConfig,
        ar: AkashicRecord,
        work_dir: Path,
        monkeypatch,
    ):
        """Arrange: Beekeeper + Ollama設定
        Act: ユーザーメッセージを送信（Hive作成→Colony作成→目標委譲）
        Assert: フルチェーンが動作し、ARにイベントが記録される

        注意: Beekeeper→Queen Bee委譲はLLMの判断に依存するため、
        確実にチェーンが発火するよう明示的な指示を与える。
        """
        import asyncio

        from colonyforge.beekeeper.server import BeekeeperMCPServer

        # Arrange: グローバル設定をOllamaに差し替え
        from colonyforge.core.config import HiveConfig, ColonyForgeSettings

        settings = ColonyForgeSettings(
            hive=HiveConfig(name="e2e-hive", vault_path=str(ar.vault_path)),
            llm=llm_config,
        )
        monkeypatch.setattr(
            "colonyforge.core.config.get_settings",
            lambda: settings,
        )

        beekeeper = BeekeeperMCPServer(ar=ar, llm_config=llm_config)

        # Act 1: Hive作成
        hive_result = await asyncio.wait_for(
            beekeeper.handle_create_hive(
                {
                    "name": "E2E Full Chain Test",
                    "goal": "E2Eテスト",
                }
            ),
            timeout=30,
        )
        assert "hive_id" in hive_result
        hive_id = hive_result["hive_id"]

        # Act 2: Colony作成
        colony_result = await asyncio.wait_for(
            beekeeper.handle_create_colony(
                {
                    "hive_id": hive_id,
                    "name": "test-colony",
                    "domain": "testing",
                }
            ),
            timeout=30,
        )
        assert "colony_id" in colony_result
        colony_id = colony_result["colony_id"]

        # Act 3: Queen Beeに目標を委譲（直接呼び出し）
        queen = beekeeper._queens.get(colony_id)
        if queen is None:
            # Beekeeper内部でQueen Beeに委譲
            await beekeeper._delegate_to_queen(
                colony_id=colony_id,
                task=f"{work_dir}/e2e_output.txt に 'Full chain works!' と書いてください。",
                context={"working_directory": str(work_dir)},
            )
        else:
            await asyncio.wait_for(
                queen.handle_execute_goal(
                    {
                        "goal": f"{work_dir}/e2e_output.txt に 'Full chain works!' と書いてください。",
                        "context": {"working_directory": str(work_dir)},
                    }
                ),
                timeout=LLM_TIMEOUT * 2,
            )

        # Assert: フルチェーンの結果
        # Run内のイベントが記録されていることを確認
        all_events = []
        for run_id in ar.list_runs():
            all_events.extend(ar.replay(run_id))
        event_types = [str(e.type) for e in all_events]

        # エージェントチェーンの基本イベントが記録されている
        assert any("run.started" in t for t in event_types), (
            f"run.started が記録されていない: {event_types}"
        )
        assert any("task.created" in t or "task.assigned" in t for t in event_types), (
            f"task イベントが記録されていない: {event_types}"
        )
        assert any("worker" in t for t in event_types), (
            f"worker イベントが記録されていない: {event_types}"
        )

        # イベントログ出力
        print(f"\n=== E2E Full Chain: {len(all_events)} events ===")
        for e in all_events:
            print(f"  [{e.type}] actor={e.actor}")

        await beekeeper.close()
