"""Requirement Analysis Colony — 要求分析パッケージ.

doorstop + pytest-bdd による要求テキスト永続化・トレーサビリティを提供する。
"""

from colonyforge.requirement_analysis.assumption_mapper import AssumptionMapper
from colonyforge.requirement_analysis.change_tracker import ChangeTracker
from colonyforge.requirement_analysis.clarify_generator import ClarifyGenerator
from colonyforge.requirement_analysis.context_forager import ContextForager
from colonyforge.requirement_analysis.gate import RAGuardGate
from colonyforge.requirement_analysis.impact_analyzer import ImpactAnalyzer
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
    ChangeReason,
    ClarificationQuestion,
    ClarificationRound,
    CodeRef,
    Constraint,
    ConstraintCategory,
    DecisionRef,
    EpisodeRef,
    EvidencePack,
    FailureHypothesis,
    FailureRef,
    Freshness,
    GateCheck,
    ImpactReport,
    IntentGraph,
    QuestionType,
    RAGateResult,
    RefereeResult,
    RequiredAction,
    RequirementChangedPayload,
    RunRef,
    SpecDraft,
    SpecPersistResult,
    SpecScore,
    SuccessCriterion,
    WebEvidencePack,
    WebFinding,
    WebSourceType,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator
from colonyforge.requirement_analysis.referee_comparer import RefereeComparer
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
    "ChangeReason",
    "ChangeTracker",
    "ClarificationQuestion",
    "ClarificationRound",
    "ClarifyGenerator",
    "CodeRef",
    "Constraint",
    "ConstraintCategory",
    "ContextForager",
    "DecisionRef",
    "EpisodeRef",
    "EvidencePack",
    "FailureHypothesis",
    "FailureRef",
    "Freshness",
    "GateCheck",
    "ImpactAnalyzer",
    "ImpactReport",
    "IntentGraph",
    "IntentMiner",
    "QuestionType",
    "RAGateResult",
    "RAGuardGate",
    "RAOrchestrator",
    "RefereeComparer",
    "RefereeResult",
    "RequiredAction",
    "RequirementChangedPayload",
    "RiskChallenger",
    "RunRef",
    "SpecDraft",
    "SpecPersistResult",
    "SpecPersister",
    "SpecScore",
    "SpecSynthesizer",
    "SuccessCriterion",
    "WebEvidencePack",
    "WebFinding",
    "WebSourceType",
]
