#!/usr/bin/env python3
"""Beekeeper → Queen Bee → Worker Bee タスク分解フロー 実験スクリプト

実際のLLM (Ollama or OpenAI) を使って、フルチェーンの動作を確認する。

=== 使い方 ===

# 1. Ollama (devcontainer内) — まずモデルをpullする
docker exec colonyforge-dev-ollama ollama pull qwen3:4b

python scripts/experiment_beekeeper_chain.py

# 2. Ollama (カスタムモデル)
LLM_MODEL=llama3.2:3b python scripts/experiment_beekeeper_chain.py

# 3. OpenAI
LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini LLM_API_KEY_ENV=OPENAI_API_KEY \
    python scripts/experiment_beekeeper_chain.py

# 4. 個別シナリオのみ実行
python scripts/experiment_beekeeper_chain.py --scenario 1    # LLM接続確認
python scripts/experiment_beekeeper_chain.py --scenario 2    # タスク分解のみ
python scripts/experiment_beekeeper_chain.py --scenario 3    # Worker単体
python scripts/experiment_beekeeper_chain.py --scenario 4    # Queen→Worker
python scripts/experiment_beekeeper_chain.py --scenario 5    # Beekeeper→Queen→Worker
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import textwrap
import urllib.request
from pathlib import Path

# ── プロジェクトルートをPATHに追加 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from colonyforge.core import AkashicRecord
from colonyforge.core.config import LLMConfig

# ─────────────────────────────────────────────────────────────
# 設定 — 環境変数でプロバイダー切替
# ─────────────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama_chat")
LLM_MODEL = os.environ.get("LLM_MODEL", os.environ.get("OLLAMA_MODEL", "qwen3:4b"))
LLM_API_BASE = os.environ.get(
    "LLM_API_BASE",
    os.environ.get("OLLAMA_BASE_URL", "http://colonyforge-dev-ollama:11434"),
)
LLM_API_KEY_ENV = os.environ.get("LLM_API_KEY_ENV", "")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))
MAX_AGENT_ITERATIONS = int(os.environ.get("MAX_AGENT_ITERATIONS", "10"))

_LOCAL_PROVIDERS = {"ollama", "ollama_chat"}

# ─────────────────────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("experiment")


def banner(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def sub_banner(title: str) -> None:
    print(f"\n--- {title} ---")


def print_result(label: str, value: object) -> None:
    if isinstance(value, dict):
        print(f"  {label}:")
        for k, v in value.items():
            vstr = str(v)[:200]
            print(f"    {k}: {vstr}")
    else:
        print(f"  {label}: {value}")


def make_llm_config() -> LLMConfig:
    """環境変数からLLMConfigを生成"""
    # gpt-5 は temperature=1 のみサポート
    model_lower = LLM_MODEL.lower()
    is_gpt5 = model_lower.startswith("gpt-5") and "gpt-5.1" not in model_lower
    kwargs: dict = {
        "provider": LLM_PROVIDER,
        "model": LLM_MODEL,
        "max_tokens": 2048,
        "temperature": 1.0 if is_gpt5 else 0.2,
    }
    if LLM_PROVIDER in _LOCAL_PROVIDERS:
        kwargs["api_base"] = LLM_API_BASE
    if LLM_API_KEY_ENV:
        kwargs["api_key_env"] = LLM_API_KEY_ENV
    return LLMConfig(**kwargs)


def check_llm_available() -> bool:
    """LLMプロバイダーに到達可能か判定"""
    if LLM_PROVIDER in _LOCAL_PROVIDERS:
        try:
            req = urllib.request.Request(f"{LLM_API_BASE}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                if models:
                    print(f"  Ollama 利用可能モデル: {models}")
                else:
                    print(f"  ⚠ Ollama にモデルがありません。")
                    print(f"    → docker exec colonyforge-dev-ollama ollama pull {LLM_MODEL}")
                    return False
                # 指定モデルが存在するか
                model_base = LLM_MODEL.split(":")[0]
                found = any(model_base in m for m in models)
                if not found:
                    print(f"  ⚠ モデル '{LLM_MODEL}' が見つかりません。")
                    print(f"    利用可能: {models}")
                    print(f"    → docker exec colonyforge-dev-ollama ollama pull {LLM_MODEL}")
                    return False
                return True
        except Exception as e:
            print(f"  ✗ Ollama接続失敗: {e}")
            print(f"    URL: {LLM_API_BASE}")
            return False
    else:
        key_env = LLM_API_KEY_ENV or f"{LLM_PROVIDER.upper()}_API_KEY"
        if os.environ.get(key_env):
            print(f"  {key_env} はセットされています")
            return True
        print(f"  ✗ {key_env} が未設定です")
        return False


def make_temp_vault() -> Path:
    return Path(tempfile.mkdtemp(prefix="cf_experiment_"))


def make_work_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="cf_workspace_"))
    return d


# ─────────────────────────────────────────────────────────────
# シナリオ 1: LLMClient 接続確認
# ─────────────────────────────────────────────────────────────
async def scenario_1_llm_connection() -> bool:
    """LLMClient で単純なチャットを送信し、応答を確認"""
    banner("シナリオ 1: LLMClient 接続確認")
    from colonyforge.llm.client import LLMClient, Message

    config = make_llm_config()
    print_result(
        "LLMConfig",
        {
            "provider": config.provider,
            "model": config.model,
            "api_base": config.api_base,
        },
    )

    client = LLMClient(config=config)

    sub_banner("1-a: 単純なチャット")
    messages = [
        Message(role="user", content="1+1は何ですか？数字だけ答えてください。"),
    ]
    try:
        response = await asyncio.wait_for(
            client.chat(messages=messages),
            timeout=LLM_TIMEOUT,
        )
        print(f"  応答: {response.content}")
        print(f"  usage: {response.usage}")
        assert response.content is not None
        print("  ✓ 成功")
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        await client.close()
        return False

    sub_banner("1-b: ツール呼び出し")
    messages2 = [
        Message(
            role="system", content="ファイル操作アシスタントです。ツールを使って応答してください。"
        ),
        Message(role="user", content="カレントディレクトリのファイル一覧を表示してください。"),
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
                        "path": {"type": "string", "description": "対象ディレクトリ"},
                    },
                    "required": ["path"],
                },
            },
        }
    ]
    try:
        response2 = await asyncio.wait_for(
            client.chat(messages=messages2, tools=tools, tool_choice="auto"),
            timeout=LLM_TIMEOUT,
        )
        if response2.has_tool_calls:
            for tc in response2.tool_calls:
                print(f"  ツール呼び出し: {tc.name}({tc.arguments})")
        else:
            print(f"  テキスト応答: {(response2.content or '')[:100]}")
        print("  ✓ 成功")
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        await client.close()
        return False

    await client.close()
    return True


# ─────────────────────────────────────────────────────────────
# シナリオ 2: TaskPlanner タスク分解
# ─────────────────────────────────────────────────────────────
async def scenario_2_task_planning() -> bool:
    """TaskPlannerでゴールをタスクに分解"""
    banner("シナリオ 2: TaskPlanner タスク分解")
    from colonyforge.llm.client import LLMClient
    from colonyforge.queen_bee.planner import TaskPlanner

    config = make_llm_config()
    client = LLMClient(config=config)
    planner = TaskPlanner(client)

    goal = (
        "Pythonで簡単なTODOアプリを作成してください。todo.pyとtest_todo.pyの2ファイルを作成する。"
    )
    sub_banner(f"ゴール: {goal}")

    try:
        plan = await asyncio.wait_for(
            planner.plan(goal),
            timeout=LLM_TIMEOUT,
        )
        print(f"\n  タスク数: {len(plan.tasks)}")
        print(f"  reasoning: {plan.reasoning}")
        print(f"  並列実行可能: {plan.is_parallelizable()}")

        exec_order = plan.execution_order()
        for i, layer in enumerate(exec_order):
            print(f"\n  レイヤー {i} (並列実行):")
            for tid in layer:
                task = next(t for t in plan.tasks if t.task_id == tid)
                deps = f" (depends_on: {task.depends_on})" if task.depends_on else ""
                print(f"    [{task.task_id}] {task.goal}{deps}")

        print("\n  ✓ 成功")
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        import traceback

        traceback.print_exc()
        await client.close()
        return False

    await client.close()
    return True


# ─────────────────────────────────────────────────────────────
# シナリオ 3: Worker Bee 単体タスク実行
# ─────────────────────────────────────────────────────────────
async def scenario_3_worker_execution() -> bool:
    """Worker Beeで1タスクをLLM実行"""
    banner("シナリオ 3: Worker Bee 単体タスク実行")
    from colonyforge.worker_bee.server import WorkerBeeMCPServer

    config = make_llm_config()
    vault = make_temp_vault()
    work_dir = make_work_dir()
    ar = AkashicRecord(vault)

    worker = WorkerBeeMCPServer(
        worker_id="exp-worker-1",
        ar=ar,
        llm_config=config,
    )

    goal = f"{work_dir}/hello.txt に 'Hello from Worker Bee!' と書いたファイルを作成してください。"
    sub_banner(f"ゴール: {goal}")

    try:
        result = await asyncio.wait_for(
            worker.execute_task_with_llm(
                {
                    "task_id": "exp-task-001",
                    "run_id": "exp-run-001",
                    "goal": goal,
                    "context": {"working_directory": str(work_dir)},
                }
            ),
            timeout=LLM_TIMEOUT,
        )

        print_result("実行結果", result)

        # ARイベント確認
        events = list(ar.replay("exp-run-001"))
        print(f"\n  ARイベント数: {len(events)}")
        for e in events:
            print(f"    [{e.type}] actor={e.actor}")

        # ファイル確認
        hello_file = work_dir / "hello.txt"
        if hello_file.exists():
            content = hello_file.read_text()
            print(f"\n  ファイル内容: {content}")
            print("  ✓ ファイル作成成功")
        else:
            print("  ⚠ ファイルは作成されませんでした")
            # 作業ディレクトリの中身を表示
            files = list(work_dir.iterdir())
            print(f"  作業ディレクトリ内容: {[f.name for f in files]}")

    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        import traceback

        traceback.print_exc()
        await worker.close()
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        return False

    await worker.close()
    shutil.rmtree(vault, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    return True


# ─────────────────────────────────────────────────────────────
# シナリオ 4: Queen Bee → Worker Bee チェーン
# ─────────────────────────────────────────────────────────────
async def scenario_4_queen_worker_chain() -> bool:
    """Queen BeeがLLMでタスク分解し、Worker Beeで実行"""
    banner("シナリオ 4: Queen Bee → Worker Bee チェーン")
    from colonyforge.queen_bee.server import QueenBeeMCPServer

    config = make_llm_config()
    vault = make_temp_vault()
    work_dir = make_work_dir()
    ar = AkashicRecord(vault)

    queen = QueenBeeMCPServer(
        colony_id="exp-colony-1",
        ar=ar,
        llm_config=config,
        use_pipeline=False,  # 直接実行（Guard Bee検証なし）
    )
    queen.add_worker("exp-worker-1")

    goal = (
        f"次のファイルを作成してください: "
        f"{work_dir}/project_info.txt "
        f"(内容: 'ProjectName: ColonyForge Experiment')"
    )
    sub_banner(f"ゴール: {goal}")

    try:
        result = await asyncio.wait_for(
            queen.handle_execute_goal(
                {
                    "run_id": "exp-chain-001",
                    "goal": goal,
                    "context": {"working_directory": str(work_dir)},
                }
            ),
            timeout=LLM_TIMEOUT * 2,
        )

        print_result("実行結果", result)

        # ARイベントの詳細
        events = list(ar.replay("exp-chain-001"))
        print(f"\n  ARイベント数: {len(events)}")
        for e in events:
            payload_keys = list(e.payload.keys()) if e.payload else []
            print(f"    [{e.type}] actor={e.actor} keys={payload_keys}")

        # ファイル確認
        info_file = work_dir / "project_info.txt"
        if info_file.exists():
            content = info_file.read_text()
            print(f"\n  ファイル内容: {content}")
            print("  ✓ ファイル作成成功")
        else:
            print("  ⚠ ファイルは作成されませんでした")
            files = list(work_dir.iterdir())
            print(f"  作業ディレクトリ: {[f.name for f in files]}")

        status = result.get("status", "unknown")
        if status == "completed":
            print("\n  ✓ チェーン全体成功")
        elif status == "partial":
            print("\n  △ 一部タスク成功")
        else:
            print(f"\n  ✗ チェーン失敗: status={status}")

    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        import traceback

        traceback.print_exc()
        await queen.close()
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        return False

    await queen.close()
    shutil.rmtree(vault, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    return True


# ─────────────────────────────────────────────────────────────
# シナリオ 5: Beekeeper → Queen Bee → Worker Bee フルチェーン
# ─────────────────────────────────────────────────────────────
async def scenario_5_full_chain() -> bool:
    """Beekeeper経由でフルチェーンを実行"""
    banner("シナリオ 5: Beekeeper → Queen Bee → Worker Bee フルチェーン")
    from unittest.mock import patch

    from colonyforge.beekeeper.server import BeekeeperMCPServer
    from colonyforge.core.config import ColonyForgeSettings, HiveConfig

    config = make_llm_config()
    vault = make_temp_vault()
    work_dir = make_work_dir()
    ar = AkashicRecord(vault)

    # グローバル設定を差し替え
    settings = ColonyForgeSettings(
        hive=HiveConfig(name="experiment-hive", vault_path=str(vault)),
        llm=config,
    )

    with patch(
        "colonyforge.core.config.get_settings",
        return_value=settings,
    ):
        beekeeper = BeekeeperMCPServer(ar=ar, llm_config=config)

        try:
            # Step 1: Hive作成
            sub_banner("Step 1: Hive作成")
            hive_result = await asyncio.wait_for(
                beekeeper.handle_create_hive({"name": "Experiment Hive", "goal": "タスク分解実験"}),
                timeout=30,
            )
            print_result("Hive", hive_result)
            hive_id = hive_result["hive_id"]

            # Step 2: Colony作成
            sub_banner("Step 2: Colony作成")
            colony_result = await asyncio.wait_for(
                beekeeper.handle_create_colony(
                    {
                        "hive_id": hive_id,
                        "name": "dev-colony",
                        "domain": "development",
                    }
                ),
                timeout=30,
            )
            print_result("Colony", colony_result)
            colony_id = colony_result["colony_id"]

            # Step 3: Queen Beeにタスク委譲
            sub_banner("Step 3: Queen Beeにタスク委譲")
            task = (
                f"{work_dir}/experiment_output.txt に "
                f"'Full chain experiment successful!' と書いてください。"
            )
            print(f"  タスク: {task}")

            delegation_result = await asyncio.wait_for(
                beekeeper._delegate_to_queen(
                    colony_id=colony_id,
                    task=task,
                    context={"working_directory": str(work_dir)},
                ),
                timeout=LLM_TIMEOUT * 2,
            )
            print(f"  委譲結果: {delegation_result}")

            # Step 4: 結果確認
            sub_banner("Step 4: 結果確認")

            # ARイベント
            all_events = []
            run_ids = ar.list_runs()
            print(f"  Run数: {len(run_ids)}")
            for run_id in run_ids:
                events = list(ar.replay(run_id))
                all_events.extend(events)
                print(f"\n  Run {run_id} ({len(events)} events):")
                for e in events:
                    print(f"    [{e.type}] actor={e.actor}")

            event_types = [str(e.type) for e in all_events]
            checks = {
                "run.started": any("run.started" in t for t in event_types),
                "task.created": any("task.created" in t for t in event_types),
                "worker events": any("worker" in t for t in event_types),
            }
            print(f"\n  イベントチェック:")
            for check, passed in checks.items():
                status = "✓" if passed else "✗"
                print(f"    {status} {check}")

            # ファイル確認
            output_file = work_dir / "experiment_output.txt"
            if output_file.exists():
                content = output_file.read_text()
                print(f"\n  出力ファイル: {content}")
                print("  ✓ フルチェーン成功!")
                success = True
            else:
                print("  ⚠ 出力ファイルなし")
                files = list(work_dir.iterdir())
                print(f"  作業ディレクトリ: {[f.name for f in files]}")
                success = "タスク完了" in delegation_result

        except Exception as e:
            print(f"  ✗ 失敗: {e}")
            import traceback

            traceback.print_exc()
            success = False

        await beekeeper.close()

    shutil.rmtree(vault, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    return success


# ─────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────
async def main(scenarios: list[int] | None = None) -> None:
    banner("ColonyForge エージェントチェーン実験")
    print(
        textwrap.dedent(f"""\
        プロバイダー : {LLM_PROVIDER}
        モデル       : {LLM_MODEL}
        API Base     : {LLM_API_BASE if LLM_PROVIDER in _LOCAL_PROVIDERS else "(default)"}
        タイムアウト : {LLM_TIMEOUT}秒
        最大反復     : {MAX_AGENT_ITERATIONS}回
    """)
    )

    # 接続チェック
    sub_banner("LLM接続チェック")
    if not check_llm_available():
        print("\n✗ LLMに接続できません。設定を確認してください。")
        print("\n=== Ollama セットアップ手順 ===")
        print("  1. docker exec colonyforge-dev-ollama ollama pull qwen3:4b")
        print("  2. python scripts/experiment_beekeeper_chain.py")
        print("\n=== OpenAI ===")
        print("  1. export OPENAI_API_KEY=sk-...")
        print(
            "  2. LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini python scripts/experiment_beekeeper_chain.py"
        )
        return

    # 実行するシナリオを決定
    all_scenarios = {
        1: ("LLMClient 接続確認", scenario_1_llm_connection),
        2: ("TaskPlanner タスク分解", scenario_2_task_planning),
        3: ("Worker Bee 単体タスク実行", scenario_3_worker_execution),
        4: ("Queen → Worker チェーン", scenario_4_queen_worker_chain),
        5: ("Beekeeper → Queen → Worker フルチェーン", scenario_5_full_chain),
    }

    to_run = scenarios or list(all_scenarios.keys())
    results: dict[int, bool] = {}

    for num in to_run:
        if num not in all_scenarios:
            print(f"  ⚠ シナリオ {num} は存在しません (1-5)")
            continue
        name, func = all_scenarios[num]
        try:
            results[num] = await func()
        except KeyboardInterrupt:
            print("\n\n中断されました")
            results[num] = False
            break
        except Exception as e:
            print(f"\n  ✗ 未処理例外: {e}")
            import traceback

            traceback.print_exc()
            results[num] = False

    # サマリー
    banner("結果サマリー")
    for num in to_run:
        if num in results:
            name = all_scenarios[num][0]
            status = "✓ PASS" if results[num] else "✗ FAIL"
            print(f"  {status}  シナリオ {num}: {name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {passed}/{total} 成功")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ColonyForge エージェントチェーン実験")
    parser.add_argument(
        "--scenario",
        "-s",
        type=int,
        action="append",
        help="実行するシナリオ番号 (1-5)。複数指定可。省略時は全実行。",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細ログを表示",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(main(args.scenario))
