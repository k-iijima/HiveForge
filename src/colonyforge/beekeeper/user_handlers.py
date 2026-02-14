"""Beekeeper ユーザー操作ハンドラMixin"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..core import generate_event_id
from ..core.events import (
    EmergencyStopEvent,
    RequirementApprovedEvent,
    RequirementCreatedEvent,
    RequirementRejectedEvent,
)

if TYPE_CHECKING:
    from ..core import AkashicRecord
    from ..queen_bee.server import QueenBeeMCPServer
    from .session import BeekeeperSession, BeekeeperSessionManager

logger = logging.getLogger(__name__)


class UserHandlersMixin:
    """ユーザー操作系ハンドラ: メッセージ・承認・拒否・緊急停止・確認"""

    if TYPE_CHECKING:
        current_session: BeekeeperSession | None
        session_manager: BeekeeperSessionManager
        ar: AkashicRecord
        _pending_requests: dict[str, asyncio.Future[str]]
        _queens: dict[str, QueenBeeMCPServer]

        async def run_with_llm(
            self, message: str, context: dict[str, Any] | None = None
        ) -> dict[str, Any]: ...

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
        except TimeoutError:
            result = f"タイムアウト: {question} (timeout={timeout}s)"
            logger.warning(f"ユーザー応答タイムアウト: request_id={request_id}")
        finally:
            # pending_requests をクリーンアップ
            self._pending_requests.pop(str(request_id), None)

            # セッション状態を ACTIVE に復元
            if self.current_session:
                self.current_session.set_active()

        return result
