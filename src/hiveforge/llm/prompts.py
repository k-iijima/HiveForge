"""エージェントプロンプト

各エージェント（Beekeeper, QueenBee, WorkerBee）のシステムプロンプト。
YAML設定ファイルから読み込むか、ハードコードされたデフォルトを使用。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hiveforge.llm.prompt_config import (
        BeekeeperConfig,
        QueenBeeConfig,
        WorkerBeeConfig,
    )

# -----------------------------------------------------------------------------
# Worker Bee プロンプト（ハードコードされたデフォルト）
# -----------------------------------------------------------------------------

WORKER_BEE_SYSTEM = """あなたはHiveForgeのWorker Beeです。専門的なタスクを実行するエージェントです。

## あなたの役割
- ユーザーから与えられた具体的なタスクを実行する
- 利用可能なツールを **必ず** 使って作業を完了する
- 作業の進捗と結果を正確に報告する

## 重要: ツールの使用は必須です
- タスクの実行には必ずツール（run_command, write_file, read_file等）を呼び出してください
- テキストで「実行しました」と説明するだけでは不十分です
- 実際にツールを呼び出して操作を実行してください
- コマンド実行が必要な場合は run_command ツールを使ってください
- ファイル作成が必要な場合は write_file ツールを使ってください

## 行動指針
1. タスクを理解し、必要なステップを考える
2. 適切なツールを選択して **実際に呼び出す**（テキスト応答ではなくツール呼び出しで実行する）
3. エラーが発生した場合は原因を分析し、可能なら代替手段を試す
4. 作業が完了したら結果を簡潔に報告する

## 制約
- 与えられたツール以外の操作はできない
- 不明点がある場合は確認を求める
- 危険な操作（ファイル削除など）は実行前に確認する

作業を開始してください。
"""

# -----------------------------------------------------------------------------
# Queen Bee プロンプト（ハードコードされたデフォルト）
# -----------------------------------------------------------------------------

QUEEN_BEE_SYSTEM = """あなたはHiveForgeのQueen Beeです。Colonyを統括し、タスクを分解・割り当てるエージェントです。

## あなたの役割
- ユーザーの目標を理解し、実行可能なタスクに分解する
- 各タスクを適切なWorker Beeに割り当てる
- Worker Beeの進捗を監視し、必要に応じて調整する
- Colony全体の作業を調整し、目標達成に導く

## 行動指針
1. 目標を分析し、必要なタスクをリストアップする
2. タスク間の依存関係を考慮して実行順序を決める
3. 各タスクの進捗を追跡する
4. 問題が発生した場合は再計画する

## 出力形式
タスク分解時は以下の形式で出力：
- タスク1: [タスク内容]
- タスク2: [タスク内容]
...
"""

# -----------------------------------------------------------------------------
# Beekeeper プロンプト（ハードコードされたデフォルト）
# -----------------------------------------------------------------------------

BEEKEEPER_SYSTEM = """あなたはHiveForgeのBeekeeperです。ユーザーとの対話窓口であり、Colonyを通じて作業を実行します。

## あなたの役割
- ユーザーの要望を理解し、Colonyに作業を依頼する
- 作業は必ず `delegate_to_queen` ツールを使ってColonyに委譲する
- ユーザーに結果を報告する

## 重要: 作業の委譲
ユーザーから作業を依頼されたら、必ず `delegate_to_queen` ツールを使ってください：
- colony_id: "default" を使用（または適切なColony名）
- task: ユーザーの依頼内容をそのまま渡す
- context: 作業ディレクトリなどの情報を渡す

## 行動指針
1. ユーザーの意図を正確に把握する
2. `delegate_to_queen` でColonyに作業を委譲する
3. 結果をユーザーに報告する

## コミュニケーション
- 簡潔で明確な日本語で応答する
- 作業結果を分かりやすく報告する
"""


# -----------------------------------------------------------------------------
# プロンプト取得関数
# -----------------------------------------------------------------------------


def get_system_prompt(agent_type: str) -> str:
    """エージェントタイプに応じたシステムプロンプトを取得（ハードコードデフォルト）

    Args:
        agent_type: "worker_bee", "queen_bee", "beekeeper"

    Returns:
        システムプロンプト
    """
    prompts = {
        "worker_bee": WORKER_BEE_SYSTEM,
        "queen_bee": QUEEN_BEE_SYSTEM,
        "beekeeper": BEEKEEPER_SYSTEM,
    }
    return prompts.get(agent_type, WORKER_BEE_SYSTEM)


def get_prompt_from_config(
    agent_type: str,
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
    worker_name: str = "default",
) -> str:
    """YAML設定ファイルからプロンプトを取得

    設定ファイルが存在しない場合はハードコードされたデフォルトを返す。

    Args:
        agent_type: "worker_bee", "queen_bee", "beekeeper"
        vault_path: Vaultディレクトリパス
        hive_id: Hive ID
        colony_id: Colony ID
        worker_name: Worker Beeの名前（worker_beeの場合のみ使用）

    Returns:
        システムプロンプト
    """
    from hiveforge.llm.prompt_config import PromptLoader

    loader = PromptLoader(vault_path)

    if agent_type == "beekeeper":
        config = loader.load_beekeeper_config(hive_id)
        if config:
            return config.prompt.system
    elif agent_type == "queen_bee":
        config = loader.load_queen_bee_config(hive_id, colony_id)
        if config:
            return config.prompt.system
    elif agent_type == "worker_bee":
        config = loader.load_worker_bee_config(worker_name, hive_id, colony_id)
        if config:
            return config.prompt.system

    # 設定ファイルがない場合はデフォルト
    return get_system_prompt(agent_type)


def get_beekeeper_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
) -> BeekeeperConfig | None:
    """Beekeeper設定を取得"""
    from hiveforge.llm.prompt_config import PromptLoader

    return PromptLoader(vault_path).load_beekeeper_config(hive_id)


def get_queen_bee_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> QueenBeeConfig | None:
    """Queen Bee設定を取得"""
    from hiveforge.llm.prompt_config import PromptLoader

    return PromptLoader(vault_path).load_queen_bee_config(hive_id, colony_id)


def get_worker_bee_config(
    name: str = "default",
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> WorkerBeeConfig | None:
    """Worker Bee設定を取得"""
    from hiveforge.llm.prompt_config import PromptLoader

    return PromptLoader(vault_path).load_worker_bee_config(name, hive_id, colony_id)
