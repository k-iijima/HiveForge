"""Scout Bee — 偵察蜂 / 編成最適化パッケージ

Honeycombの過去エピソードから類似タスクを検索し、
最適なColonyテンプレートを推薦する。
"""

from .analyzer import TemplateAnalyzer
from .matcher import EpisodeMatcher, SimilarEpisode
from .models import (
    OptimizationProposal,
    ScoutReport,
    ScoutVerdict,
    TemplateStats,
)
from .scout import ScoutBee

__all__ = [
    "EpisodeMatcher",
    "OptimizationProposal",
    "ScoutBee",
    "ScoutReport",
    "ScoutVerdict",
    "SimilarEpisode",
    "TemplateAnalyzer",
    "TemplateStats",
]
