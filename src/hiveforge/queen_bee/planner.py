"""Queen Bee タスクプランナー — LLMによるゴール分解

ゴール(goal)をLLMで分析し、具体的なタスクリストに分解する。
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from hiveforge.core import generate_event_id
from hiveforge.llm.client import LLMClient, Message

if TYPE_CHECKING:
    from hiveforge.guard_bee.models import GuardBeeReport
    from hiveforge.guard_bee.verifier import GuardBeeVerifier

logger = logging.getLogger(__name__)


# ─── タスク分解プロンプト ───────────────────────────────

TASK_DECOMPOSITION_SYSTEM = """\
あなたはHiveForgeのQueen Bee（タスク分解エージェント）です。
ユーザーの目標を、具体的かつ実行可能なタスクリストに分解してください。

## ルール
- 各タスクは1つの明確なアクションに対応すること
- タスクには一意のidを付与すること（"task-1", "task-2" 等）
- タスク間に依存関係がある場合は depends_on で明示すること
- 依存関係がないタスクは並列実行可能という意味である
- 最低1タスク、最大10タスクに分解すること
- 目標が十分具体的であれば、無理に分解せず1タスクのままでよい

## 分解方針（重要）
1. **最速完了**: なるべく多くのタスクを並列実行できるように分解する。\
依存関係が不要なタスクを無理に直列にしないこと。
2. **作業競合の回避**: 各タスクが操作するファイル・リソースが重複しないように分割する。\
同じファイルを複数タスクが同時に編集する状況を避けること。\
競合が避けられない場合は depends_on で順序を明示する。
3. **粒度の適正化**: 1タスクが大きすぎず、細かすぎず、\
Worker Beeが1回のツール実行ループで完了できる単位にする。

## 出力形式
以下の形式のJSONのみを出力してください。他のテキストは含めないでください。

{"tasks": [{"id": "task-1", "goal": "具体的なタスク目標1"}, \
{"id": "task-2", "goal": "具体的なタスク目標2", "depends_on": ["task-1"]}], \
"reasoning": "分解の理由"}
"""


# ─── Pydantic モデル ────────────────────────────────────


class PlannedTask(BaseModel):
    """分解された個別タスク"""

    model_config = ConfigDict(strict=True, frozen=True)

    task_id: str = Field(
        default_factory=lambda: str(generate_event_id()),
        description="タスクの一意識別子（ULID）",
    )
    goal: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="タスクの具体的な目標",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="依存するタスクIDのリスト",
    )


class TaskPlan(BaseModel):
    """タスク分解計画"""

    model_config = ConfigDict(strict=True, frozen=True)

    tasks: list[PlannedTask] = Field(..., min_length=1)
    reasoning: str = Field(default="", description="分解の理由・根拠")

    def execution_order(self) -> list[list[str]]:
        """依存関係を解析し、並列実行可能なグループを返す

        トポロジカルソート（Kahn's algorithm）でタスクを層別にグループ化。
        同じ層のタスクは並列実行可能。

        Returns:
            list[list[str]]: 各層のタスクIDリスト。
                例: [["task-1", "task-2"], ["task-3"]] →
                    task-1/task-2は並列、task-3は後続

        Raises:
            ValueError: 循環依存が検出された場合
        """
        task_map = {t.task_id: t for t in self.tasks}
        all_ids = set(task_map.keys())

        # 入次数を計算（不明な依存先は無視）
        in_degree: dict[str, int] = dict.fromkeys(all_ids, 0)
        for task in self.tasks:
            for dep in task.depends_on:
                if dep in all_ids:
                    in_degree[task.task_id] += 1

        # Kahn's algorithm
        layers: list[list[str]] = []
        remaining = dict(in_degree)

        while remaining:
            # 入次数 0 のノードを収集
            ready = [tid for tid, deg in remaining.items() if deg == 0]
            if not ready:
                raise ValueError("タスクに循環依存があります: " + ", ".join(remaining.keys()))
            layers.append(sorted(ready))
            for tid in ready:
                del remaining[tid]
            # 削除したノードが向き先の入次数を減らす
            for tid in remaining:
                task = task_map[tid]
                for dep in task.depends_on:
                    if dep in ready:
                        remaining[tid] -= 1

        return layers

    def is_parallelizable(self) -> bool:
        """並列実行可能なタスクがあるか"""
        layers = self.execution_order()
        return any(len(layer) > 1 for layer in layers)


# ─── TaskPlanner ────────────────────────────────────────


class TaskPlanner:
    """LLMを使ったタスク分解"""

    MAX_TASKS = 10

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    async def plan(self, goal: str, context: dict[str, Any] | None = None) -> TaskPlan:
        """ゴールをタスクに分解する

        LLMでタスク分解を試み、失敗した場合は目標をそのまま
        1タスクとして返すフォールバックを行う。
        """
        messages = self._build_messages(goal, context or {})
        try:
            response = await self._client.chat(messages)
            return self._parse_response(response.content)
        except Exception:
            logger.error(
                "LLMタスク分解に失敗、単一タスクにフォールバック: goal=%s",
                goal,
                exc_info=True,
            )
            return TaskPlan(
                tasks=[PlannedTask(goal=goal)],
                reasoning="LLMタスク分解に失敗したため、目標をそのまま1タスクとして実行",
            )

    def _build_messages(self, goal: str, context: dict[str, Any]) -> list[Message]:
        """LLM用メッセージを構築"""
        user_content = f"## 目標\n{goal}"
        if context:
            context_json = json.dumps(context, ensure_ascii=False, indent=2)
            user_content += f"\n\n## コンテキスト\n{context_json}"
        return [
            Message(role="system", content=TASK_DECOMPOSITION_SYSTEM),
            Message(role="user", content=user_content),
        ]

    def _parse_response(self, content: str) -> TaskPlan:
        """LLMレスポンスをパースしてTaskPlanに変換

        JSONコードブロック (```json ... ```) または
        生JSONの両方に対応する。
        """
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else content.strip()

        data = json.loads(json_str)

        # タスク数上限を適用
        if "tasks" in data and len(data["tasks"]) > self.MAX_TASKS:
            data["tasks"] = data["tasks"][: self.MAX_TASKS]

        # LLM出力の "id" を "task_id" にマッピング
        if "tasks" in data:
            for task_data in data["tasks"]:
                if "id" in task_data and "task_id" not in task_data:
                    task_data["task_id"] = task_data.pop("id")

        return TaskPlan.model_validate(data)

    @staticmethod
    def validate(
        plan: TaskPlan,
        original_goal: str,
        verifier: GuardBeeVerifier,
        colony_id: str,
        task_id: str,
        run_id: str,
    ) -> GuardBeeReport:
        """Guard Beeでプラン妥当性を検証する

        PlanStructureRule (L1) と PlanGoalCoverageRule (L2) を適用し、
        構造的妥当性とゴール品質をチェックする。

        Args:
            plan: 検証対象のタスク分解計画
            original_goal: 分解前の元のゴール
            verifier: GuardBeeVerifier（プラン用ルール構成済み）
            colony_id: Colony ID
            task_id: Task ID（親タスク）
            run_id: Run ID

        Returns:
            GuardBeeReport（verdict, rule_results 等）
        """
        from hiveforge.guard_bee.plan_rules import create_plan_evidence

        evidence = [create_plan_evidence(plan, original_goal)]
        return verifier.verify(
            colony_id=colony_id,
            task_id=task_id,
            run_id=run_id,
            evidence=evidence,
        )
