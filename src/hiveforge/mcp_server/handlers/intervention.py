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
from .base import BaseHandler

if TYPE_CHECKING:
    pass


# インメモリストア（Phase 1用簡易実装）
_interventions: dict[str, dict[str, Any]] = {}
_escalations: dict[str, dict[str, Any]] = {}
_feedbacks: dict[str, dict[str, Any]] = {}


class InterventionHandlers(BaseHandler):
    """Direct Intervention関連のMCPハンドラー"""

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

        data = {
            "event_id": event.id,
            "type": "user_intervention",
            "colony_id": colony_id,
            "instruction": instruction,
            "reason": reason,
            "share_with_beekeeper": share_with_beekeeper,
            "timestamp": event.timestamp.isoformat(),
        }
        _interventions[event.id] = data

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

        data = {
            "event_id": event.id,
            "type": "queen_escalation",
            "colony_id": colony_id,
            "escalation_type": esc_type.value,
            "summary": summary,
            "details": details,
            "suggested_actions": suggested_actions,
            "beekeeper_context": beekeeper_context,
            "status": "pending",
            "timestamp": event.timestamp.isoformat(),
        }
        _escalations[event.id] = data

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
        target = _escalations.get(escalation_id) or _interventions.get(escalation_id)
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

        data = {
            "event_id": event.id,
            "type": "beekeeper_feedback",
            "escalation_id": escalation_id,
            "resolution": resolution,
            "beekeeper_adjustment": beekeeper_adjustment,
            "lesson_learned": lesson_learned,
            "timestamp": event.timestamp.isoformat(),
        }
        _feedbacks[event.id] = data

        # エスカレーションのステータス更新
        if escalation_id in _escalations:
            _escalations[escalation_id]["status"] = "resolved"

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
        escalations = list(_escalations.values())

        colony_id = args.get("colony_id")
        status = args.get("status")

        if colony_id:
            escalations = [e for e in escalations if e.get("colony_id") == colony_id]
        if status:
            escalations = [e for e in escalations if e.get("status") == status]

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

        escalation = _escalations.get(escalation_id)
        if not escalation:
            return {"error": f"Escalation not found: {escalation_id}"}

        return escalation
