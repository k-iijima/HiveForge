"""Waggle Dance ARイベント記録

バリデーション結果をAkashic Record (AR) のイベントとして記録する。
検証成功はWAGGLE_DANCE_VALIDATED、失敗はWAGGLE_DANCE_VIOLATIONとして記録。
"""

from __future__ import annotations

from colonyforge.core.events import (
    WaggleDanceValidatedEvent,
    WaggleDanceViolationEvent,
)

from .models import WaggleDanceResult


class WaggleDanceRecorder:
    """Waggle Dance バリデーション結果のAR記録"""

    def create_event(
        self,
        result: WaggleDanceResult,
        colony_id: str,
    ) -> WaggleDanceValidatedEvent | WaggleDanceViolationEvent:
        """バリデーション結果からARイベントを生成する

        Args:
            result: バリデーション結果
            colony_id: 対象ColonyのID

        Returns:
            生成されたARイベント（成功: WaggleDanceValidatedEvent, 違反: WaggleDanceViolationEvent）
        """
        errors_payload = [{"field": err.field, "message": err.message} for err in result.errors]

        payload = {
            "valid": result.valid,
            "direction": result.direction.value,
            "errors": errors_payload,
            "colony_id": colony_id,
        }

        if result.valid:
            return WaggleDanceValidatedEvent(
                colony_id=colony_id,
                actor="waggle_dance",
                payload=payload,
            )
        else:
            return WaggleDanceViolationEvent(
                colony_id=colony_id,
                actor="waggle_dance",
                payload=payload,
            )
