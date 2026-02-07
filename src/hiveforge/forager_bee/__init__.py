"""Forager Bee — 探索的テスト・影響分析エージェント

変更の影響範囲を広く探索し、潜在的な不整合や違和感を
証拠として収集してGuard Beeに渡す。

4フェーズ:
1. 変更影響グラフ構築 (GraphBuilder)
2. 含意シナリオ生成 (ScenarioGenerator)
3. 探索実行 (ForagerExplorer)
4. 違和感検知 (AnomalyDetector)
"""

from .anomaly_detector import AnomalyDetector
from .explorer import ForagerExplorer
from .graph_builder import GraphBuilder
from .models import (
    AnomalyType,
    ChangeImpactGraph,
    DependencyEdge,
    DependencyType,
    ForagerReport,
    ForagerVerdict,
    ImpactNode,
    Scenario,
    ScenarioCategory,
    ScenarioResult,
)
from .reporter import ForagerReporter
from .scenario_generator import ScenarioGenerator

__all__ = [
    "AnomalyDetector",
    "AnomalyType",
    "ChangeImpactGraph",
    "DependencyEdge",
    "DependencyType",
    "ForagerExplorer",
    "ForagerReport",
    "ForagerReporter",
    "ForagerVerdict",
    "GraphBuilder",
    "ImpactNode",
    "Scenario",
    "ScenarioCategory",
    "ScenarioGenerator",
    "ScenarioResult",
]
