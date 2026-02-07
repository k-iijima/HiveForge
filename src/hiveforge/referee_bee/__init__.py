"""Referee Bee — 審判蜂 / 自動採点・生存選抜エージェント

N案候補を多面的に自動採点し、上位候補のみをGuard Beeに渡す。

コンポーネント:
- ScoringEngine: 5次元スコア計算
- DiffTester: Differential Testing
- Tournament: トーナメント選抜
- RefereeReporter: Guard Bee連携
"""

from .diff_tester import DiffTester
from .models import (
    CandidateScore,
    DiffResult,
    RefereeReport,
    RefereeVerdict,
    ScoreWeights,
    ScoringDimension,
    SelectionResult,
)
from .reporter import RefereeReporter
from .scoring import ScoringEngine
from .tournament import Tournament

__all__ = [
    "CandidateScore",
    "DiffResult",
    "DiffTester",
    "RefereeReport",
    "RefereeReporter",
    "RefereeVerdict",
    "ScoreWeights",
    "ScoringDimension",
    "ScoringEngine",
    "SelectionResult",
    "Tournament",
]
