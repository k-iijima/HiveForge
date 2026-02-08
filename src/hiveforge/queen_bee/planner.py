"""Queen Bee タスクプランナー — LLMによるゴール分解

ゴール(goal)をLLMで分析し、具体的なタスクリストに分解する。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hiveforge.core import generate_event_id
from hiveforge.llm.client import LLMClient, Message

logger = logging.getLogger(__name__)


# ─── タスク分解プロンプト ───────────────────────────────

TASK_DECOMPOSITION_SYSTEM = """\
あなたはHiveForgeのQueen Bee（タスク分解エージェント）です。
ユーザーの目標を、具体的かつ実行可能なタスクリストに分解してください。

## ルール
- 各タスクは1つの明確なアクションに対応すること
- タスクは実行順に並べること
- 最低1タスク、最大10タスクに分解すること
- 目標が十分具体的であれば、無理に分解せず1タスクのままでよい

## 出力形式
以下の形式のJSONのみを出力してください。他のテキストは含めないでください。

{"tasks": [{"goal": "具体的なタスク目標1"}, {"goal": "具体的なタスク目標2"}], \
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


class TaskPlan(BaseModel):
    """タスク分解計画"""

    model_config = ConfigDict(strict=True, frozen=True)

    tasks: list[PlannedTask] = Field(..., min_length=1)
    reasoning: str = Field(default="", description="分解の理由・根拠")


# ─── TaskPlanner ────────────────────────────────────────


class TaskPlanner:
    """LLMを使ったタスク分解"""

    MAX_TASKS = 10

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    async def plan(
        self, goal: str, context: dict[str, Any] | None = None
    ) -> TaskPlan:
        """ゴールをタスクに分解する

        LLMでタスク分解を試み、失敗した場合は目標をそのまま
        1タスクとして返すフォールバックを行う。
        """
        messages = self._build_messages(goal, context or {})
        try:
            response = await self._client.chat(messages)
            return self._parse_response(response.content)
        except Exception:
            logger.warning(
                "LLMタスク分解に失敗、単一タスクにフォールバック", exc_info=True
            )
            return TaskPlan(
                tasks=[PlannedTask(goal=goal)],
                reasoning="LLMタスク分解に失敗したため、目標をそのまま1タスクとして実行",
            )

    def _build_messages(
        self, goal: str, context: dict[str, Any]
    ) -> list[Message]:
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
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL
        )
        json_str = json_match.group(1).strip() if json_match else content.strip()

        data = json.loads(json_str)

        # タスク数上限を適用
        if "tasks" in data and len(data["tasks"]) > self.MAX_TASKS:
            data["tasks"] = data["tasks"][: self.MAX_TASKS]

        return TaskPlan.model_validate(data)
