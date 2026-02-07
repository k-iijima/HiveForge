"""Swarming Protocol Engine — テンプレート選択ロジック

タスクの特徴量からColonyテンプレートを選択する。
ルールベースの選択ロジック。
"""

from __future__ import annotations

import logging
from typing import Any

from .models import SwarmingFeatures, TemplateName
from .templates import COLONY_TEMPLATES, ColonyTemplate

logger = logging.getLogger(__name__)


class SwarmingEngine:
    """Swarming Protocol エンジン

    入力特徴量（SwarmingFeatures）から最適なColonyテンプレートを選択。
    ルールベースの選択ロジックで、将来的にHoneycombデータ駆動に移行可能。
    """

    def __init__(
        self,
        templates: dict[TemplateName, ColonyTemplate] | None = None,
    ) -> None:
        """初期化

        Args:
            templates: カスタマイズ済テンプレート辞書。
                       Noneの場合はデフォルトのCOLONY_TEMPLATESを使用。
        """
        self._templates = templates or COLONY_TEMPLATES

    def select_template(self, features: SwarmingFeatures) -> ColonyTemplate:
        """特徴量からテンプレートを選択

        選択ルール:
        1. Recovery: 障害復旧フラグが設定されている場合
           → メソッド呼び出し時に is_recovery=True で指定
        2. Speed: complexity<=2 AND risk<=2 AND urgency>=4
        3. Quality: complexity>=4 OR risk>=4
        4. Balanced: その他

        Args:
            features: タスクの入力特徴量

        Returns:
            選択されたColonyテンプレート
        """
        template_name = self._evaluate_rules(features)
        template = self._templates[template_name]

        logger.info(
            f"テンプレート選択: {template_name.value} "
            f"(C={features.complexity}, R={features.risk}, U={features.urgency})"
        )
        return template

    def select_template_for_recovery(self) -> ColonyTemplate:
        """障害復旧用テンプレートを選択"""
        return self._templates[TemplateName.RECOVERY]

    def evaluate(self, features: SwarmingFeatures) -> dict[str, Any]:
        """特徴量からテンプレート選択の評価結果を返す

        テンプレート選択の理由を含む詳細情報を返す。
        Beekeeperがユーザーに提案する際に使用。
        """
        template_name = self._evaluate_rules(features)
        template = self._templates[template_name]
        reason = self._explain_selection(features, template_name)

        return {
            "template": template_name.value,
            "features": features.to_dict(),
            "reason": reason,
            "config": {
                "min_workers": template.min_workers,
                "max_workers": template.max_workers,
                "guard_bee": template.guard_bee_enabled,
                "reviewer": template.reviewer_enabled,
                "sentinel": template.sentinel_integration,
                "retry_limit": template.retry_limit,
            },
        }

    def _evaluate_rules(self, features: SwarmingFeatures) -> TemplateName:
        """ルールベースのテンプレート選択"""
        c, r, u = features.complexity, features.risk, features.urgency

        # Speed: 低C + 低R + 高U
        if c <= 2 and r <= 2 and u >= 4:
            return TemplateName.SPEED

        # Quality: 高C or 高R
        if c >= 4 or r >= 4:
            return TemplateName.QUALITY

        # Balanced: その他
        return TemplateName.BALANCED

    def _explain_selection(self, features: SwarmingFeatures, selected: TemplateName) -> str:
        """テンプレート選択理由の説明文を生成"""
        c, r, u = features.complexity, features.risk, features.urgency

        if selected == TemplateName.SPEED:
            return (
                f"低複雑性(C={c}) + 低リスク(R={r}) + 高緊急度(U={u}) → "
                f"最小構成のSpeedテンプレートを推奨"
            )
        elif selected == TemplateName.QUALITY:
            reasons = []
            if c >= 4:
                reasons.append(f"高複雑性(C={c})")
            if r >= 4:
                reasons.append(f"高リスク(R={r})")
            return f"{' + '.join(reasons)} → 厳格な品質ゲート付きQualityテンプレートを推奨"
        elif selected == TemplateName.RECOVERY:
            return "障害復旧タスク → Recoveryテンプレートを推奨"
        else:
            return f"中程度の特徴量(C={c}, R={r}, U={u}) → 標準的なBalancedテンプレートを推奨"
