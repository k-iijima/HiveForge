"""Beekeeper MCPハンドラ

ユーザー操作をHive/Colonyに伝達するMCPツールハンドラ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..queen_bee.communication import ColonyMessenger, MessagePriority, MessageType
from .session import BeekeeperSession, BeekeeperSessionManager, UserInstruction


@dataclass
class InstructionResult:
    """指示実行結果"""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class BeekeeperHandler:
    """Beekeeperハンドラ

    ユーザーからの指示を受け取り、適切なColony/Queen Beeに伝達する。
    """

    def __init__(
        self,
        session_manager: BeekeeperSessionManager | None = None,
        messenger: ColonyMessenger | None = None,
    ) -> None:
        self._session_manager = session_manager or BeekeeperSessionManager()
        self._messenger = messenger or ColonyMessenger()
        self._instruction_history: list[UserInstruction] = []

    def start_session(self, hive_id: str) -> BeekeeperSession:
        """セッションを開始

        Args:
            hive_id: 対象のHive ID

        Returns:
            作成されたセッション
        """
        return self._session_manager.create_session(hive_id)

    def get_session(self, session_id: str) -> BeekeeperSession | None:
        """セッションを取得"""
        return self._session_manager.get_session(session_id)

    def end_session(self, session_id: str) -> bool:
        """セッションを終了"""
        return self._session_manager.close_session(session_id)

    def send_instruction(
        self,
        session_id: str,
        content: str,
        target_colony: str | None = None,
        priority: str = "normal",
    ) -> InstructionResult:
        """指示を送信

        Args:
            session_id: セッションID
            content: 指示内容
            target_colony: 対象Colony（Noneの場合は全体）
            priority: 優先度

        Returns:
            実行結果
        """
        session = self._session_manager.get_session(session_id)
        if not session:
            return InstructionResult(
                success=False, message="Session not found", data={"session_id": session_id}
            )

        instruction = UserInstruction(
            session_id=session_id,
            content=content,
            target_colony=target_colony,
            priority=priority,
        )
        self._instruction_history.append(instruction)

        session.set_busy()

        # Colony が指定されている場合はそのColonyに送信
        if target_colony:
            if target_colony not in session.active_colonies:
                session.add_colony(target_colony)

            self._messenger.register_colony(target_colony)
            self._messenger.send(
                from_colony="beekeeper",
                to_colony=target_colony,
                message_type=MessageType.REQUEST,
                payload={"instruction": content, "instruction_id": instruction.instruction_id},
                priority=self._map_priority(priority),
            )

            return InstructionResult(
                success=True,
                message=f"Instruction sent to {target_colony}",
                data={"instruction_id": instruction.instruction_id},
            )

        # Colonyが指定されていない場合はブロードキャスト
        self._messenger.register_colony("beekeeper")
        for colony_id in session.active_colonies:
            self._messenger.register_colony(colony_id)

        if session.active_colonies:
            self._messenger.broadcast(
                from_colony="beekeeper",
                message_type=MessageType.NOTIFICATION,
                payload={"instruction": content, "instruction_id": instruction.instruction_id},
                priority=self._map_priority(priority),
            )

        session.set_active()

        return InstructionResult(
            success=True,
            message="Instruction broadcast",
            data={
                "instruction_id": instruction.instruction_id,
                "target_colonies": list(session.active_colonies.keys()),
            },
        )

    def _map_priority(self, priority: str) -> MessagePriority:
        """優先度をマッピング"""
        mapping = {
            "urgent": MessagePriority.URGENT,
            "high": MessagePriority.HIGH,
            "normal": MessagePriority.NORMAL,
            "low": MessagePriority.LOW,
        }
        return mapping.get(priority, MessagePriority.NORMAL)

    def add_colony_to_session(
        self, session_id: str, colony_id: str, queen_bee_id: str | None = None
    ) -> InstructionResult:
        """セッションにColonyを追加"""
        session = self._session_manager.get_session(session_id)
        if not session:
            return InstructionResult(success=False, message="Session not found")

        session.add_colony(colony_id, queen_bee_id)
        self._messenger.register_colony(colony_id)

        return InstructionResult(
            success=True,
            message=f"Colony {colony_id} added to session",
            data={"colony_id": colony_id},
        )

    def remove_colony_from_session(self, session_id: str, colony_id: str) -> InstructionResult:
        """セッションからColonyを削除"""
        session = self._session_manager.get_session(session_id)
        if not session:
            return InstructionResult(success=False, message="Session not found")

        session.remove_colony(colony_id)

        return InstructionResult(
            success=True,
            message=f"Colony {colony_id} removed from session",
            data={"colony_id": colony_id},
        )

    def get_instruction_history(self, session_id: str | None = None) -> list[UserInstruction]:
        """指示履歴を取得"""
        if session_id:
            return [i for i in self._instruction_history if i.session_id == session_id]
        return self._instruction_history.copy()

    def get_active_sessions(self) -> list[BeekeeperSession]:
        """アクティブセッション一覧"""
        return self._session_manager.get_active_sessions()
