"""Colony テンプレート定義

4つのColonyテンプレート:
- Speed: 低Complexity + 低Risk + 高Urgency → 最小構成で高速実行
- Balanced: 中程度の全指標 → 標準的な品質保証付き
- Quality: 高Complexity or 高Risk → 厳格な品質ゲート
- Recovery: 障害復旧、過去の失敗タスク → 問題解決特化
"""

from __future__ import annotations

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
