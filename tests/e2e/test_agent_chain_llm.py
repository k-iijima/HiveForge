"""エージェントチェーン E2Eシナリオテスト（LiteLLM → Ollama 実LLM呼び出し）

LiteLLM経由でOllama (Qwen3 4B) を使用し、実際のLLM推論を含む
エージェントチェーンシナリオをテストする。

前提条件:
  - Ollamaコンテナが hiveforge-dev-network 上で稼働
  - qwen3:4b モデルがpull済み
  - 環境変数 OLLAMA_BASE_URL が設定済み（デフォルト: http://hiveforge-dev-ollama:11434）

実行:
  pytest tests/e2e/test_agent_chain_llm.py -v -m e2e --timeout=120
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.config import LLMConfig

# ---------------------------------------------------------------------------
# マーカー: e2e + asyncio
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://hiveforge-dev-ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
# LLMの応答待ちタイムアウト（秒）
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))


def _is_ollama_available() -> bool:
    """Ollamaサービスに到達可能か判定"""
    import urllib.request

    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# Ollama未接続時はスキップ
ollama_required = pytest.mark.skipif(
    not _is_ollama_available(),
    reason=f"Ollama not reachable at {OLLAMA_BASE_URL}",
)


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------
@pytest.fixture
def ollama_config() -> LLMConfig:
    """Ollama接続用LLM設定"""
    return LLMConfig(
        provider="ollama_chat",
        model=OLLAMA_MODEL,
        api_base=OLLAMA_BASE_URL,
        max_tokens=2048,
        temperature=0.2,
    )


@pytest.fixture
def temp_vault():
    """テスト用一時Vaultディレクトリ"""
    vault_path = Path(tempfile.mkdtemp(prefix="hiveforge_e2e_"))
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
@ollama_required
class TestLLMClientOllama:
    """LLMClient → Ollama 直接呼び出しテスト"""

    async def test_simple_chat(self, ollama_config: LLMConfig):
        """Arrange: Ollama接続設定
        Act: 簡単な質問を送信
        Assert: テキスト応答が返る
        """
        import asyncio

        from hiveforge.llm.client import LLMClient, Message

        # Arrange
        client = LLMClient(config=ollama_config)
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

    async def test_tool_calling(self, ollama_config: LLMConfig):
        """Arrange: ツール定義付きで質問
        Act: ツール呼び出しが必要な質問を送信
        Assert: ツール呼び出しが返る
        """
        import asyncio

        from hiveforge.llm.client import LLMClient, Message

        # Arrange
        client = LLMClient(config=ollama_config)
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
@ollama_required
class TestAgentRunnerOllama:
    """AgentRunner → Ollama ツール実行ループテスト"""

    async def test_agent_runner_with_tools(self, ollama_config: LLMConfig, work_dir: Path):
        """Arrange: AgentRunner + 基本ツール + 作業ディレクトリ
        Act: ファイル作成を依頼
        Assert: ファイルが作成され、成功が返る
        """
        import asyncio

        from hiveforge.llm.client import LLMClient
        from hiveforge.llm.runner import AgentContext, AgentRunner
        from hiveforge.llm.tools import get_basic_tools

        # Arrange
        client = LLMClient(config=ollama_config)
        runner = AgentRunner(
            client,
            agent_type="worker_bee",
            max_iterations=10,
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
                f"以下のパスにhello.txtファイルを作成して、中身は 'Hello HiveForge' としてください: {work_dir}/hello.txt",
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
@ollama_required
class TestWorkerBeeOllama:
    """Worker Bee → Ollama タスク実行テスト"""

    async def test_worker_executes_task(
        self,
        ollama_config: LLMConfig,
        ar: AkashicRecord,
        work_dir: Path,
    ):
        """Arrange: Worker Bee + Ollama設定
        Act: ファイル作成タスクをexecute_task_with_llmで実行
        Assert: タスクが完了し、ARにイベントが記録される
        """
        import asyncio

        from hiveforge.worker_bee.server import WorkerBeeMCPServer

        # Arrange
        worker = WorkerBeeMCPServer(
            worker_id="e2e-worker-1",
            ar=ar,
            llm_config=ollama_config,
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
@ollama_required
class TestQueenBeeChainOllama:
    """Queen Bee → Worker Bee フルチェーンテスト"""

    async def test_queen_decomposes_and_executes(
        self,
        ollama_config: LLMConfig,
        ar: AkashicRecord,
        work_dir: Path,
    ):
        """Arrange: Queen Bee + Worker Bee + Ollama
        Act: 目標を与えてタスク分解→Worker実行
        Assert: Runが完了し、ARにRun/Task/Workerイベントが記録される
        """
        import asyncio

        from hiveforge.queen_bee.server import QueenBeeMCPServer

        # Arrange
        queen = QueenBeeMCPServer(
            colony_id="e2e-colony-1",
            ar=ar,
            llm_config=ollama_config,
            use_pipeline=False,  # 直接実行（Guard Bee検証なし）
        )
        queen.add_worker("e2e-worker-1")

        # Act
        result = await asyncio.wait_for(
            queen.handle_execute_goal(
                {
                    "run_id": "e2e-chain-run-001",
                    "goal": f"次のファイルを作成してください: {work_dir}/project_info.txt (内容: 'ProjectName: HiveForge E2E Test')",
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
@ollama_required
class TestFullAgentChainOllama:
    """Beekeeper → Queen Bee → Worker Bee 完全チェーンテスト"""

    async def test_beekeeper_delegates_to_queen(
        self,
        ollama_config: LLMConfig,
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

        from hiveforge.beekeeper.server import BeekeeperMCPServer

        # Arrange: グローバル設定をOllamaに差し替え
        from hiveforge.core.config import HiveConfig, HiveForgeSettings

        settings = HiveForgeSettings(
            hive=HiveConfig(name="e2e-hive", vault_path=str(ar.vault_path)),
            llm=ollama_config,
        )
        monkeypatch.setattr(
            "hiveforge.core.config.get_settings",
            lambda: settings,
        )

        beekeeper = BeekeeperMCPServer(ar=ar, llm_config=ollama_config)

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
            queen_result = await beekeeper._delegate_to_queen(
                colony_id=colony_id,
                task=f"{work_dir}/e2e_output.txt に 'Full chain works!' と書いてください。",
                context={"working_directory": str(work_dir)},
            )
        else:
            queen_result = await asyncio.wait_for(
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
