"""Waggle Dance ARイベント記録

バリデーション結果をAkashic Record (AR) のイベントとして記録する。
検証成功はWAGGLE_DANCE_VALIDATED、失敗はWAGGLE_DANCE_VIOLATIONとして記録。
"""

from __future__ import annotations

from hiveforge.core.events import BaseEvent, EventType

from .models import WaggleDanceResult


class WaggleDanceRecorder:
    """Waggle Dance バリデーション結果のAR記録"""

    def create_event(
        self,
        result: WaggleDanceResult,
        colony_id: str,
    ) -> BaseEvent:
        """バリデーション結果からARイベントを生成する

        Args:
            result: バリデーション結果
            colony_id: 対象ColonyのID

        Returns:
            BaseEvent: 生成されたARイベント
        """
        event_type = (
            EventType.WAGGLE_DANCE_VALIDATED if result.valid else EventType.WAGGLE_DANCE_VIOLATION
        )

        errors_payload = [{"field": err.field, "message": err.message} for err in result.errors]

        return BaseEvent(
            type=event_type,
            colony_id=colony_id,
            actor="waggle_dance",
            payload={
                "valid": result.valid,
                "direction": result.direction.value,
                "errors": errors_payload,
                "colony_id": colony_id,
            },
        )
