"""
Direct Intervention MCP ハンドラー

ユーザー直接介入、Queen直訴、Beekeeperフィードバックの
MCPツールハンドラー。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.events import (
    BeekeeperFeedbackEvent,
    EscalationType,
    QueenEscalationEvent,
    UserDirectInterventionEvent,
)
from ...core.intervention import (
    EscalationRecord,
    FeedbackRecord,
    InterventionRecord,
    InterventionStore,
)
from .base import BaseHandler

if TYPE_CHECKING:
    pass


class InterventionHandlers(BaseHandler):
    """Direct Intervention関連のMCPハンドラー"""

    def __init__(self, server: Any, store: InterventionStore | None = None) -> None:
        super().__init__(server)
        self._store = store

    def _get_store(self) -> InterventionStore:
        """InterventionStoreを取得（遅延初期化）"""
        if self._store is None:
            ar = self._get_ar()
            self._store = InterventionStore(base_path=ar.vault_path)
        return self._store

    async def handle_user_intervene(self, args: dict[str, Any]) -> dict[str, Any]:
        """ユーザー直接介入を作成

        Args:
            args:
                colony_id: 対象Colony ID（必須）
                instruction: 直接指示（必須）
                reason: 介入理由（オプション）
                share_with_beekeeper: Beekeeperに共有するか（デフォルトTrue）

        Returns:
            介入情報
        """
        colony_id = args.get("colony_id")
        instruction = args.get("instruction")

        if not colony_id:
            return {"error": "colony_id is required"}
        if not instruction:
            return {"error": "instruction is required"}

        reason = args.get("reason", "")
        share_with_beekeeper = args.get("share_with_beekeeper", True)

        event = UserDirectInterventionEvent(
            actor="mcp",
            payload={
                "colony_id": colony_id,
                "instruction": instruction,
                "reason": reason,
                "bypass_beekeeper": True,
                "share_with_beekeeper": share_with_beekeeper,
            },
        )

        # ARに永続化（因果リンク構築のため）
        ar = self._get_ar()
        stream_key = f"intervention-{colony_id}"
        ar.append(event, stream_key)

        record = InterventionRecord(
            event_id=event.id,
            colony_id=colony_id,
            instruction=instruction,
            reason=reason,
            share_with_beekeeper=share_with_beekeeper,
            timestamp=event.timestamp.isoformat(),
        )
        self._get_store().add_intervention(record)

        return {
            "event_id": event.id,
            "colony_id": colony_id,
            "message": f"Direct intervention sent to colony {colony_id}",
        }

    async def handle_queen_escalate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Queen直訴を作成

        Args:
            args:
                colony_id: Queen BeeのColony ID（必須）
                escalation_type: エスカレーション種別（必須）
                summary: 問題の要約（必須）
                details: 詳細説明（オプション）
                suggested_actions: 提案アクション（オプション）
                beekeeper_context: Beekeeperとの経緯（オプション）

        Returns:
            エスカレーション情報
        """
        colony_id = args.get("colony_id")
        escalation_type = args.get("escalation_type")
        summary = args.get("summary")

        if not colony_id:
            return {"error": "colony_id is required"}
        if not escalation_type:
            return {"error": "escalation_type is required"}
        if not summary:
            return {"error": "summary is required"}

        # エスカレーションタイプを検証
        try:
            esc_type = EscalationType(escalation_type)
        except ValueError:
            valid_types = [t.value for t in EscalationType]
            return {
                "error": f"Invalid escalation_type: {escalation_type}. Valid types: {valid_types}"
            }

        details = args.get("details", "")
        suggested_actions = args.get("suggested_actions", [])
        beekeeper_context = args.get("beekeeper_context", "")

        event = QueenEscalationEvent(
            actor=f"queen-{colony_id}",
            payload={
                "colony_id": colony_id,
                "escalation_type": esc_type.value,
                "summary": summary,
                "details": details,
                "suggested_actions": suggested_actions,
                "beekeeper_context": beekeeper_context,
            },
        )

        # ARに永続化（因果リンク構築のため）
        ar = self._get_ar()
        stream_key = f"intervention-{colony_id}"
        ar.append(event, stream_key)

        record = EscalationRecord(
            event_id=event.id,
            colony_id=colony_id,
            escalation_type=esc_type.value,
            summary=summary,
            details=details,
            suggested_actions=suggested_actions,
            beekeeper_context=beekeeper_context,
            timestamp=event.timestamp.isoformat(),
        )
        self._get_store().add_escalation(record)

        return {
            "event_id": event.id,
            "colony_id": colony_id,
            "escalation_type": esc_type.value,
            "summary": summary,
            "status": "pending",
            "message": "Escalation created and awaiting user response",
        }

    async def handle_beekeeper_feedback(self, args: dict[str, Any]) -> dict[str, Any]:
        """Beekeeperフィードバックを作成

        Args:
            args:
                escalation_id: 対応したエスカレーション/介入のID（必須）
                resolution: 解決方法（必須）
                beekeeper_adjustment: Beekeeperへの調整（オプション）
                lesson_learned: 学んだ教訓（オプション）

        Returns:
            フィードバック情報
        """
        escalation_id = args.get("escalation_id")
        resolution = args.get("resolution")

        if not escalation_id:
            return {"error": "escalation_id is required"}
        if not resolution:
            return {"error": "resolution is required"}

        # 対象の確認
        store = self._get_store()
        target = store.get_target(escalation_id)
        if not target:
            return {"error": f"Escalation or intervention not found: {escalation_id}"}

        beekeeper_adjustment = args.get("beekeeper_adjustment", {})
        lesson_learned = args.get("lesson_learned", "")

        event = BeekeeperFeedbackEvent(
            actor="mcp",
            payload={
                "escalation_id": escalation_id,
                "resolution": resolution,
                "beekeeper_adjustment": beekeeper_adjustment,
                "lesson_learned": lesson_learned,
            },
        )

        # ARに永続化（因果リンク構築のため）
        # フィードバック対象のcolony_idを取得
        feedback_colony_id = getattr(target, "colony_id", "unknown")
        ar = self._get_ar()
        stream_key = f"intervention-{feedback_colony_id}"
        ar.append(event, stream_key)

        record = FeedbackRecord(
            event_id=event.id,
            escalation_id=escalation_id,
            resolution=resolution,
            beekeeper_adjustment=beekeeper_adjustment,
            lesson_learned=lesson_learned,
            timestamp=event.timestamp.isoformat(),
        )
        store.add_feedback(record)

        # エスカレーションのステータス更新
        store.resolve_escalation(escalation_id)

        return {
            "event_id": event.id,
            "escalation_id": escalation_id,
            "message": "Feedback recorded and escalation resolved",
        }

    async def handle_list_escalations(self, args: dict[str, Any]) -> dict[str, Any]:
        """エスカレーション一覧を取得

        Args:
            args:
                colony_id: Colony IDでフィルタ（オプション）
                status: ステータスでフィルタ（オプション: pending, resolved）

        Returns:
            エスカレーション一覧
        """
        colony_id = args.get("colony_id")
        status = args.get("status")

        escalations = self._get_store().list_escalations(colony_id=colony_id, status=status)

        return {
            "escalations": escalations,
            "count": len(escalations),
        }

    async def handle_get_escalation(self, args: dict[str, Any]) -> dict[str, Any]:
        """エスカレーション詳細を取得

        Args:
            args:
                escalation_id: エスカレーションID（必須）

        Returns:
            エスカレーション詳細
        """
        escalation_id = args.get("escalation_id")
        if not escalation_id:
            return {"error": "escalation_id is required"}

        escalation = self._get_store().get_escalation(escalation_id)
        if not escalation:
            return {"error": f"Escalation not found: {escalation_id}"}

        return escalation.model_dump(mode="json")
