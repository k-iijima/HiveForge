"""Beekeeper MCPサーバー

ユーザー/Copilotとの対話窓口。
Hive/Colonyを管理し、Queen Beeに作業を依頼する。
LLMを使用してユーザーの意図を解釈し、適切な対応を行う。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.config import LLMConfig
from ..queen_bee.server import QueenBeeMCPServer
from .session import BeekeeperSession, BeekeeperSessionManager, SessionState

logger = logging.getLogger(__name__)


@dataclass
class BeekeeperMCPServer:
    """Beekeeper MCPサーバー

    ユーザーとの対話を管理し、Hive/Colonyへの指示を仲介する。
    MCPプロトコルでVS Code拡張（Copilot）と通信する。
    LLMを使用してユーザーの意図を解釈する。
    """

    ar: AkashicRecord
    session_manager: BeekeeperSessionManager = field(default_factory=BeekeeperSessionManager)
    llm_config: LLMConfig | None = None  # エージェント別LLM設定
    current_session: BeekeeperSession | None = None

    def __post_init__(self) -> None:
        """初期化"""
        self._llm_client = None
        self._agent_runner = None
        self._queens: dict[str, QueenBeeMCPServer] = {}  # colony_id -> Queen Bee

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得

        ユーザー/CopilotがBeekeeperに対して実行できるツール。
        """
        return [
            {
                "name": "send_message",
                "description": "Beekeeperにメッセージを送信して作業を依頼する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "ユーザーからのメッセージ（自然言語）",
                        },
                        "context": {
                            "type": "object",
                            "description": "追加コンテキスト情報",
                            "properties": {
                                "working_directory": {"type": "string"},
                                "selected_files": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["message"],
                },
            },
            {
                "name": "get_status",
                "description": "Hive/Colonyの現在の状態を取得",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "hive_id": {
                            "type": "string",
                            "description": "Hive ID（省略時は現在のHive）",
                        },
                        "include_colonies": {
                            "type": "boolean",
                            "description": "Colony情報を含めるか",
                            "default": True,
                        },
                    },
                },
            },
            {
                "name": "create_hive",
                "description": "新しいHiveを作成",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Hive名"},
                        "goal": {"type": "string", "description": "プロジェクトの目標"},
                    },
                    "required": ["name", "goal"],
                },
            },
            {
                "name": "create_colony",
                "description": "新しいColonyを作成",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "hive_id": {"type": "string", "description": "所属Hive ID"},
                        "name": {"type": "string", "description": "Colony名"},
                        "domain": {
                            "type": "string",
                            "description": "専門領域の説明",
                        },
                    },
                    "required": ["hive_id", "name", "domain"],
                },
            },
            {
                "name": "list_hives",
                "description": "Hive一覧を取得",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "list_colonies",
                "description": "Colony一覧を取得",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "hive_id": {"type": "string", "description": "Hive ID"},
                    },
                    "required": ["hive_id"],
                },
            },
            {
                "name": "approve",
                "description": "承認待ちの操作を承認する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string", "description": "承認リクエストID"},
                        "comment": {"type": "string", "description": "コメント"},
                    },
                    "required": ["request_id"],
                },
            },
            {
                "name": "reject",
                "description": "承認待ちの操作を拒否する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string", "description": "承認リクエストID"},
                        "reason": {"type": "string", "description": "拒否理由"},
                    },
                    "required": ["request_id", "reason"],
                },
            },
            {
                "name": "emergency_stop",
                "description": "全ての作業を緊急停止する",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "停止理由"},
                        "scope": {
                            "type": "string",
                            "enum": ["all", "hive", "colony"],
                            "description": "停止範囲",
                            "default": "all",
                        },
                        "target_id": {
                            "type": "string",
                            "description": "対象ID（scope=hive/colonyの場合）",
                        },
                    },
                    "required": ["reason"],
                },
            },
        ]

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
        """ステータス取得ハンドラ"""
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

        return {
            "status": "success",
            "session": session_info,
            "hives": [],  # TODO: AR/Projectionから取得
            "colonies": [] if include_colonies else None,
        }

    async def handle_create_hive(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive作成ハンドラ"""
        name = arguments.get("name", "")
        goal = arguments.get("goal", "")

        hive_id = generate_event_id()

        # セッションをアクティブ化
        if not self.current_session:
            self.current_session = self.session_manager.create_session()
        self.current_session.activate(hive_id)

        # TODO: HiveCreatedイベントを発行

        return {
            "status": "created",
            "hive_id": hive_id,
            "name": name,
            "goal": goal,
        }

    async def handle_create_colony(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony作成ハンドラ"""
        hive_id = arguments.get("hive_id", "")
        name = arguments.get("name", "")
        domain = arguments.get("domain", "")

        colony_id = generate_event_id()

        # セッションにColonyを追加
        if self.current_session:
            self.current_session.add_colony(colony_id)

        # TODO: ColonyCreatedイベントを発行

        return {
            "status": "created",
            "colony_id": colony_id,
            "hive_id": hive_id,
            "name": name,
            "domain": domain,
        }

    async def handle_list_hives(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Hive一覧ハンドラ"""
        # TODO: AR/Projectionから取得
        return {
            "status": "success",
            "hives": [],
        }

    async def handle_list_colonies(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Colony一覧ハンドラ"""
        hive_id = arguments.get("hive_id", "")
        # TODO: AR/Projectionから取得
        return {
            "status": "success",
            "hive_id": hive_id,
            "colonies": [],
        }

    async def handle_approve(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """承認ハンドラ"""
        request_id = arguments.get("request_id", "")
        comment = arguments.get("comment", "")

        # TODO: 承認処理を実装
        return {
            "status": "approved",
            "request_id": request_id,
            "comment": comment,
        }

    async def handle_reject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """拒否ハンドラ"""
        request_id = arguments.get("request_id", "")
        reason = arguments.get("reason", "")

        # TODO: 拒否処理を実装
        return {
            "status": "rejected",
            "request_id": request_id,
            "reason": reason,
        }

    async def handle_emergency_stop(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """緊急停止ハンドラ"""
        reason = arguments.get("reason", "")
        scope = arguments.get("scope", "all")
        target_id = arguments.get("target_id")

        # TODO: 緊急停止処理を実装
        logger.warning(f"緊急停止: {reason} (scope={scope}, target={target_id})")

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
            from ..llm.runner import AgentRunner
            from ..llm.tools import ToolDefinition

            client = await self._get_llm_client()
            self._agent_runner = AgentRunner(client, agent_type="beekeeper")

            # Beekeeperが使える内部ツールを登録
            self._register_internal_tools()

        return self._agent_runner

    def _register_internal_tools(self) -> None:
        """Beekeeperが内部で使えるツールを登録"""
        from ..llm.tools import ToolDefinition

        # Queen Beeに作業を依頼するツール
        delegate_to_queen = ToolDefinition(
            name="delegate_to_queen",
            description="Queen Beeにタスクを委譲する",
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

        self._agent_runner.register_tool(delegate_to_queen)
        self._agent_runner.register_tool(ask_user)
        self._agent_runner.register_tool(get_hive_status)

    async def _delegate_to_queen(
        self, colony_id: str, task: str, context: dict[str, Any] | None = None
    ) -> str:
        """Queen Beeにタスクを委譲"""
        logger.info(f"タスクをQueen Bee ({colony_id}) に委譲: {task}")

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
        result = await queen.dispatch_tool(
            "execute_goal",
            {
                "run_id": run_id,
                "goal": task,
                "context": context or {},
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

    async def _ask_user(self, question: str, options: list[str] | None = None) -> str:
        """ユーザーに確認を求める"""
        # TODO: VS Code拡張に通知してユーザー入力を待つ
        logger.info(f"ユーザーに確認: {question}")
        if self.current_session:
            self.current_session.set_waiting_user()
        return f"ユーザーに確認を求めています: {question}"

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
