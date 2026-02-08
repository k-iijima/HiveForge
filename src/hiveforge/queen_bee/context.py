"""Queen Bee タスクコンテキスト共有

エージェント間のコンテキスト共有を実現する。
先行タスクの成果物を後続タスクに渡し、
依存関係に基づいた情報の流れを管理する。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ─── タスク結果モデル ────────────────────────────────────


class TaskResult(BaseModel):
    """個別タスクの実行結果"""

    model_config = ConfigDict(strict=True, frozen=True)

    task_id: str = Field(..., description="タスクID")
    goal: str = Field(..., description="タスクのゴール")
    status: str = Field(..., description="completed / failed / error")
    output: str = Field(default="", description="タスクの出力・成果物")
    error: str | None = Field(default=None, description="エラーメッセージ")
    tool_calls_made: int = Field(default=0, description="ツール呼び出し回数")
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="追加の成果物（ファイルパス等）",
    )


# ─── タスクコンテキスト ─────────────────────────────────


class TaskContext:
    """タスク間のコンテキスト共有マネージャー

    タスクの実行結果を蓄積し、依存関係に基づいて
    後続タスクに先行タスクの成果物を渡す。
    """

    def __init__(self, original_goal: str, run_id: str) -> None:
        self.original_goal = original_goal
        self.run_id = run_id
        self.completed_tasks: dict[str, TaskResult] = {}
        self.failed_tasks: dict[str, TaskResult] = {}

    def add_result(self, result: TaskResult) -> None:
        """タスク結果を追加する"""
        if result.status == "completed":
            self.completed_tasks[result.task_id] = result
        else:
            self.failed_tasks[result.task_id] = result

    def get_predecessor_results(
        self, depends_on: list[str]
    ) -> dict[str, TaskResult]:
        """先行タスクの完了結果を取得する

        Args:
            depends_on: 依存するタスクIDのリスト

        Returns:
            完了済み先行タスクの結果（未完了は含まない）
        """
        return {
            tid: self.completed_tasks[tid]
            for tid in depends_on
            if tid in self.completed_tasks
        }

    def build_context_for_task(
        self,
        task_id: str,
        goal: str,
        depends_on: list[str],
    ) -> dict[str, Any]:
        """タスク実行用のコンテキストdict を構築する

        Worker Bee に渡す context パラメータを構築。
        先行タスクの結果を含めることで、依存関係に基づいた
        情報の流れを実現する。

        Args:
            task_id: 実行するタスクのID
            goal: タスクのゴール
            depends_on: 依存するタスクIDのリスト

        Returns:
            Worker Bee に渡すコンテキストdict
        """
        predecessors = self.get_predecessor_results(depends_on)

        # 先行タスクの結果をシリアライズ
        predecessor_data = {
            tid: {
                "goal": r.goal,
                "output": r.output,
                "artifacts": r.artifacts,
            }
            for tid, r in predecessors.items()
        }

        return {
            "original_goal": self.original_goal,
            "run_id": self.run_id,
            "current_task": {
                "task_id": task_id,
                "goal": goal,
            },
            "predecessor_results": predecessor_data,
        }

    def summary(self) -> dict[str, Any]:
        """コンテキストのサマリーを返す"""
        return {
            "original_goal": self.original_goal,
            "run_id": self.run_id,
            "completed_count": len(self.completed_tasks),
            "failed_count": len(self.failed_tasks),
            "total_count": len(self.completed_tasks) + len(self.failed_tasks),
        }
