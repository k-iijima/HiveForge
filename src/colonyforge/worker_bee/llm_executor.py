"""Worker Bee LLM 実行ロジック

AgentRunner を使用してタスクをLLMで自律実行する機能。
WorkerBeeMCPServer に mix-in される。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LLMExecutorMixin:
    """LLM実行メソッドを提供するMixin

    WorkerBeeMCPServer に mix-in される。
    以下の属性・メソッドを利用する:
    - worker_id, ar, context, llm_config
    - handle_report_progress(), handle_receive_task()
    - handle_complete_task(), handle_fail_task()
    """

    async def _get_llm_client(self) -> Any:
        """LLMクライアントを取得（遅延初期化）"""
        if self._llm_client is None:
            from ..llm.client import LLMClient

            self._llm_client = LLMClient(config=self.llm_config)
        return self._llm_client

    async def _get_agent_runner(self) -> Any:
        """AgentRunnerを取得（遅延初期化）"""
        if self._agent_runner is None:
            from ..core.activity_bus import AgentInfo, AgentRole
            from ..llm.runner import AgentRunner
            from ..llm.tools import get_basic_tools

            client = await self._get_llm_client()
            agent_info = AgentInfo(
                agent_id=self.worker_id,
                role=AgentRole.WORKER_BEE,
                hive_id="0",
                colony_id=(self.context.colony_id if hasattr(self.context, "colony_id") else "0"),
            )
            self._agent_runner = AgentRunner(
                client,
                agent_type="worker_bee",
                vault_path=str(self.ar.vault_path),
                worker_name=self.worker_id,
                agent_info=agent_info,
                require_tool_use=True,
            )

            # 基本ツールを登録
            for tool in get_basic_tools():
                self._agent_runner.register_tool(tool)

        return self._agent_runner

    async def run_with_llm(
        self, goal: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """LLMを使用してタスクを自律実行

        Args:
            goal: タスクの目標（自然言語）
            context: 追加コンテキスト情報

        Returns:
            実行結果
        """
        from ..llm.runner import AgentContext

        runner = await self._get_agent_runner()

        # コンテキストを構築
        agent_context = AgentContext(
            run_id=self.context.current_run_id or "standalone",
            task_id=self.context.current_task_id,
            working_directory=context.get("working_directory", ".") if context else ".",
            metadata=context or {},
        )

        # 進捗報告: 開始
        await self.handle_report_progress({"progress": 10, "message": "LLMで思考中..."})

        try:
            # LLMで実行
            result = await runner.run(goal, agent_context)

            # 進捗報告: 完了
            await self.handle_report_progress({"progress": 100, "message": "実行完了"})

            if result.success:
                return {
                    "status": "success",
                    "output": result.output,
                    "tool_calls_made": result.tool_calls_made,
                }
            else:
                return {
                    "status": "error",
                    "error": result.error,
                    "tool_calls_made": result.tool_calls_made,
                }

        except Exception as e:
            logger.exception("LLM実行エラー: %s", e)
            return {
                "status": "error",
                "error": str(e),
            }

    async def execute_task_with_llm(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """タスクを受け取りLLMで自律実行（ワンショット）

        receive_task + run_with_llm + complete_task/fail_task を一括実行
        """
        # タスクを受け取る
        receive_result = await self.handle_receive_task(arguments)
        if "error" in receive_result:
            return receive_result

        goal = arguments.get("goal", "")
        context = arguments.get("context", {})

        # LLMで実行
        llm_result = await self.run_with_llm(goal, context)

        # 結果に応じて完了/失敗を報告
        if llm_result.get("status") == "success":
            complete_result = await self.handle_complete_task(
                {
                    "result": llm_result.get("output", ""),
                    "deliverables": [],
                }
            )
            return {
                **complete_result,
                "llm_output": llm_result.get("output"),
                "tool_calls_made": llm_result.get("tool_calls_made", 0),
            }
        else:
            fail_result = await self.handle_fail_task(
                {
                    "reason": llm_result.get("error", "Unknown error"),
                    "recoverable": True,
                }
            )
            return {
                **fail_result,
                "llm_error": llm_result.get("error"),
            }
