"""Beekeeperセッション管理

ユーザーとの対話セッションを管理する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ulid import ULID


class SessionState(str, Enum):
    """セッション状態"""

    IDLE = "idle"  # 待機中
    ACTIVE = "active"  # アクティブ
    BUSY = "busy"  # 処理中
    WAITING_USER = "waiting_user"  # ユーザー入力待ち
    SUSPENDED = "suspended"  # 一時停止


@dataclass
class ActiveColony:
    """アクティブなColony情報"""

    colony_id: str
    queen_bee_id: str | None = None
    last_interaction: datetime | None = None


@dataclass
class BeekeeperSession:
    """Beekeeperセッション

    ユーザーとの対話を管理し、Hive/Colonyへの指示を仲介する。
    """

    session_id: str = field(default_factory=lambda: str(ULID()))
    hive_id: str | None = None
    state: SessionState = SessionState.IDLE
    active_colonies: dict[str, ActiveColony] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime | None = None

    def activate(self, hive_id: str) -> None:
        """セッションをアクティブ化"""
        self.hive_id = hive_id
        self.state = SessionState.ACTIVE
        self.last_activity = datetime.now(UTC)

    def add_colony(self, colony_id: str, queen_bee_id: str | None = None) -> None:
        """Colonyを追加"""
        self.active_colonies[colony_id] = ActiveColony(
            colony_id=colony_id,
            queen_bee_id=queen_bee_id,
            last_interaction=datetime.now(UTC),
        )

    def remove_colony(self, colony_id: str) -> None:
        """Colonyを削除"""
        self.active_colonies.pop(colony_id, None)

    def set_busy(self) -> None:
        """処理中に設定"""
        self.state = SessionState.BUSY
        self.last_activity = datetime.now(UTC)

    def set_waiting_user(self) -> None:
        """ユーザー入力待ちに設定"""
        self.state = SessionState.WAITING_USER
        self.last_activity = datetime.now(UTC)

    def set_active(self) -> None:
        """アクティブに設定"""
        self.state = SessionState.ACTIVE
        self.last_activity = datetime.now(UTC)

    def suspend(self) -> None:
        """一時停止"""
        self.state = SessionState.SUSPENDED
        self.last_activity = datetime.now(UTC)

    def resume(self) -> None:
        """再開"""
        self.state = SessionState.ACTIVE
        self.last_activity = datetime.now(UTC)

    def update_context(self, key: str, value: Any) -> None:
        """コンテキストを更新"""
        self.context[key] = value
        self.last_activity = datetime.now(UTC)

    def get_context(self, key: str, default: Any = None) -> Any:
        """コンテキストを取得"""
        return self.context.get(key, default)

    def clear_context(self) -> None:
        """コンテキストをクリア"""
        self.context.clear()


@dataclass
class UserInstruction:
    """ユーザー指示"""

    instruction_id: str = field(default_factory=lambda: str(ULID()))
    session_id: str = ""
    content: str = ""
    target_colony: str | None = None
    priority: str = "normal"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BeekeeperResponse:
    """Beekeeperレスポンス"""

    response_id: str = field(default_factory=lambda: str(ULID()))
    instruction_id: str = ""
    content: str = ""
    status: str = "success"
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BeekeeperSessionManager:
    """セッションマネージャー

    複数のセッションを管理する。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, BeekeeperSession] = {}

    def create_session(self, hive_id: str | None = None) -> BeekeeperSession:
        """新しいセッションを作成"""
        session = BeekeeperSession()
        if hive_id:
            session.activate(hive_id)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> BeekeeperSession | None:
        """セッションを取得"""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """セッションを終了"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> list[BeekeeperSession]:
        """全セッションを取得"""
        return list(self._sessions.values())

    def get_active_sessions(self) -> list[BeekeeperSession]:
        """アクティブなセッションを取得"""
        return [
            s
            for s in self._sessions.values()
            if s.state in (SessionState.ACTIVE, SessionState.BUSY)
        ]
