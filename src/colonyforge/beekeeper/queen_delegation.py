"""Beekeeper Queen Bee委譲Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core import generate_event_id
from ..core.models.action_class import TrustLevel
from ..core.swarming import SwarmingFeatures

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from ..core.config import LLMConfig
    from ..core.swarming import SwarmingEngine
    from ..queen_bee.server import QueenBeeMCPServer
    from .session import BeekeeperSession

logger = logging.getLogger(__name__)


class QueenDelegationMixin:
    """Queen Beeへのタスク委譲・パイプライン実行・結果整形"""

    if TYPE_CHECKING:
        ar: AkashicRecord
        llm_config: LLMConfig | None
        current_session: BeekeeperSession | None
        _swarming_engine: SwarmingEngine
        _queens: dict[str, QueenBeeMCPServer]

        async def _ask_user(self, question: str, options: list[str] | None = None) -> str: ...

    async def _delegate_to_queen(
        self, colony_id: str, task: str, context: dict[str, Any] | None = None
    ) -> str:
        """Queen Beeにタスクを委譲"""
        from ..queen_bee.server import QueenBeeMCPServer

        logger.info(f"タスクをQueen Bee ({colony_id}) に委譲: {task}")

        # Swarming評価: タスク特徴量をcontextから取得（あれば）
        ctx = context or {}
        swarming_info: dict[str, Any] | None = None
        if any(k in ctx for k in ("complexity", "risk", "urgency")):
            features = SwarmingFeatures(
                complexity=ctx.get("complexity", 3),
                risk=ctx.get("risk", 3),
                urgency=ctx.get("urgency", 3),
            )
            swarming_info = self._swarming_engine.evaluate(features)
            logger.info(f"Swarming評価: {swarming_info['template']} - {swarming_info['reason']}")

        # Queen Beeを取得または作成
        if colony_id not in self._queens:
            queen = QueenBeeMCPServer(
                colony_id=colony_id,
                ar=self.ar,
                llm_config=self.llm_config,
            )
            self._queens[colony_id] = queen
            logger.info(f"新規Queen Bee作成: {colony_id}")
        else:
            queen = self._queens[colony_id]

        # セッションにColonyを追加
        if self.current_session:
            self.current_session.add_colony(colony_id)

        # Run IDを生成
        run_id = generate_event_id()

        # Queen Beeでタスクを実行
        execute_context = ctx.copy()
        if swarming_info:
            execute_context["swarming"] = swarming_info

        result = await queen.dispatch_tool(
            "execute_goal",
            {
                "run_id": run_id,
                "goal": task,
                "context": execute_context,
            },
        )

        # 結果を整形
        if result.get("status") == "completed":
            tasks_completed = result.get("tasks_completed", 0)
            tasks_total = result.get("tasks_total", 0)
            # 各タスクの結果からLLM出力を取得
            outputs = []
            for task_result in result.get("results", []):
                if task_result.get("llm_output"):
                    outputs.append(task_result["llm_output"])
            output_text = "\n".join(outputs) if outputs else ""
            return f"タスク完了 ({tasks_completed}/{tasks_total})\n{output_text}"
        elif result.get("status") == "partial":
            tasks_completed = result.get("tasks_completed", 0)
            tasks_total = result.get("tasks_total", 0)
            outputs = []
            for task_result in result.get("results", []):
                if task_result.get("llm_output"):
                    outputs.append(task_result["llm_output"])
            output_text = "\n".join(outputs) if outputs else ""
            return f"一部タスク完了 ({tasks_completed}/{tasks_total})\n{output_text}"
        else:
            error = result.get("error", "Unknown error")
            return f"タスク失敗: {error}"

    async def _delegate_to_queen_with_pipeline(
        self,
        colony_id: str,
        task: str,
        trust_level: TrustLevel = TrustLevel.PROPOSE_CONFIRM,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Queen Bee に Pipeline 有効でタスクを委譲する

        承認が必要な場合は _ask_user() でユーザーに確認を求め、
        approve/reject を受けて実行を再開する。

        Args:
            colony_id: Colony ID
            task: 委譲するタスク
            trust_level: 信頼レベル
            context: コンテキスト

        Returns:
            実行結果の文字列
        """
        from ..queen_bee.server import QueenBeeMCPServer

        logger.info(f"Pipeline付きタスクをQueen Bee ({colony_id}) に委譲: {task}")

        ctx = context or {}

        # Queen Beeを取得または作成（Pipeline有効）
        if colony_id not in self._queens:
            queen = QueenBeeMCPServer(
                colony_id=colony_id,
                ar=self.ar,
                llm_config=self.llm_config,
                use_pipeline=True,
                trust_level=trust_level,
            )
            self._queens[colony_id] = queen
            logger.info(f"新規Queen Bee (Pipeline) 作成: {colony_id}")
        else:
            queen = self._queens[colony_id]

        # セッションにColonyを追加
        if self.current_session:
            self.current_session.add_colony(colony_id)

        # Run IDを生成
        run_id = generate_event_id()

        # Queen Beeでタスクを実行
        result = await queen.dispatch_tool(
            "execute_goal",
            {
                "run_id": run_id,
                "goal": task,
                "context": ctx,
            },
        )

        # 承認が必要な場合
        if result.get("status") == "approval_required":
            request_id = result["request_id"]
            action_class = result.get("action_class", "unknown")
            task_count = result.get("task_count", 0)

            # _ask_user() でユーザーに確認
            question = (
                f"承認が必要です。\n"
                f"タスク: {task}\n"
                f"アクションクラス: {action_class}\n"
                f"タスク数: {task_count}\n"
                f"承認しますか？"
            )
            user_response = await self._ask_user(question, options=["承認", "拒否"])

            # 応答に基づき再実行
            if "approved" in user_response.lower() or "承認" in user_response:
                resumed = await queen.resume_with_approval(
                    request_id=request_id,
                    approved=True,
                    reason="ユーザー承認",
                )
                return self._format_queen_result(resumed)
            else:
                resumed = await queen.resume_with_approval(
                    request_id=request_id,
                    approved=False,
                    reason="ユーザー拒否",
                )
                return f"拒否されました: {task}"

        return self._format_queen_result(result)

    def _format_queen_result(self, result: dict[str, Any]) -> str:
        """Queen Beeの実行結果を文字列にフォーマットする"""
        if result.get("status") == "completed":
            tasks_completed = result.get("tasks_completed", 0)
            tasks_total = result.get("tasks_total", 0)
            outputs = []
            for task_result in result.get("results", []):
                if isinstance(task_result, dict) and task_result.get("llm_output"):
                    outputs.append(task_result["llm_output"])
            output_text = "\n".join(outputs) if outputs else ""
            return f"タスク完了 ({tasks_completed}/{tasks_total})\n{output_text}"
        elif result.get("status") == "partial":
            tasks_completed = result.get("tasks_completed", 0)
            tasks_total = result.get("tasks_total", 0)
            outputs = []
            for task_result in result.get("results", []):
                if isinstance(task_result, dict) and task_result.get("llm_output"):
                    outputs.append(task_result["llm_output"])
            output_text = "\n".join(outputs) if outputs else ""
            return f"一部タスク完了 ({tasks_completed}/{tasks_total})\n{output_text}"
        elif result.get("status") == "rejected":
            return f"拒否されました: {result.get('reason', '')}"
        else:
            error = result.get("error", "Unknown error")
            return f"タスク失敗: {error}"
