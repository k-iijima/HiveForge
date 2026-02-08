"""Beekeeper MCPサーバー

ユーザー/Copilotとの対話窓口。
Hive/Colonyを管理し、Queen Beeに作業を依頼する。
LLMを使用してユーザーの意図を解釈し、適切な対応を行う。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.ar.hive_projections import build_hive_aggregate
from ..core.ar.hive_storage import HiveStore
from ..core.config import LLMConfig
from ..core.events import (
    ColonyCreatedEvent,
    EmergencyStopEvent,
    HiveCreatedEvent,
    RequirementApprovedEvent,
    RequirementCreatedEvent,
    RequirementRejectedEvent,
)
from ..core.models.action_class import TrustLevel
from ..core.swarming import SwarmingEngine, SwarmingFeatures
from ..queen_bee.server import QueenBeeMCPServer
from .session import BeekeeperSession, BeekeeperSessionManager
from .tool_definitions import get_mcp_tool_definitions

logger = logging.getLogger(__name__)


@dataclass
class BeekeeperMCPServer:
    """Beekeeper MCPサーバー

    ユーザーとの対話を管理し、Hive/Colonyへの指示を仲介する。
    MCPプロトコルでVS Code拡張（Copilot）と通信する。
    LLMを使用してユーザーの意図を解釈する。
    """

    ar: AkashicRecord
    hive_store: HiveStore | None = None
    session_manager: BeekeeperSessionManager = field(default_factory=BeekeeperSessionManager)
    llm_config: LLMConfig | None = None  # エージェント別LLM設定
    current_session: BeekeeperSession | None = None

    def __post_init__(self) -> None:
        """初期化"""
        self._llm_client = None
        self._agent_runner = None
        self._queens: dict[str, QueenBeeMCPServer] = {}  # colony_id -> Queen Bee
        self._swarming_engine = SwarmingEngine()
        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        # HiveStoreが未設定の場合、ARと同じVaultパスで作成
        if self.hive_store is None:
            self.hive_store = HiveStore(self.ar.vault_path)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得

        ユーザー/CopilotがBeekeeperに対して実行できるツール。
        """
        return get_mcp_tool_definitions()

    # -------------------------------------------------------------------------
    # ハンドラ実装
    # -------------------------------------------------------------------------

    async def handle_send_message(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """メッセージ送信ハンドラ

        ユーザーからのメッセージを受け取り、LLMで解釈して適切な対応を行う。
        """
        message = arguments.get("message", "")
        context = arguments.get("context", {})

        # セッションがなければ作成
        if not self.current_session:
            self.current_session = self.session_manager.create_session()

        self.current_session.set_busy()

        try:
            # LLMで意図を解釈して実行
            result = await self.run_with_llm(message, context)

            self.current_session.set_active()

            if result.get("status") == "error":
                return {
                    "status": "error",
                    "session_id": self.current_session.session_id,
                    "error": result.get("error", "Unknown error"),
                }

            return {
                "status": "success",
                "session_id": self.current_session.session_id,
                "response": result.get("output", ""),
                "actions_taken": result.get("tool_calls_made", 0),
            }

        except Exception as e:
            logger.exception(f"メッセージ処理エラー: {e}")
            self.current_session.set_active()
            return {
                "status": "error",
                "session_id": self.current_session.session_id,
                "error": str(e),
            }

    async def handle_get_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """ステータス取得ハンドラ

        HiveStore投影から実データを取得する。
        hive_idが指定されていればそのHiveの詳細を、
        なければ全Hiveの概要を返す。
        """
        hive_id = arguments.get("hive_id")
        include_colonies = arguments.get("include_colonies", True)

        # 現在のセッション状態を返す
        session_info = None
        if self.current_session:
            session_info = {
                "session_id": self.current_session.session_id,
                "state": self.current_session.state.value,
                "hive_id": self.current_session.hive_id,
                "active_colonies": list(self.current_session.active_colonies.keys()),
            }

        assert self.hive_store is not None

        # Hive情報をHiveStore投影から取得
        hives_data: list[dict[str, Any]] = []
        colonies_data: list[dict[str, Any]] | None = [] if include_colonies else None

        if hive_id:
            # 特定Hiveの詳細
            events = list(self.hive_store.replay(hive_id))
            if events:
                aggregate = build_hive_aggregate(hive_id, events)
                hive_info: dict[str, Any] = {
                    "hive_id": hive_id,
                    "name": aggregate.name,
                    "status": aggregate.state.value,
                }
                if include_colonies and colonies_data is not None:
                    for cid, colony in aggregate.colonies.items():
                        colonies_data.append(
                            {
                                "colony_id": cid,
                                "hive_id": hive_id,
                                "goal": colony.goal,
                                "status": colony.state.value,
                            }
                        )
                    hive_info["colony_count"] = len(aggregate.colonies)
                hives_data.append(hive_info)
        else:
            # 全Hiveの概要
            for h_id in self.hive_store.list_hives():
                events = list(self.hive_store.replay(h_id))
                if events:
                    aggregate = build_hive_aggregate(h_id, events)
                    hive_info = {
                        "hive_id": h_id,
                        "name": aggregate.name,
                        "status": aggregate.state.value,
                        "colony_count": len(aggregate.colonies),
                    }
                    hives_data.append(hive_info)

                    if include_colonies and colonies_data is not None:
                        for cid, colony in aggregate.colonies.items():
                            colonies_data.append(
                                {
                                    "colony_id": cid,
                                    "hive_id": h_id,
                                    "goal": colony.goal,
                                    "status": colony.state.value,
                                }
                            )

        return {
            "status": "success",
            "session": session_info,
            "hives": hives_data,
            "colonies": colonies_data,
        }

    async def handle_create_hive(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive作成ハンドラ

        HiveCreatedイベントを発行し、HiveStoreに永続化する。
        セッションをこのHiveにアクティブ化する。
        """
        name = arguments.get("name", "")
        goal = arguments.get("goal", "")

        hive_id = generate_event_id()

        # セッションをアクティブ化
        if not self.current_session:
            self.current_session = self.session_manager.create_session()
        self.current_session.activate(hive_id)

        # HiveCreatedイベントを発行してHiveStoreに永続化
        assert self.hive_store is not None
        event = HiveCreatedEvent(
            run_id=hive_id,
            actor="beekeeper",
            payload={
                "hive_id": hive_id,
                "name": name,
                "description": goal,
            },
        )
        self.hive_store.append(event, hive_id)

        return {
            "status": "created",
            "hive_id": hive_id,
            "name": name,
            "goal": goal,
        }

    async def handle_create_colony(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony作成ハンドラ

        ColonyCreatedイベントを発行し、HiveStoreに永続化する。
        Hiveの存在確認を行い、セッションにColonyを追加する。
        """
        hive_id = arguments.get("hive_id", "")
        name = arguments.get("name", "")
        domain = arguments.get("domain", "")

        # Hiveの存在確認
        assert self.hive_store is not None
        events = list(self.hive_store.replay(hive_id))
        if not events:
            return {
                "status": "error",
                "error": f"Hive {hive_id} not found",
            }

        colony_id = generate_event_id()

        # セッションにColonyを追加
        if self.current_session:
            self.current_session.add_colony(colony_id)

        # ColonyCreatedイベントを発行してHiveStoreに永続化
        event = ColonyCreatedEvent(
            run_id=colony_id,
            actor="beekeeper",
            payload={
                "colony_id": colony_id,
                "hive_id": hive_id,
                "name": name,
                "goal": domain,
            },
        )
        self.hive_store.append(event, hive_id)

        return {
            "status": "created",
            "colony_id": colony_id,
            "hive_id": hive_id,
            "name": name,
            "domain": domain,
        }

    async def handle_list_hives(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive一覧ハンドラ

        HiveStore投影から全Hiveの一覧を取得する。
        """
        assert self.hive_store is not None
        hives: list[dict[str, Any]] = []

        for hive_id in self.hive_store.list_hives():
            events = list(self.hive_store.replay(hive_id))
            if events:
                aggregate = build_hive_aggregate(hive_id, events)
                hives.append(
                    {
                        "hive_id": hive_id,
                        "name": aggregate.name,
                        "status": aggregate.state.value,
                        "colony_count": len(aggregate.colonies),
                    }
                )

        return {
            "status": "success",
            "hives": hives,
        }

    async def handle_list_colonies(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony一覧ハンドラ

        HiveStore投影から指定HiveのColony一覧を取得する。
        """
        hive_id = arguments.get("hive_id", "")

        assert self.hive_store is not None
        events = list(self.hive_store.replay(hive_id))
        if not events:
            return {
                "status": "error",
                "error": f"Hive {hive_id} not found",
            }

        aggregate = build_hive_aggregate(hive_id, events)
        colonies: list[dict[str, Any]] = []
        for cid, colony in aggregate.colonies.items():
            colonies.append(
                {
                    "colony_id": cid,
                    "hive_id": hive_id,
                    "name": colony.metadata.get("name", colony.goal),
                    "goal": colony.goal,
                    "status": colony.state.value,
                }
            )

        return {
            "status": "success",
            "hive_id": hive_id,
            "colonies": colonies,
        }

    async def handle_approve(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """承認ハンドラ

        RequirementApprovedイベントを発行してARに記録する。
        pending_requests に対応する Future があれば解決する。
        """
        request_id = arguments.get("request_id", "")
        comment = arguments.get("comment", "")

        # RequirementApprovedイベントを発行
        event = RequirementApprovedEvent(
            run_id=request_id,
            actor="beekeeper",
            payload={
                "request_id": request_id,
                "comment": comment,
                "decided_by": "user",
            },
        )
        self.ar.append(event, request_id)

        logger.info(f"承認: request_id={request_id}, comment={comment}")

        # pending_requests の Future を解決
        future = self._pending_requests.get(request_id)
        if future and not future.done():
            future.set_result(f"approved: {comment}")

        return {
            "status": "approved",
            "request_id": request_id,
            "comment": comment,
        }

    async def handle_reject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """拒否ハンドラ

        RequirementRejectedイベントを発行してARに記録する。
        pending_requests に対応する Future があれば拒否結果で解決する。
        """
        request_id = arguments.get("request_id", "")
        reason = arguments.get("reason", "")

        # RequirementRejectedイベントを発行
        event = RequirementRejectedEvent(
            run_id=request_id,
            actor="beekeeper",
            payload={
                "request_id": request_id,
                "reason": reason,
                "decided_by": "user",
            },
        )
        self.ar.append(event, request_id)

        logger.info(f"拒否: request_id={request_id}, reason={reason}")

        # pending_requests の Future を拒否結果で解決
        future = self._pending_requests.get(request_id)
        if future and not future.done():
            future.set_result(f"rejected: {reason}")

        return {
            "status": "rejected",
            "request_id": request_id,
            "reason": reason,
        }

    async def handle_emergency_stop(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """緊急停止ハンドラ

        EmergencyStopイベントを発行してARに記録する。
        セッションを一時停止状態にし、全Queen Beeを閉じる。
        scope=hive/colonyの場合は対象を限定する。
        """
        reason = arguments.get("reason", "")
        scope = arguments.get("scope", "all")
        target_id = arguments.get("target_id")

        logger.warning(f"緊急停止: {reason} (scope={scope}, target={target_id})")

        # EmergencyStopイベントを発行
        event = EmergencyStopEvent(
            run_id=target_id or "system",
            actor="beekeeper",
            payload={
                "reason": reason,
                "scope": scope,
                "target_id": target_id,
            },
        )
        # ARに記録（対象IDがあればそのストリームに、なければ"system"に）
        self.ar.append(event, target_id or "system")

        # セッションを一時停止
        if self.current_session:
            self.current_session.suspend()

        # scope=all の場合、全Queen Beeを閉じる
        if scope == "all":
            for queen in self._queens.values():
                await queen.close()
            self._queens.clear()
        elif scope == "colony" and target_id:
            # 対象Colonyのみ閉じる
            if target_id in self._queens:
                await self._queens[target_id].close()
                del self._queens[target_id]

        return {
            "status": "stopped",
            "reason": reason,
            "scope": scope,
            "target_id": target_id,
        }

    # -------------------------------------------------------------------------
    # LLM統合
    # -------------------------------------------------------------------------

    async def _get_llm_client(self):
        """LLMクライアントを取得（遅延初期化）"""
        if self._llm_client is None:
            from ..llm.client import LLMClient

            self._llm_client = LLMClient(config=self.llm_config)
        return self._llm_client

    async def _get_agent_runner(self):
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
        from ..llm.tools import ToolDefinition

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

    async def _delegate_to_queen(
        self, colony_id: str, task: str, context: dict[str, Any] | None = None
    ) -> str:
        """Queen Beeにタスクを委譲"""
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

    async def _ask_user(
        self,
        question: str,
        options: list[str] | None = None,
        timeout: float | None = None,
    ) -> str:
        """ユーザーに確認を求め、応答を非同期に待機する

        RequirementCreatedEvent を AR に記録し、asyncio.Future で
        ユーザーの approve/reject を待つ。

        Args:
            question: 質問内容
            options: 選択肢（任意）
            timeout: タイムアウト秒数（None の場合は無制限）

        Returns:
            ユーザーの応答結果文字列
        """
        request_id = generate_event_id()
        logger.info(f"ユーザーに確認: {question} (request_id={request_id})")

        # RequirementCreatedEvent を AR に記録
        event = RequirementCreatedEvent(
            run_id=str(request_id),
            actor="beekeeper",
            payload={
                "request_id": str(request_id),
                "description": question,
                "options": options or [],
            },
        )
        self.ar.append(event, str(request_id))

        # セッション状態を WAITING_USER に設定
        if self.current_session:
            self.current_session.set_waiting_user()

        # Future を作成して pending_requests に登録
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_requests[str(request_id)] = future

        try:
            # タイムアウト付きで応答を待機
            if timeout is not None:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
        except asyncio.TimeoutError:
            result = f"タイムアウト: {question} (timeout={timeout}s)"
            logger.warning(f"ユーザー応答タイムアウト: request_id={request_id}")
        finally:
            # pending_requests をクリーンアップ
            self._pending_requests.pop(str(request_id), None)

            # セッション状態を ACTIVE に復元
            if self.current_session:
                self.current_session.set_active()

        return result

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

    async def close(self) -> None:
        """リソースを解放"""
        # 全Queen Beeを閉じる
        for queen in self._queens.values():
            await queen.close()
        self._queens.clear()

        if self._llm_client:
            await self._llm_client.close()
            self._llm_client = None
        self._agent_runner = None

    # -------------------------------------------------------------------------
    # ディスパッチャ
    # -------------------------------------------------------------------------

    async def dispatch_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール呼び出しをディスパッチ"""
        handlers = {
            "send_message": self.handle_send_message,
            "get_status": self.handle_get_status,
            "create_hive": self.handle_create_hive,
            "create_colony": self.handle_create_colony,
            "list_hives": self.handle_list_hives,
            "list_colonies": self.handle_list_colonies,
            "approve": self.handle_approve,
            "reject": self.handle_reject,
            "emergency_stop": self.handle_emergency_stop,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        return await handler(arguments)
