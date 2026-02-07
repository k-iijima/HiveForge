"""エージェントアクティビティバス

各エージェントの活動（LLM呼び出し、MCPツール操作、メッセージ送受信）を
リアルタイムに購読・配信するイベントバス。

VS Code拡張のAgent Monitorパネルにストリーム配信する基盤。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)


# =============================================================================
# 列挙型
# =============================================================================


class ActivityType(StrEnum):
    """アクティビティの種別"""

    # LLM関連
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"

    # MCP関連
    MCP_TOOL_CALL = "mcp.tool_call"
    MCP_TOOL_RESULT = "mcp.tool_result"

    # エージェントライフサイクル
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"

    # エージェント間メッセージ
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    # タスク関連
    TASK_ASSIGNED = "task.assigned"
    TASK_PROGRESS = "task.progress"


class AgentRole(StrEnum):
    """エージェントの役割"""

    BEEKEEPER = "beekeeper"
    QUEEN_BEE = "queen_bee"
    WORKER_BEE = "worker_bee"


# =============================================================================
# データクラス
# =============================================================================


@dataclass(frozen=True)
class AgentInfo:
    """エージェントの識別情報"""

    agent_id: str
    role: AgentRole
    hive_id: str
    colony_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """辞書に変換"""
        d: dict[str, Any] = {
            "agent_id": self.agent_id,
            "role": str(self.role),
            "hive_id": self.hive_id,
        }
        if self.colony_id is not None:
            d["colony_id"] = self.colony_id
        return d


@dataclass
class ActivityEvent:
    """アクティビティイベント

    エージェントの活動を表す1つのイベント。
    """

    activity_type: ActivityType
    agent: AgentInfo
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid4())[:8])

    def to_dict(self) -> dict[str, Any]:
        """SSE配信用の辞書に変換"""
        return {
            "event_id": self.event_id,
            "activity_type": str(self.activity_type),
            "agent": self.agent.to_dict(),
            "summary": self.summary,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


# =============================================================================
# ActivityBus
# =============================================================================

# サブスクライバーの型
ActivityHandler = Callable[[ActivityEvent], Awaitable[None]]

# 最近のイベント保持上限
MAX_RECENT_EVENTS = 100


class ActivityBus:
    """エージェントアクティビティバス（シングルトン）

    各エージェントの活動をリアルタイムに配信する。
    サブスクライバーパターンで、SSEエンドポイントやWebviewに接続。
    """

    _instance: ActivityBus | None = None

    def __init__(self) -> None:
        self._subscribers: list[ActivityHandler] = []
        self._recent_events: deque[ActivityEvent] = deque(maxlen=MAX_RECENT_EVENTS)
        self._active_agents: dict[str, AgentInfo] = {}  # agent_id -> AgentInfo

    @classmethod
    def get_instance(cls) -> ActivityBus:
        """シングルトンインスタンスを取得"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """シングルトンをリセット（テスト用）"""
        cls._instance = None

    def subscribe(self, handler: ActivityHandler) -> None:
        """イベントハンドラーを登録"""
        self._subscribers.append(handler)

    def unsubscribe(self, handler: ActivityHandler) -> None:
        """イベントハンドラーを解除"""
        self._subscribers = [h for h in self._subscribers if h is not handler]

    async def emit(self, event: ActivityEvent) -> None:
        """イベントを発行

        全てのサブスクライバーに通知し、履歴に保存する。
        サブスクライバーのエラーは他のサブスクライバーに影響しない。
        """
        # 履歴に保存
        self._recent_events.append(event)

        # アクティブエージェントの追跡
        if event.activity_type == ActivityType.AGENT_STARTED:
            self._active_agents[event.agent.agent_id] = event.agent
        elif event.activity_type == ActivityType.AGENT_COMPLETED:
            self._active_agents.pop(event.agent.agent_id, None)

        # サブスクライバーに通知
        for handler in self._subscribers:
            try:
                await handler(event)
            except Exception:
                logger.exception(f"アクティビティハンドラーエラー: {handler.__name__}")

    def get_recent_events(self, limit: int = MAX_RECENT_EVENTS) -> list[ActivityEvent]:
        """最近のイベント履歴を取得"""
        events = list(self._recent_events)
        return events[-limit:]

    def get_active_agents(self) -> list[AgentInfo]:
        """アクティブなエージェント一覧を取得"""
        return list(self._active_agents.values())

    def get_hierarchy(self) -> dict[str, Any]:
        """Hive → Colony → Agent の階層構造を取得

        Returns:
            {
                "hive-id": {
                    "beekeeper": AgentInfo | None,
                    "colonies": {
                        "colony-id": {
                            "queen_bee": AgentInfo | None,
                            "workers": [AgentInfo, ...]
                        }
                    }
                }
            }
        """
        hierarchy: dict[str, Any] = {}

        for agent in self._active_agents.values():
            hive_id = agent.hive_id

            if hive_id not in hierarchy:
                hierarchy[hive_id] = {
                    "beekeeper": None,
                    "colonies": {},
                }

            hive = hierarchy[hive_id]

            if agent.role == AgentRole.BEEKEEPER:
                hive["beekeeper"] = agent
            elif agent.colony_id:
                if agent.colony_id not in hive["colonies"]:
                    hive["colonies"][agent.colony_id] = {
                        "queen_bee": None,
                        "workers": [],
                    }
                colony = hive["colonies"][agent.colony_id]

                if agent.role == AgentRole.QUEEN_BEE:
                    colony["queen_bee"] = agent
                elif agent.role == AgentRole.WORKER_BEE:
                    colony["workers"].append(agent)

        return hierarchy
