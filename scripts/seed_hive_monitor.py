#!/usr/bin/env python3
"""Hive Monitor テストデータ投入スクリプト

APIサーバーにHive/Colony/Agentの階層データを投入し、
リアルタイムにアクティビティイベントを発生させて
Hive Monitorの動作確認を可能にする。

使い方:
  1. 別ターミナルでAPIサーバーを起動:
     uvicorn hiveforge.api.server:app --reload

  2. このスクリプトを実行:
     python scripts/seed_hive_monitor.py
"""

import asyncio
import os
import random
import sys

# srcをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hiveforge.core.activity_bus import (
    ActivityBus,
    ActivityEvent,
    ActivityType,
    AgentInfo,
    AgentRole,
)

# ===========================================================================
# テスト用エージェント定義
# ===========================================================================

# Hive A: Webアプリ開発プロジェクト
AGENTS_HIVE_A = {
    "beekeeper": AgentInfo(
        agent_id="beekeeper-01",
        role=AgentRole.BEEKEEPER,
        hive_id="hive-webapp",
    ),
    "queen_ui": AgentInfo(
        agent_id="queen-ui",
        role=AgentRole.QUEEN_BEE,
        hive_id="hive-webapp",
        colony_id="colony-ui-ux",
    ),
    "worker_design": AgentInfo(
        agent_id="worker-design",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-webapp",
        colony_id="colony-ui-ux",
    ),
    "worker_a11y": AgentInfo(
        agent_id="worker-a11y",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-webapp",
        colony_id="colony-ui-ux",
    ),
    "queen_api": AgentInfo(
        agent_id="queen-api",
        role=AgentRole.QUEEN_BEE,
        hive_id="hive-webapp",
        colony_id="colony-api",
    ),
    "worker_backend": AgentInfo(
        agent_id="worker-backend",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-webapp",
        colony_id="colony-api",
    ),
    "worker_db": AgentInfo(
        agent_id="worker-db",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-webapp",
        colony_id="colony-api",
    ),
    "queen_infra": AgentInfo(
        agent_id="queen-infra",
        role=AgentRole.QUEEN_BEE,
        hive_id="hive-webapp",
        colony_id="colony-infra",
    ),
    "worker_docker": AgentInfo(
        agent_id="worker-docker",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-webapp",
        colony_id="colony-infra",
    ),
}

# Hive B: データパイプラインプロジェクト
AGENTS_HIVE_B = {
    "queen_data": AgentInfo(
        agent_id="queen-data",
        role=AgentRole.QUEEN_BEE,
        hive_id="hive-datapipe",
        colony_id="colony-etl",
    ),
    "worker_etl": AgentInfo(
        agent_id="worker-etl",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-datapipe",
        colony_id="colony-etl",
    ),
    "queen_ml": AgentInfo(
        agent_id="queen-ml",
        role=AgentRole.QUEEN_BEE,
        hive_id="hive-datapipe",
        colony_id="colony-ml",
    ),
    "worker_train": AgentInfo(
        agent_id="worker-train",
        role=AgentRole.WORKER_BEE,
        hive_id="hive-datapipe",
        colony_id="colony-ml",
    ),
}


# ===========================================================================
# シナリオ定義: リアルなエージェント行動パターン
# ===========================================================================

SCENARIOS = [
    # UI/UX Colony の活動
    {
        "agent_key": "worker_design",
        "hive": "A",
        "events": [
            (ActivityType.LLM_REQUEST, "ダッシュボードレイアウトの設計案を生成中"),
            (ActivityType.LLM_RESPONSE, "Flexboxベースの3カラムレイアウトを提案"),
            (ActivityType.MCP_TOOL_CALL, "list_directory: src/components/"),
            (ActivityType.MCP_TOOL_RESULT, "12ファイルを検出"),
            (ActivityType.LLM_REQUEST, "既存コンポーネントとの整合性を分析中"),
            (ActivityType.LLM_RESPONSE, "Header, Sidebar, Mainの分割を推奨"),
            (ActivityType.TASK_PROGRESS, "レイアウト設計 60% 完了"),
        ],
    },
    {
        "agent_key": "worker_a11y",
        "hive": "A",
        "events": [
            (ActivityType.MCP_TOOL_CALL, "axe-core: アクセシビリティ監査を実行"),
            (ActivityType.MCP_TOOL_RESULT, "3件のコントラスト比違反を検出"),
            (ActivityType.LLM_REQUEST, "WCAG 2.1 AA準拠の修正案を生成中"),
            (ActivityType.LLM_RESPONSE, "カラースキーム修正案を提案"),
        ],
    },
    # API Colony の活動
    {
        "agent_key": "worker_backend",
        "hive": "A",
        "events": [
            (ActivityType.LLM_REQUEST, "REST APIエンドポイント設計を生成中"),
            (ActivityType.LLM_RESPONSE, "OpenAPI仕様を出力"),
            (ActivityType.MCP_TOOL_CALL, "write_file: src/api/routes/users.py"),
            (ActivityType.MCP_TOOL_RESULT, "ファイルを作成"),
            (ActivityType.LLM_REQUEST, "Pydanticモデルのバリデーション追加"),
            (ActivityType.LLM_RESPONSE, "バリデーション付きモデルを生成"),
        ],
    },
    {
        "agent_key": "worker_db",
        "hive": "A",
        "events": [
            (ActivityType.MCP_TOOL_CALL, "SQLAlchemy: マイグレーション生成"),
            (ActivityType.MCP_TOOL_RESULT, "alembic revision --autogenerate 完了"),
            (ActivityType.TASK_PROGRESS, "DBスキーマ設計 80% 完了"),
        ],
    },
    # Infra Colony の活動
    {
        "agent_key": "worker_docker",
        "hive": "A",
        "events": [
            (ActivityType.LLM_REQUEST, "マルチステージDockerfile最適化"),
            (ActivityType.LLM_RESPONSE, "ビルドサイズを40%削減する案を生成"),
            (ActivityType.MCP_TOOL_CALL, "write_file: Dockerfile"),
            (ActivityType.MCP_TOOL_RESULT, "Dockerfileを更新"),
        ],
    },
    # Queen Bee の調停活動
    {
        "agent_key": "queen_ui",
        "hive": "A",
        "events": [
            (ActivityType.MESSAGE_RECEIVED, "worker-designからレイアウト提案を受信"),
            (ActivityType.MESSAGE_RECEIVED, "worker-a11yからアクセシビリティ報告を受信"),
            (ActivityType.LLM_REQUEST, "提案を統合・評価中"),
            (ActivityType.LLM_RESPONSE, "統合レポートを生成"),
            (ActivityType.MESSAGE_SENT, "Beekeeperに統合レポートを送信"),
        ],
    },
    {
        "agent_key": "queen_api",
        "hive": "A",
        "events": [
            (ActivityType.TASK_ASSIGNED, "worker-backendにAPI実装を割り当て"),
            (ActivityType.TASK_ASSIGNED, "worker-dbにスキーマ設計を割り当て"),
            (ActivityType.MESSAGE_RECEIVED, "worker-backendから進捗報告"),
            (ActivityType.LLM_REQUEST, "API設計のインターフェース整合性を検証"),
            (ActivityType.LLM_RESPONSE, "整合性OK、型安全性の追加提案"),
        ],
    },
    # Beekeeper の統括活動
    {
        "agent_key": "beekeeper",
        "hive": "A",
        "events": [
            (ActivityType.MESSAGE_RECEIVED, "queen-uiから統合レポートを受信"),
            (ActivityType.MESSAGE_RECEIVED, "queen-apiから進捗報告を受信"),
            (ActivityType.LLM_REQUEST, "プロジェクト全体の進捗を評価中"),
            (ActivityType.LLM_RESPONSE, "UI: 60%, API: 45%, Infra: 30% - 全体40%"),
            (ActivityType.MESSAGE_SENT, "ユーザーに進捗サマリーを報告"),
        ],
    },
    # Hive B の活動
    {
        "agent_key": "worker_etl",
        "hive": "B",
        "events": [
            (ActivityType.LLM_REQUEST, "CSVパーサのバリデーション生成中"),
            (ActivityType.LLM_RESPONSE, "Pandasベースのパーサを生成"),
            (ActivityType.MCP_TOOL_CALL, "write_file: src/etl/csv_parser.py"),
            (ActivityType.MCP_TOOL_RESULT, "ファイルを作成"),
            (ActivityType.TASK_PROGRESS, "ETLパイプライン構築 55% 完了"),
        ],
    },
    {
        "agent_key": "worker_train",
        "hive": "B",
        "events": [
            (ActivityType.MCP_TOOL_CALL, "GPU利用状況を確認"),
            (ActivityType.MCP_TOOL_RESULT, "GPU 0: 使用率 72%, VRAM 8.2/16 GB"),
            (ActivityType.LLM_REQUEST, "ハイパーパラメータ最適化の提案"),
            (ActivityType.LLM_RESPONSE, "学習率スケジューリングの変更を推奨"),
        ],
    },
]


async def seed_data():
    """テストデータを投入し、リアルタイムにイベントを発生させる"""
    bus = ActivityBus.get_instance()

    print("=" * 60)
    print("🐝 Hive Monitor テストデータ投入")
    print("=" * 60)

    # 全エージェントを結合
    all_agents = {**AGENTS_HIVE_A, **AGENTS_HIVE_B}

    # Step 1: エージェントを登録（agent.started）
    print("\n📋 エージェントを登録中...")
    for key, agent in all_agents.items():
        event = ActivityEvent(
            activity_type=ActivityType.AGENT_STARTED,
            agent=agent,
            summary=f"{agent.agent_id} が起動しました",
        )
        await bus.emit(event)
        print(f"  ✅ {agent.role}: {agent.agent_id} ({agent.hive_id})")
        await asyncio.sleep(0.1)

    print(f"\n📊 アクティブエージェント: {len(bus.get_active_agents())}体")
    hierarchy = bus.get_hierarchy()
    print(f"📊 Hive数: {len(hierarchy)}")
    for hive_id, hive_data in hierarchy.items():
        colonies = hive_data.get("colonies", {})
        print(f"  🏠 {hive_id}: {len(colonies)} colonies")
        for col_id, col_data in colonies.items():
            workers = col_data.get("workers", [])
            queen = col_data.get("queen_bee")
            print(f"    🏗️ {col_id}: Queen={'✅' if queen else '❌'}, Workers={len(workers)}")

    # Step 2: シナリオを順番に実行（ループ）
    print("\n🎬 アクティビティシナリオを再生中...")
    print("   (Ctrl+C で停止)")
    print("-" * 60)

    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"\n--- サイクル {cycle} ---")

            # シナリオをシャッフルして自然な見た目に
            scenarios = list(SCENARIOS)
            random.shuffle(scenarios)

            for scenario in scenarios:
                hive = scenario["hive"]
                agents = AGENTS_HIVE_A if hive == "A" else AGENTS_HIVE_B
                agent = agents[scenario["agent_key"]]

                for activity_type, summary in scenario["events"]:
                    event = ActivityEvent(
                        activity_type=activity_type,
                        agent=agent,
                        summary=summary,
                    )
                    await bus.emit(event)

                    icon = {
                        ActivityType.LLM_REQUEST: "🧠",
                        ActivityType.LLM_RESPONSE: "💬",
                        ActivityType.MCP_TOOL_CALL: "🔧",
                        ActivityType.MCP_TOOL_RESULT: "📦",
                        ActivityType.AGENT_STARTED: "▶️",
                        ActivityType.AGENT_COMPLETED: "✅",
                        ActivityType.MESSAGE_SENT: "📤",
                        ActivityType.MESSAGE_RECEIVED: "📥",
                        ActivityType.TASK_ASSIGNED: "📋",
                        ActivityType.TASK_PROGRESS: "📊",
                    }.get(activity_type, "📌")

                    print(f"  {icon} [{agent.agent_id}] {summary}")

                    # リアルタイム感を出すためランダムに待機
                    await asyncio.sleep(random.uniform(0.5, 2.0))

            # サイクル間の休止
            await asyncio.sleep(1.0)

    except KeyboardInterrupt:
        print("\n\n🛑 停止しました")


async def main():
    """メインエントリ - APIサーバーと一緒にseedを実行"""
    import uvicorn

    # クリーンな状態にリセット
    ActivityBus.reset()

    # AppStateをリセット（HiveStore含む）
    from hiveforge.api.dependencies import AppState

    AppState.reset()

    # APIサーバーをバックグラウンドで起動
    config = uvicorn.Config(
        "hiveforge.api.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # サーバーとseedを並行して実行
    async def run_server():
        await server.serve()

    async def run_seed():
        # サーバーが起動するまで少し待つ
        await asyncio.sleep(1.5)
        await seed_data()

    print("🚀 APIサーバーを起動中 (http://localhost:8000) ...")
    await asyncio.gather(
        run_server(),
        run_seed(),
    )


if __name__ == "__main__":
    asyncio.run(main())
