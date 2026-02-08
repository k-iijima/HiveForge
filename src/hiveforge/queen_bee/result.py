"""Queen Bee Colony結果集約

タスク実行結果を Colony 単位で集約し、
Queen Bee への報告用レポートを生成する。
"""

from __future__ import annotations

import enum
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hiveforge.queen_bee.context import TaskContext, TaskResult

logger = logging.getLogger(__name__)


class ColonyStatus(str, enum.Enum):
    """Colony全体の実行ステータス"""

    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class ColonyResult(BaseModel):
    """Colony実行結果の集約レポート"""

    model_config = ConfigDict(strict=True, frozen=True)

    colony_id: str = Field(..., description="Colony ID")
    run_id: str = Field(..., description="Run ID")
    original_goal: str = Field(..., description="元の目標")
    status: ColonyStatus = Field(..., description="全体ステータス")
    total_tasks: int = Field(..., description="タスク総数")
    completed_count: int = Field(..., description="完了タスク数")
    failed_count: int = Field(..., description="失敗タスク数")
    total_tool_calls: int = Field(default=0, description="ツール呼び出し総数")
    task_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="個別タスクの結果リスト",
    )
    summary_text: str = Field(default="", description="人間向けサマリー")

    def to_event_data(self) -> dict[str, Any]:
        """イベント発行用のデータを返す"""
        data: dict[str, Any] = {
            "colony_id": self.colony_id,
            "run_id": self.run_id,
            "original_goal": self.original_goal,
            "status": self.status.value,
            "total_tasks": self.total_tasks,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "total_tool_calls": self.total_tool_calls,
        }
        if self.failed_count > 0:
            data["failed_tasks"] = [r for r in self.task_results if r.get("status") != "completed"]
        return data


class ColonyResultBuilder:
    """TaskContext から ColonyResult を構築する"""

    @staticmethod
    def build(ctx: TaskContext, colony_id: str) -> ColonyResult:
        """TaskContext から ColonyResult を構築

        Args:
            ctx: 実行済みの TaskContext
            colony_id: Colony ID

        Returns:
            集約された ColonyResult
        """
        completed = len(ctx.completed_tasks)
        failed = len(ctx.failed_tasks)
        total = completed + failed

        status = ColonyResultBuilder._determine_status(completed, failed)
        task_results = ColonyResultBuilder._collect_task_results(ctx)
        tool_calls = sum(r.tool_calls_made for r in ctx.completed_tasks.values()) + sum(
            r.tool_calls_made for r in ctx.failed_tasks.values()
        )

        summary_text = f"目標「{ctx.original_goal}」: {completed}/{total} タスク完了"
        if failed > 0:
            summary_text += f"（{failed} 件失敗）"

        return ColonyResult(
            colony_id=colony_id,
            run_id=ctx.run_id,
            original_goal=ctx.original_goal,
            status=status,
            total_tasks=total,
            completed_count=completed,
            failed_count=failed,
            total_tool_calls=tool_calls,
            task_results=task_results,
            summary_text=summary_text,
        )

    @staticmethod
    def _determine_status(completed: int, failed: int) -> ColonyStatus:
        """完了・失敗件数からステータスを判定"""
        if failed == 0 and completed > 0:
            return ColonyStatus.COMPLETED
        if completed > 0 and failed > 0:
            return ColonyStatus.PARTIAL_FAILURE
        return ColonyStatus.FAILED

    @staticmethod
    def _collect_task_results(ctx: TaskContext) -> list[dict[str, Any]]:
        """全タスク結果をリスト化"""
        results: list[dict[str, Any]] = []

        for result in ctx.completed_tasks.values():
            results.append(_task_result_to_dict(result))

        for result in ctx.failed_tasks.values():
            results.append(_task_result_to_dict(result))

        return results


def _task_result_to_dict(result: TaskResult) -> dict[str, Any]:
    """TaskResult を辞書に変換"""
    data: dict[str, Any] = {
        "task_id": result.task_id,
        "goal": result.goal,
        "status": result.status,
    }
    if result.output:
        data["output"] = result.output
    if result.error:
        data["error"] = result.error
    if result.tool_calls_made > 0:
        data["tool_calls_made"] = result.tool_calls_made
    if result.artifacts:
        data["artifacts"] = result.artifacts
    return data
