"""Waggle Dance バリデーションミドルウェア

エージェント間の通信メッセージをPydanticスキーマで検証する。
ステートレスなミドルウェアとして機能し、不正なメッセージを検出する。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from .models import (
    MessageDirection,
    OpinionRequest,
    OpinionResponse,
    TaskAssignment,
    TaskResult,
    WaggleDanceResult,
)
from .models import (
    ValidationError as WDValidationError,
)

# メッセージ方向 → 対応するスキーマのマッピング
_DIRECTION_SCHEMA_MAP: dict[MessageDirection, type] = {
    MessageDirection.BEEKEEPER_TO_QUEEN: OpinionRequest,
    MessageDirection.QUEEN_TO_BEEKEEPER: OpinionResponse,
    MessageDirection.QUEEN_TO_WORKER: TaskAssignment,
    MessageDirection.WORKER_TO_QUEEN: TaskResult,
}


class WaggleDanceValidator:
    """Waggle Dance バリデータ

    エージェント間通信の各メッセージを、方向に応じた
    Pydanticスキーマで検証するステートレスミドルウェア。
    """

    def validate(
        self,
        direction: MessageDirection,
        data: dict[str, Any],
    ) -> WaggleDanceResult:
        """メッセージを検証する

        Args:
            direction: メッセージの方向
            data: 検証対象のメッセージデータ

        Returns:
            WaggleDanceResult: 検証結果
        """
        schema = _DIRECTION_SCHEMA_MAP.get(direction)
        if schema is None:
            return WaggleDanceResult(
                valid=False,
                errors=[
                    WDValidationError(
                        field="direction",
                        message=f"未対応のメッセージ方向: {direction}",
                    )
                ],
                direction=direction,
            )

        try:
            schema(**data)
            return WaggleDanceResult(
                valid=True,
                errors=[],
                direction=direction,
            )
        except PydanticValidationError as e:
            errors = [
                WDValidationError(
                    field=".".join(str(loc) for loc in err["loc"]),
                    message=err["msg"],
                )
                for err in e.errors()
            ]
            return WaggleDanceResult(
                valid=False,
                errors=errors,
                direction=direction,
            )
