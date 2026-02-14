"""Requirement Analysis Colony — 要求分析パッケージ.

doorstop + pytest-bdd による要求テキスト永続化・トレーサビリティを提供する。
"""

from colonyforge.requirement_analysis.assumption_mapper import AssumptionMapper
from colonyforge.requirement_analysis.clarify_generator import ClarifyGenerator
from colonyforge.requirement_analysis.gate import RAGuardGate
from colonyforge.requirement_analysis.intent_miner import IntentMiner
from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    AmbiguityScores,
    AnalysisPath,
    Assumption,
    AssumptionStatus,
    Challenge,
    ChallengeReport,
    ChallengeVerdict,
    ClarificationQuestion,
    ClarificationRound,
    Constraint,
    ConstraintCategory,
    FailureHypothesis,
    GateCheck,
    IntentGraph,
    QuestionType,
    RAGateResult,
    RequiredAction,
    SpecDraft,
    SpecPersistResult,
    SuccessCriterion,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator
from colonyforge.requirement_analysis.risk_challenger import RiskChallenger
from colonyforge.requirement_analysis.scorer import AmbiguityScorer
from colonyforge.requirement_analysis.spec_persister import SpecPersister
from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

__all__ = [
    "AcceptanceCriterion",
    "AmbiguityScorer",
    "AmbiguityScores",
    "AnalysisPath",
    "Assumption",
    "AssumptionMapper",
    "AssumptionStatus",
    "Challenge",
    "ChallengeReport",
    "ChallengeVerdict",
    "ClarificationQuestion",
    "ClarificationRound",
    "ClarifyGenerator",
    "Constraint",
    "ConstraintCategory",
    "FailureHypothesis",
    "GateCheck",
    "IntentGraph",
    "IntentMiner",
    "QuestionType",
    "RAGateResult",
    "RAGuardGate",
    "RAOrchestrator",
    "RequiredAction",
    "RiskChallenger",
    "SpecDraft",
    "SpecPersistResult",
    "SpecPersister",
    "SpecSynthesizer",
    "SuccessCriterion",
]
