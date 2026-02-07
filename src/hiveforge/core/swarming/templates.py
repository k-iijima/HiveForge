"""Colony テンプレート定義

4つのColonyテンプレート:
- Speed: 低Complexity + 低Risk + 高Urgency → 最小構成で高速実行
- Balanced: 中程度の全指標 → 標準的な品質保証付き
- Quality: 高Complexity or 高Risk → 厳格な品質ゲート
- Recovery: 障害復旧、過去の失敗タスク → 問題解決特化
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import TemplateName


class ColonyTemplate(BaseModel):
    """Colonyテンプレート設定"""

    model_config = ConfigDict(frozen=True)

    name: TemplateName = Field(..., description="テンプレート名")
    description: str = Field(..., description="テンプレートの説明")
    min_workers: int = Field(default=1, ge=1, description="最小Worker数")
    max_workers: int = Field(default=1, ge=1, description="最大Worker数")
    guard_bee_enabled: bool = Field(default=False, description="Guard Beeを使用するか")
    reviewer_enabled: bool = Field(default=False, description="レビュアーを使用するか")
    sentinel_integration: bool = Field(default=False, description="Sentinel Hornet強化連携")
    retry_limit: int = Field(default=3, ge=1, description="リトライ上限")


# 4テンプレート定義
SPEED_TEMPLATE = ColonyTemplate(
    name=TemplateName.SPEED,
    description="最小構成で高速実行。低複雑性・低リスク・高緊急度のタスク向け。",
    min_workers=1,
    max_workers=1,
    guard_bee_enabled=False,
    reviewer_enabled=False,
    sentinel_integration=False,
    retry_limit=1,
)

BALANCED_TEMPLATE = ColonyTemplate(
    name=TemplateName.BALANCED,
    description="標準的な品質保証付き。中程度の全指標向け。",
    min_workers=2,
    max_workers=3,
    guard_bee_enabled=True,
    reviewer_enabled=False,
    sentinel_integration=False,
    retry_limit=3,
)

QUALITY_TEMPLATE = ColonyTemplate(
    name=TemplateName.QUALITY,
    description="厳格な品質ゲート。高複雑性または高リスクのタスク向け。",
    min_workers=3,
    max_workers=5,
    guard_bee_enabled=True,
    reviewer_enabled=True,
    sentinel_integration=True,
    retry_limit=5,
)

RECOVERY_TEMPLATE = ColonyTemplate(
    name=TemplateName.RECOVERY,
    description="問題解決特化。障害復旧、過去の失敗タスク向け。",
    min_workers=1,
    max_workers=2,
    guard_bee_enabled=True,
    reviewer_enabled=False,
    sentinel_integration=True,
    retry_limit=5,
)

# テンプレート辞書
COLONY_TEMPLATES: dict[TemplateName, ColonyTemplate] = {
    TemplateName.SPEED: SPEED_TEMPLATE,
    TemplateName.BALANCED: BALANCED_TEMPLATE,
    TemplateName.QUALITY: QUALITY_TEMPLATE,
    TemplateName.RECOVERY: RECOVERY_TEMPLATE,
}


def apply_config_overrides(
    config: dict[str, Any],
) -> dict[TemplateName, ColonyTemplate]:
    """設定ファイルのテンプレートカスタマイズを適用

    hiveforge.config.yaml の swarming.templates セクションから
    テンプレートパラメータを上書きした新しい辞書を返す。

    Args:
        config: swarming.templates セクションの辞書
            例: {"speed": {"max_workers": 2}, "balanced": {"retry_limit": 5}}

    Returns:
        カスタマイズ済みのテンプレート辞書
    """
    result = dict(COLONY_TEMPLATES)

    # テンプレート名 → TemplateName マッピング
    name_map = {t.value: t for t in TemplateName}

    for template_key, overrides in config.items():
        template_name = name_map.get(template_key)
        if template_name is None or template_name not in result:
            continue

        base = result[template_name]
        # 設定キー → Pydanticフィールド名 マッピング
        field_map = {
            "min_workers": "min_workers",
            "max_workers": "max_workers",
            "guard_bee": "guard_bee_enabled",
            "reviewer": "reviewer_enabled",
            "sentinel": "sentinel_integration",
            "retry_limit": "retry_limit",
        }

        update_kwargs: dict[str, Any] = {}
        for config_key, field_name in field_map.items():
            if config_key in overrides:
                update_kwargs[field_name] = overrides[config_key]

        if update_kwargs:
            # frozenモデルなので新インスタンスを生成
            data = base.model_dump()
            data.update(update_kwargs)
            result[template_name] = ColonyTemplate(**data)

    return result
