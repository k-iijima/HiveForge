"""Beekeeper LLM統合Mixin"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core.swarming import SwarmingFeatures

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from ..core.config import LLMConfig
    from ..core.swarming import SwarmingEngine
    from ..llm.client import LLMClient
    from ..llm.runner import AgentRunner
    from .session import BeekeeperSession

logger = logging.getLogger(__name__)


class LLMIntegrationMixin:
    """LLMクライアント・AgentRunner・内部ツール登録"""

    if TYPE_CHECKING:
        ar: AkashicRecord
        llm_config: LLMConfig | None
        current_session: BeekeeperSession | None
        _llm_client: LLMClient | None
        _agent_runner: AgentRunner | None
        _swarming_engine: SwarmingEngine

        async def _delegate_to_queen(
            self, colony_id: str, task: str, context: dict[str, Any] | None = None
        ) -> str: ...
        async def _ask_user(self, question: str, options: list[str] | None = None) -> str: ...
        async def handle_create_hive(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
        async def handle_create_colony(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
        async def handle_list_hives(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
        async def handle_get_status(self, arguments: dict[str, Any]) -> dict[str, Any]: ...

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

            client = await self._get_llm_client()
            agent_info = AgentInfo(
                agent_id="beekeeper",
                role=AgentRole.BEEKEEPER,
                hive_id="0",
            )
            self._agent_runner = AgentRunner(
                client,
                agent_type="beekeeper",
                vault_path=str(self.ar.vault_path),
                agent_info=agent_info,
            )

            # Beekeeperが使える内部ツールを登録
            self._register_internal_tools()

        return self._agent_runner

    def _register_internal_tools(self) -> None:
        """Beekeeperが内部で使えるツールを登録"""
        from ..llm.tools import ToolDefinition  # type: ignore[attr-defined]

        assert self._agent_runner is not None

        # Hiveを作成するツール
        create_hive = ToolDefinition(
            name="create_hive",
            description="新しいHive（プロジェクト）を作成する。タスクを実行する前にHiveを作成する必要がある。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Hive名（プロジェクト名）"},
                    "goal": {"type": "string", "description": "プロジェクトの目標"},
                },
                "required": ["name", "goal"],
            },
            handler=self._internal_create_hive,
        )

        # Colonyを作成するツール
        create_colony = ToolDefinition(
            name="create_colony",
            description="Hive内に新しいColony（作業チーム）を作成する。タスクを委譲する前にColonyを作成する必要がある。",
            parameters={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "所属Hive ID"},
                    "name": {"type": "string", "description": "Colony名"},
                    "domain": {"type": "string", "description": "専門領域の説明"},
                },
                "required": ["hive_id", "name", "domain"],
            },
            handler=self._internal_create_colony,
        )

        # Queen Beeに作業を依頼するツール
        delegate_to_queen = ToolDefinition(
            name="delegate_to_queen",
            description="Queen Beeにタスクを委譲する。事前にcreate_hiveとcreate_colonyでHive/Colonyを作成しておく必要がある。",
            parameters={
                "type": "object",
                "properties": {
                    "colony_id": {"type": "string", "description": "Colony ID"},
                    "task": {"type": "string", "description": "委譲するタスク"},
                    "context": {"type": "object", "description": "コンテキスト"},
                },
                "required": ["colony_id", "task"],
            },
            handler=self._delegate_to_queen,
        )

        # ユーザーに確認を求めるツール
        ask_user = ToolDefinition(
            name="ask_user",
            description="ユーザーに確認を求める",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "質問内容"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "選択肢（任意）",
                    },
                },
                "required": ["question"],
            },
            handler=self._ask_user,
        )

        # Hive/Colony状態を取得するツール
        get_hive_status = ToolDefinition(
            name="get_hive_status",
            description="Hive/Colonyの状態を取得",
            parameters={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string"},
                },
            },
            handler=self._get_hive_status,
        )

        # Hive一覧を取得するツール
        list_hives = ToolDefinition(
            name="list_hives",
            description="全Hiveの一覧を取得する",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=self._internal_list_hives,
        )

        # タスク特徴量を評価してテンプレートを提案するツール
        evaluate_task = ToolDefinition(
            name="evaluate_task",
            description="タスクの特徴量（複雑性・リスク・緊急度）を評価し、最適なColonyテンプレートを提案する",
            parameters={
                "type": "object",
                "properties": {
                    "complexity": {
                        "type": "integer",
                        "description": "複雑性 (1-5)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "risk": {
                        "type": "integer",
                        "description": "リスク (1-5)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "urgency": {
                        "type": "integer",
                        "description": "緊急度 (1-5)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
            },
            handler=self._internal_evaluate_task,
        )

        self._agent_runner.register_tool(create_hive)
        self._agent_runner.register_tool(create_colony)
        self._agent_runner.register_tool(delegate_to_queen)
        self._agent_runner.register_tool(ask_user)
        self._agent_runner.register_tool(get_hive_status)
        self._agent_runner.register_tool(list_hives)
        self._agent_runner.register_tool(evaluate_task)

    async def _internal_create_hive(self, name: str, goal: str) -> str:
        """内部ツール: Hiveを作成"""
        result = await self.handle_create_hive({"name": name, "goal": goal})
        if result.get("status") == "created":
            return f"Hive作成完了: hive_id={result['hive_id']}, name={result['name']}"
        return f"Hive作成失敗: {result.get('error', 'Unknown')}"

    async def _internal_create_colony(self, hive_id: str, name: str, domain: str) -> str:
        """内部ツール: Colonyを作成"""
        result = await self.handle_create_colony(
            {"hive_id": hive_id, "name": name, "domain": domain}
        )
        if result.get("status") == "created":
            return f"Colony作成完了: colony_id={result['colony_id']}, name={result['name']}"
        return f"Colony作成失敗: {result.get('error', 'Unknown')}"

    async def _internal_list_hives(self) -> str:
        """内部ツール: Hive一覧を取得"""
        result = await self.handle_list_hives({})
        hives = result.get("hives", [])
        if not hives:
            return "Hiveはまだありません。create_hiveで新しいHiveを作成してください。"
        lines = [f"- {h['hive_id']}: {h['name']} ({h['status']})" for h in hives]
        return "Hive一覧:\n" + "\n".join(lines)

    async def _internal_evaluate_task(
        self,
        complexity: int = 3,
        risk: int = 3,
        urgency: int = 3,
    ) -> str:
        """内部ツール: タスク特徴量を評価してテンプレートを提案

        Swarming Protocolを使用してタスク特徴量から
        最適なColonyテンプレートを選択・提案する。
        """
        features = SwarmingFeatures(
            complexity=complexity,
            risk=risk,
            urgency=urgency,
        )
        evaluation = self._swarming_engine.evaluate(features)
        config = evaluation["config"]

        return (
            f"テンプレート推奨: {evaluation['template'].upper()}\n"
            f"理由: {evaluation['reason']}\n"
            f"構成: Workers {config['min_workers']}-{config['max_workers']}, "
            f"GuardBee={'有' if config['guard_bee'] else '無'}, "
            f"Reviewer={'有' if config['reviewer'] else '無'}, "
            f"リトライ上限={config['retry_limit']}"
        )

    async def _get_hive_status(self, hive_id: str | None = None) -> str:
        """Hive/Colonyの状態を取得"""
        result = await self.handle_get_status({"hive_id": hive_id})
        return str(result)

    async def run_with_llm(
        self, message: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """LLMを使用してメッセージを処理

        Args:
            message: ユーザーからのメッセージ
            context: 追加コンテキスト情報

        Returns:
            処理結果
        """
        from ..llm.runner import AgentContext

        runner = await self._get_agent_runner()

        # コンテキストを構築
        agent_context = AgentContext(
            run_id=self.current_session.session_id if self.current_session else "standalone",
            working_directory=context.get("working_directory", ".") if context else ".",
            metadata=context or {},
        )

        try:
            result = await runner.run(message, agent_context)

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
            logger.exception(f"LLM実行エラー: {e}")
            return {
                "status": "error",
                "error": str(e),
            }
