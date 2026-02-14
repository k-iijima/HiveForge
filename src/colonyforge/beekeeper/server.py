"""Beekeeper MCPサーバー

ユーザー/Copilotとの対話窓口。
Hive/Colonyを管理し、Queen Beeに作業を依頼する。
LLMを使用してユーザーの意図を解釈し、適切な対応を行う。

実装は以下のMixinに分割:
- HiveHandlersMixin: Hive/Colony CRUD + ステータス
- UserHandlersMixin: メッセージ・承認・拒否・緊急停止
- LLMIntegrationMixin: LLMクライアント・内部ツール・run_with_llm
- QueenDelegationMixin: Queen Bee委譲・パイプライン・結果整形
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..core import AkashicRecord
from ..core.ar.hive_storage import HiveStore
from ..core.config import LLMConfig
from ..core.swarming import SwarmingEngine
from ..queen_bee.server import QueenBeeMCPServer
from .hive_handlers import HiveHandlersMixin
from .llm_integration import LLMIntegrationMixin
from .queen_delegation import QueenDelegationMixin
from .ra_integration import RequirementAnalysisMixin
from .session import BeekeeperSession, BeekeeperSessionManager
from .tool_definitions import get_mcp_tool_definitions
from .user_handlers import UserHandlersMixin

logger = logging.getLogger(__name__)


@dataclass
class BeekeeperMCPServer(
    HiveHandlersMixin,
    UserHandlersMixin,
    LLMIntegrationMixin,
    QueenDelegationMixin,
    RequirementAnalysisMixin,
):
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
        from ..llm.client import LLMClient
        from ..llm.runner import AgentRunner

        self._llm_client: LLMClient | None = None
        self._agent_runner: AgentRunner | None = None
        self._queens: dict[str, QueenBeeMCPServer] = {}  # colony_id -> Queen Bee
        self._swarming_engine = SwarmingEngine()
        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        self._ra_enabled: bool = True
        self._ra_components: dict[str, Any] = {}
        # HiveStoreが未設定の場合、ARと同じVaultパスで作成
        if self.hive_store is None:
            self.hive_store = HiveStore(self.ar.vault_path)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """MCPツール定義を取得

        ユーザー/CopilotがBeekeeperに対して実行できるツール。
        """
        return get_mcp_tool_definitions()

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
