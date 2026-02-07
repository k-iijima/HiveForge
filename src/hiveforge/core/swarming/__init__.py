"""Swarming Protocol — 適応的Colony編成

タスクの特性に応じて最適なColony編成を決定する。
入力特徴量（Complexity, Risk, Urgency）から
4つのColonyテンプレートを選択する。
"""

from .models import SwarmingFeatures, TemplateName
from .templates import ColonyTemplate, COLONY_TEMPLATES
from .engine import SwarmingEngine

__all__ = [
    "ColonyTemplate",
    "COLONY_TEMPLATES",
    "SwarmingEngine",
    "SwarmingFeatures",
    "TemplateName",
]
