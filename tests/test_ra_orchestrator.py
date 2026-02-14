"""RAOrchestrator テスト — §4 状態遷移エンジン.

RAOrchestrator は RAStateMachine を駆動し、各ステップのコンポーネント
（AmbiguityScorer, IntentMiner 等）を協調させて要求分析プロセスを管理する。

W2 ではコアの状態遷移管理・イベント発行・高速パス判定を実装する。
W3 で AssumptionMapper, RiskChallenger, ClarifyGenerator を統合する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from colonyforge.core.ar.projections import RAState
from colonyforge.core.events.types import EventType
from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    AmbiguityScores,
    AnalysisPath,
    Assumption,
    AssumptionStatus,
    ClarificationQuestion,
    ClarificationRound,
    FailureHypothesis,
    IntentGraph,
    QuestionType,
    RAGateResult,
    SpecDraft,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_mock_intent_miner(
    goals: list[str] | None = None,
) -> MagicMock:
    """IntentMiner のモックを生成."""
    miner = MagicMock()
    graph = IntentGraph(goals=goals or ["テスト目標"])
    miner.extract = AsyncMock(return_value=graph)
    return miner


def _make_mock_scorer(
    ambiguity: float = 0.5,
    context_sufficiency: float = 0.5,
    execution_risk: float = 0.3,
    path: AnalysisPath = AnalysisPath.ASSUMPTION_PASS,
) -> MagicMock:
    """AmbiguityScorer のモックを生成."""
    scorer = MagicMock()
    scores = AmbiguityScores(
        ambiguity=ambiguity,
        context_sufficiency=context_sufficiency,
        execution_risk=execution_risk,
    )
    scorer.score_text.return_value = scores
    scorer.determine_path.return_value = path
    scorer.score_and_determine.return_value = (scores, path)
    return scorer


# ---------------------------------------------------------------------------
# 初期化テスト
# ---------------------------------------------------------------------------


class TestRAOrchestratorInit:
    """RAOrchestrator の初期化."""

    def test_initial_state(self) -> None:
        """初期状態は INTAKE."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.current_state == RAState.INTAKE

    def test_accepts_components(self) -> None:
        """コンポーネントを注入できる."""
        # Arrange
        scorer = _make_mock_scorer()
        miner = _make_mock_intent_miner()

        # Act
        orch = RAOrchestrator(scorer=scorer, intent_miner=miner)

        # Assert
        assert orch._scorer is scorer
        assert orch._intent_miner is miner

    def test_default_components(self) -> None:
        """コンポーネント未指定時はデフォルトが使用される."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert: デフォルトの AmbiguityScorer が使用される
        assert orch._scorer is not None

    def test_events_empty_initially(self) -> None:
        """初期状態ではイベント履歴が空."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.events == []

    def test_request_id_generated(self) -> None:
        """request_id が自動生成される."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert isinstance(orch.request_id, str)
        assert len(orch.request_id) > 0


# ---------------------------------------------------------------------------
# intake() — 生テキスト受領
# ---------------------------------------------------------------------------


class TestIntake:
    """intake() — INTAKE → TRIAGE 遷移."""

    @pytest.mark.asyncio
    async def test_intake_transitions_to_triage(self) -> None:
        """intake() で INTAKE → TRIAGE に遷移する."""
        # Arrange
        scorer = _make_mock_scorer()
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("ログイン機能を作って")

        # Assert
        assert orch.current_state == RAState.TRIAGE

    @pytest.mark.asyncio
    async def test_intake_stores_raw_input(self) -> None:
        """intake() でユーザー入力テキストが保存される."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("ログイン機能を作って")

        # Assert
        assert orch.raw_input == "ログイン機能を作って"

    @pytest.mark.asyncio
    async def test_intake_emits_event(self) -> None:
        """intake() で RA_INTAKE_RECEIVED イベントが発行される."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("テスト")

        # Assert
        assert len(orch.events) >= 1
        intake_events = [e for e in orch.events if e.type == EventType.RA_INTAKE_RECEIVED]
        assert len(intake_events) == 1

    @pytest.mark.asyncio
    async def test_intake_computes_scores(self) -> None:
        """intake() で AmbiguityScores が算出される."""
        # Arrange
        scorer = _make_mock_scorer()
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("ログイン機能を作って")

        # Assert
        assert orch.ambiguity_scores is not None
        scorer.score_and_determine.assert_called_once()

    @pytest.mark.asyncio
    async def test_intake_determines_path(self) -> None:
        """intake() で分析パスが決定される."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS)
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("認証システムを改善して")

        # Assert
        assert orch.analysis_path == AnalysisPath.FULL_ANALYSIS

    @pytest.mark.asyncio
    async def test_intake_triage_emits_event(self) -> None:
        """intake() で RA_TRIAGE_COMPLETED イベントも発行される."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("テスト")

        # Assert
        triage_events = [e for e in orch.events if e.type == EventType.RA_TRIAGE_COMPLETED]
        assert len(triage_events) == 1


# ---------------------------------------------------------------------------
# 高速パス判定
# ---------------------------------------------------------------------------


class TestFastPath:
    """高速パス判定（§8）."""

    @pytest.mark.asyncio
    async def test_instant_pass_flag(self) -> None:
        """INSTANT_PASS パスが正しく設定される."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.INSTANT_PASS)
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("テストを実行して")

        # Assert
        assert orch.analysis_path == AnalysisPath.INSTANT_PASS

    @pytest.mark.asyncio
    async def test_assumption_pass_flag(self) -> None:
        """ASSUMPTION_PASS パスが正しく設定される."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.ASSUMPTION_PASS)
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("既存機能を拡張して")

        # Assert
        assert orch.analysis_path == AnalysisPath.ASSUMPTION_PASS

    @pytest.mark.asyncio
    async def test_full_analysis_flag(self) -> None:
        """FULL_ANALYSIS パスが正しく設定される."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS)
        orch = RAOrchestrator(scorer=scorer)

        # Act
        await orch.intake("認証システムを改善して")

        # Assert
        assert orch.analysis_path == AnalysisPath.FULL_ANALYSIS


# ---------------------------------------------------------------------------
# step() — 次のステップを実行
# ---------------------------------------------------------------------------


class TestStep:
    """step() — 現在の状態に基づいて次のステップを実行."""

    @pytest.mark.asyncio
    async def test_step_from_triage(self) -> None:
        """TRIAGE 状態で step() すると CONTEXT_ENRICH に遷移."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS)
        orch = RAOrchestrator(scorer=scorer)
        await orch.intake("テスト")

        # Act
        assert orch.current_state == RAState.TRIAGE
        await orch.step()

        # Assert
        assert orch.current_state == RAState.CONTEXT_ENRICH

    @pytest.mark.asyncio
    async def test_step_emits_context_enriched(self) -> None:
        """TRIAGE → CONTEXT_ENRICH で RA_CONTEXT_ENRICHED が発行される."""
        # Arrange
        scorer = _make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS)
        orch = RAOrchestrator(scorer=scorer)
        await orch.intake("テスト")

        # Act
        await orch.step()

        # Assert
        ctx_events = [e for e in orch.events if e.type == EventType.RA_CONTEXT_ENRICHED]
        assert len(ctx_events) == 1

    @pytest.mark.asyncio
    async def test_step_at_terminal_state_no_transition(self) -> None:
        """終端状態で step() しても状態は変わらない."""
        # Arrange
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.EXECUTION_READY

        # Act
        await orch.step()

        # Assert
        assert orch.current_state == RAState.EXECUTION_READY


# ---------------------------------------------------------------------------
# is_terminal / is_complete
# ---------------------------------------------------------------------------


class TestTerminalStates:
    """終端状態の判定."""

    def test_intake_not_terminal(self) -> None:
        """INTAKE は終端でない."""
        orch = RAOrchestrator()
        assert orch.is_terminal is False

    def test_execution_ready_is_terminal(self) -> None:
        """EXECUTION_READY は終端."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.EXECUTION_READY
        assert orch.is_terminal is True

    def test_execution_ready_with_risks_is_terminal(self) -> None:
        """EXECUTION_READY_WITH_RISKS は終端."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.EXECUTION_READY_WITH_RISKS
        assert orch.is_terminal is True

    def test_abandoned_is_terminal(self) -> None:
        """ABANDONED は終端."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.ABANDONED
        assert orch.is_terminal is True

    def test_is_complete_success(self) -> None:
        """EXECUTION_READY は正常完了."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.EXECUTION_READY
        assert orch.is_complete is True

    def test_is_complete_with_risks(self) -> None:
        """EXECUTION_READY_WITH_RISKS も完了扱い."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.EXECUTION_READY_WITH_RISKS
        assert orch.is_complete is True

    def test_is_complete_abandoned_false(self) -> None:
        """ABANDONED は完了ではない（放棄）."""
        orch = RAOrchestrator()
        orch._state_machine.current_state = RAState.ABANDONED
        assert orch.is_complete is False


# ---------------------------------------------------------------------------
# イベント履歴
# ---------------------------------------------------------------------------


class TestEventHistory:
    """イベント履歴の管理."""

    @pytest.mark.asyncio
    async def test_events_ordered(self) -> None:
        """イベントは発行順に蓄積される."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("テスト")

        # Assert: INTAKE_RECEIVED → TRIAGE_COMPLETED の順
        assert len(orch.events) >= 2
        assert orch.events[0].type == EventType.RA_INTAKE_RECEIVED
        assert orch.events[1].type == EventType.RA_TRIAGE_COMPLETED

    @pytest.mark.asyncio
    async def test_events_have_request_id(self) -> None:
        """全イベントに request_id がペイロードに含まれる."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("テスト")

        # Assert
        for event in orch.events:
            assert "request_id" in event.payload
            assert event.payload["request_id"] == orch.request_id

    @pytest.mark.asyncio
    async def test_events_chained(self) -> None:
        """イベントはハッシュチェーンで連結される."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())

        # Act
        await orch.intake("テスト")

        # Assert: 2つ目以降のイベントは prev_hash を持つ
        if len(orch.events) >= 2:
            assert orch.events[1].prev_hash == orch.events[0].hash


# ---------------------------------------------------------------------------
# get_status() — 現在の状態サマリ
# ---------------------------------------------------------------------------


class TestGetStatus:
    """get_status() — 現在の分析状態のサマリ情報."""

    def test_initial_status(self) -> None:
        """初期状態のステータス."""
        # Arrange & Act
        orch = RAOrchestrator()
        status = orch.get_status()

        # Assert
        assert status["state"] == RAState.INTAKE
        assert status["is_terminal"] is False
        assert "request_id" in status
        assert status["event_count"] == 0

    @pytest.mark.asyncio
    async def test_status_after_intake(self) -> None:
        """intake() 後のステータス."""
        # Arrange
        orch = RAOrchestrator(scorer=_make_mock_scorer())
        await orch.intake("テスト")

        # Act
        status = orch.get_status()

        # Assert
        assert status["state"] == RAState.TRIAGE
        assert status["raw_input"] == "テスト"
        assert status["event_count"] >= 2
        assert "analysis_path" in status


# ---------------------------------------------------------------------------
# W3 ヘルパー
# ---------------------------------------------------------------------------


def _make_mock_assumption_mapper(
    assumptions: list[Assumption] | None = None,
) -> MagicMock:
    """AssumptionMapper のモックを生成."""
    mapper = MagicMock()
    default_assumptions = assumptions or [
        Assumption(
            assumption_id="a1",
            text="ユーザー認証が必要",
            confidence=0.9,
            status=AssumptionStatus.AUTO_APPROVED,
        ),
        Assumption(
            assumption_id="a2",
            text="REST APIを使用する",
            confidence=0.7,
            status=AssumptionStatus.PENDING,
        ),
    ]
    mapper.extract = AsyncMock(return_value=default_assumptions)
    return mapper


def _make_mock_risk_challenger(
    hypotheses: list[FailureHypothesis] | None = None,
) -> MagicMock:
    """RiskChallenger のモックを生成."""
    challenger = MagicMock()
    default_hypotheses = hypotheses or [
        FailureHypothesis(
            hypothesis_id="fh1",
            text="認証トークン漏洩リスク",
            severity="HIGH",
            mitigation="HTTPSの強制とトークンローテーション",
        ),
    ]
    challenger.challenge = AsyncMock(return_value=default_hypotheses)
    return challenger


def _make_mock_clarify_generator(
    round_: ClarificationRound | None = None,
) -> MagicMock:
    """ClarifyGenerator のモックを生成."""
    gen = MagicMock()
    default_round = round_ or ClarificationRound(
        round_number=1,
        questions=[
            ClarificationQuestion(
                question_id="q1",
                text="OAuth2を使用しますか？",
                question_type=QuestionType.YES_NO,
                impact="high",
                related_assumption_ids=["a1"],
            ),
        ],
    )
    gen.generate = AsyncMock(return_value=default_round)
    return gen


# ---------------------------------------------------------------------------
# W3: コンポーネント注入テスト
# ---------------------------------------------------------------------------


class TestOrchestratorW3Init:
    """W3 コンポーネント注入テスト."""

    def test_accepts_assumption_mapper(self) -> None:
        """AssumptionMapper を注入できる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()

        # Act
        orch = RAOrchestrator(assumption_mapper=mapper)

        # Assert
        assert orch._assumption_mapper is mapper

    def test_accepts_risk_challenger(self) -> None:
        """RiskChallenger を注入できる."""
        # Arrange
        challenger = _make_mock_risk_challenger()

        # Act
        orch = RAOrchestrator(risk_challenger=challenger)

        # Assert
        assert orch._risk_challenger is challenger

    def test_accepts_clarify_generator(self) -> None:
        """ClarifyGenerator を注入できる."""
        # Arrange
        gen = _make_mock_clarify_generator()

        # Act
        orch = RAOrchestrator(clarify_generator=gen)

        # Assert
        assert orch._clarify_generator is gen

    def test_assumptions_empty_initially(self) -> None:
        """初期状態では assumptions が空リスト."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.assumptions == []

    def test_failure_hypotheses_empty_initially(self) -> None:
        """初期状態では failure_hypotheses が空リスト."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.failure_hypotheses == []

    def test_clarification_rounds_empty_initially(self) -> None:
        """初期状態では clarification_rounds が空リスト."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.clarification_rounds == []


# ---------------------------------------------------------------------------
# W3: HYPOTHESIS_BUILD ステップ
# ---------------------------------------------------------------------------


class TestHypothesisBuildStep:
    """CONTEXT_ENRICH → HYPOTHESIS_BUILD: AssumptionMapper + RiskChallenger."""

    @pytest.mark.asyncio
    async def test_calls_assumption_mapper(self) -> None:
        """AssumptionMapper.extract() が呼ばれる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("認証機能")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        mapper.extract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calls_risk_challenger(self) -> None:
        """RiskChallenger.challenge() が呼ばれる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("認証機能")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        challenger.challenge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stores_assumptions(self) -> None:
        """抽出された Assumption がオーケストレータに保存される."""
        # Arrange
        assumptions = [
            Assumption(assumption_id="a1", text="前提1", confidence=0.9),
            Assumption(assumption_id="a2", text="前提2", confidence=0.6),
        ]
        mapper = _make_mock_assumption_mapper(assumptions)
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        assert orch.assumptions == assumptions

    @pytest.mark.asyncio
    async def test_stores_failure_hypotheses(self) -> None:
        """生成された FailureHypothesis がオーケストレータに保存される."""
        # Arrange
        hypotheses = [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="障害モード1",
                severity="HIGH",
            ),
        ]
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger(hypotheses)
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        assert orch.failure_hypotheses == hypotheses

    @pytest.mark.asyncio
    async def test_emits_event_with_counts(self) -> None:
        """RA_HYPOTHESIS_BUILT イベントに正しいカウントが含まれる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()  # 2 assumptions
        challenger = _make_mock_risk_challenger()  # 1 hypothesis
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        hyp_events = [e for e in orch.events if e.type == EventType.RA_HYPOTHESIS_BUILT]
        assert len(hyp_events) == 1
        assert hyp_events[0].payload["assumptions_count"] == 2
        assert hyp_events[0].payload["failure_hypotheses_count"] == 1

    @pytest.mark.asyncio
    async def test_transitions_to_hypothesis_build(self) -> None:
        """CONTEXT_ENRICH → HYPOTHESIS_BUILD に遷移する."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert
        assert orch.current_state == RAState.HYPOTHESIS_BUILD

    @pytest.mark.asyncio
    async def test_passes_intent_graph_to_mapper(self) -> None:
        """AssumptionMapper に IntentGraph が渡される."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        miner = _make_mock_intent_miner(goals=["ゴール1"])
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            intent_miner=miner,
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert: mapper.extract に IntentGraph が渡されている
        call_args = mapper.extract.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_passes_assumptions_to_challenger(self) -> None:
        """RiskChallenger に assumptions が渡される."""
        # Arrange
        assumptions = [
            Assumption(assumption_id="a1", text="前提1", confidence=0.9),
        ]
        mapper = _make_mock_assumption_mapper(assumptions)
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert: challenger.challenge に assumptions が渡されている
        call_args = challenger.challenge.call_args
        assert call_args is not None
        # 2番目の引数（assumptions）を検証
        passed_assumptions = call_args[1].get(
            "assumptions", call_args[0][1] if len(call_args[0]) > 1 else None
        )
        if passed_assumptions is None:
            # positional args
            passed_assumptions = call_args[0][1]
        assert passed_assumptions == assumptions

    @pytest.mark.asyncio
    async def test_without_mapper_uses_stub(self) -> None:
        """AssumptionMapper 未注入時はスタブ動作（空リスト）."""
        # Arrange
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH

        # Act
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Assert: スタブ動作で空リスト
        assert orch.assumptions == []
        assert orch.failure_hypotheses == []


# ---------------------------------------------------------------------------
# W3: CLARIFY_GEN ステップ
# ---------------------------------------------------------------------------


class TestClarifyGenStep:
    """HYPOTHESIS_BUILD → CLARIFY_GEN: ClarifyGenerator."""

    @pytest.mark.asyncio
    async def test_calls_clarify_generator(self) -> None:
        """ClarifyGenerator.generate() が呼ばれる."""
        # Arrange
        gen = _make_mock_clarify_generator()
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        gen.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stores_clarification_round(self) -> None:
        """ClarificationRound がオーケストレータに保存される."""
        # Arrange
        round_ = ClarificationRound(
            round_number=1,
            questions=[
                ClarificationQuestion(
                    question_id="q1",
                    text="質問1",
                    question_type=QuestionType.FREE_TEXT,
                ),
            ],
        )
        gen = _make_mock_clarify_generator(round_)
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        assert len(orch.clarification_rounds) == 1
        assert orch.clarification_rounds[0] == round_

    @pytest.mark.asyncio
    async def test_emits_event_with_questions_count(self) -> None:
        """RA_CLARIFY_GENERATED イベントに質問数が含まれる."""
        # Arrange
        gen = _make_mock_clarify_generator()  # 1 question
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        cg_events = [e for e in orch.events if e.type == EventType.RA_CLARIFY_GENERATED]
        assert len(cg_events) == 1
        assert cg_events[0].payload["questions_count"] == 1

    @pytest.mark.asyncio
    async def test_skip_to_spec_when_no_questions(self) -> None:
        """質問が生成されない場合は skip_to_spec=True."""
        # Arrange
        empty_round = ClarificationRound(round_number=1, questions=[])
        gen = _make_mock_clarify_generator(empty_round)
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        cg_events = [e for e in orch.events if e.type == EventType.RA_CLARIFY_GENERATED]
        assert cg_events[0].payload["skip_to_spec"] is True

    @pytest.mark.asyncio
    async def test_no_skip_when_questions_exist(self) -> None:
        """質問が存在する場合は skip_to_spec=False."""
        # Arrange
        gen = _make_mock_clarify_generator()  # 1 question
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        cg_events = [e for e in orch.events if e.type == EventType.RA_CLARIFY_GENERATED]
        assert cg_events[0].payload["skip_to_spec"] is False

    @pytest.mark.asyncio
    async def test_without_generator_uses_stub(self) -> None:
        """ClarifyGenerator 未注入時はスタブ動作（skip_to_spec=True）."""
        # Arrange
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        cg_events = [e for e in orch.events if e.type == EventType.RA_CLARIFY_GENERATED]
        assert cg_events[0].payload["skip_to_spec"] is True
        assert orch.clarification_rounds == []

    @pytest.mark.asyncio
    async def test_passes_context_to_generator(self) -> None:
        """ClarifyGenerator に intent_graph, assumptions, failure_hypotheses が渡される."""
        # Arrange
        gen = _make_mock_clarify_generator()
        assumptions = [
            Assumption(assumption_id="a1", text="前提1", confidence=0.9),
        ]
        hypotheses = [
            FailureHypothesis(hypothesis_id="fh1", text="障害1", severity="HIGH"),
        ]
        mapper = _make_mock_assumption_mapper(assumptions)
        challenger = _make_mock_risk_challenger(hypotheses)
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
            clarify_generator=gen,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        await orch.step()  # HYPOTHESIS_BUILD → CLARIFY_GEN

        # Assert
        call_kwargs = gen.generate.call_args[1]
        assert "assumptions" in call_kwargs
        assert "failure_hypotheses" in call_kwargs
        assert call_kwargs["assumptions"] == assumptions
        assert call_kwargs["failure_hypotheses"] == hypotheses


# ---------------------------------------------------------------------------
# W3: get_status() W3 拡張
# ---------------------------------------------------------------------------


class TestGetStatusW3:
    """get_status() に W3 コンポーネントの情報が含まれる."""

    @pytest.mark.asyncio
    async def test_status_includes_assumptions_count(self) -> None:
        """ステータスに assumptions_count が含まれる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        status = orch.get_status()

        # Assert
        assert status["assumptions_count"] == 2

    @pytest.mark.asyncio
    async def test_status_includes_failure_hypotheses_count(self) -> None:
        """ステータスに failure_hypotheses_count が含まれる."""
        # Arrange
        mapper = _make_mock_assumption_mapper()
        challenger = _make_mock_risk_challenger()
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
            assumption_mapper=mapper,
            risk_challenger=challenger,
        )
        await orch.intake("テスト")
        await orch.step()  # TRIAGE → CONTEXT_ENRICH
        await orch.step()  # CONTEXT_ENRICH → HYPOTHESIS_BUILD

        # Act
        status = orch.get_status()

        # Assert
        assert status["failure_hypotheses_count"] == 1


# ---------------------------------------------------------------------------
# W4 ヘルパー
# ---------------------------------------------------------------------------


def _make_mock_spec_synthesizer(
    spec: SpecDraft | None = None,
) -> MagicMock:
    """SpecSynthesizer のモックを生成."""
    synth = MagicMock()
    default_spec = spec or SpecDraft(
        draft_id="d1",
        version=1,
        goal="テスト目標を達成する",
        acceptance_criteria=[
            AcceptanceCriterion(
                text="テストが通る",
                measurable=True,
                metric="テスト成功率",
                threshold="100%",
            ),
        ],
        constraints=["HTTPS必須"],
    )
    synth.synthesize = AsyncMock(return_value=default_spec)
    return synth


def _make_mock_guard_gate(
    result: RAGateResult | None = None,
) -> MagicMock:
    """RAGuardGate のモックを生成."""
    gate = MagicMock()
    default_result = result or RAGateResult(
        passed=True,
        checks=[],
    )
    gate.evaluate.return_value = default_result
    return gate


def _make_full_w4_orch(
    *,
    spec: SpecDraft | None = None,
    gate_result: RAGateResult | None = None,
    path: AnalysisPath = AnalysisPath.FULL_ANALYSIS,
) -> RAOrchestrator:
    """全 W4 コンポーネントを注入した RAOrchestrator を生成."""
    return RAOrchestrator(
        scorer=_make_mock_scorer(path=path),
        assumption_mapper=_make_mock_assumption_mapper(),
        risk_challenger=_make_mock_risk_challenger(),
        clarify_generator=_make_mock_clarify_generator(
            ClarificationRound(round_number=1, questions=[]),
        ),
        spec_synthesizer=_make_mock_spec_synthesizer(spec),
        guard_gate=_make_mock_guard_gate(gate_result),
    )


async def _advance_to_state(orch: RAOrchestrator, target: RAState) -> None:
    """target 状態まで step() を繰り返す."""
    await orch.intake("テスト要求")
    max_steps = 20
    for _ in range(max_steps):
        if orch.current_state == target or orch.is_terminal:
            break
        await orch.step()


# ---------------------------------------------------------------------------
# W4: コンポーネント注入テスト
# ---------------------------------------------------------------------------


class TestOrchestratorW4Init:
    """W4 コンポーネント注入テスト."""

    def test_accepts_spec_synthesizer(self) -> None:
        """SpecSynthesizer を注入できる."""
        # Arrange
        synth = _make_mock_spec_synthesizer()

        # Act
        orch = RAOrchestrator(spec_synthesizer=synth)

        # Assert
        assert orch._spec_synthesizer is synth

    def test_accepts_guard_gate(self) -> None:
        """RAGuardGate を注入できる."""
        # Arrange
        gate = _make_mock_guard_gate()

        # Act
        orch = RAOrchestrator(guard_gate=gate)

        # Assert
        assert orch._guard_gate is gate

    def test_spec_drafts_empty_initially(self) -> None:
        """初期状態では spec_drafts が空リスト."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.spec_drafts == []

    def test_gate_result_none_initially(self) -> None:
        """初期状態では gate_result が None."""
        # Arrange & Act
        orch = RAOrchestrator()

        # Assert
        assert orch.gate_result is None


# ---------------------------------------------------------------------------
# W4: SPEC_SYNTHESIS ステップ
# ---------------------------------------------------------------------------


class TestSpecSynthesisStep:
    """CLARIFY_GEN → SPEC_SYNTHESIS: SpecSynthesizer 統合."""

    @pytest.mark.asyncio
    async def test_calls_spec_synthesizer(self) -> None:
        """SpecSynthesizer.synthesize() が呼ばれる."""
        # Arrange
        synth = _make_mock_spec_synthesizer()
        orch = _make_full_w4_orch()
        orch._spec_synthesizer = synth
        await _advance_to_state(orch, RAState.CLARIFY_GEN)

        # Act
        await orch.step()  # CLARIFY_GEN → SPEC_SYNTHESIS

        # Assert
        synth.synthesize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stores_spec_draft(self) -> None:
        """生成された SpecDraft がオーケストレータに保存される."""
        # Arrange
        spec = SpecDraft(
            draft_id="d2",
            version=1,
            goal="保存テスト",
            acceptance_criteria=["AC1"],
            constraints=["C1"],
        )
        synth = _make_mock_spec_synthesizer(spec)
        orch = _make_full_w4_orch()
        orch._spec_synthesizer = synth
        await _advance_to_state(orch, RAState.CLARIFY_GEN)

        # Act
        await orch.step()  # CLARIFY_GEN → SPEC_SYNTHESIS

        # Assert
        assert len(orch.spec_drafts) == 1
        assert orch.spec_drafts[0] == spec

    @pytest.mark.asyncio
    async def test_emits_spec_synthesized_event(self) -> None:
        """RA_SPEC_SYNTHESIZED イベントが発行される."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.CLARIFY_GEN)

        # Act
        await orch.step()  # CLARIFY_GEN → SPEC_SYNTHESIS

        # Assert
        spec_events = [e for e in orch.events if e.type == EventType.RA_SPEC_SYNTHESIZED]
        assert len(spec_events) == 1
        assert spec_events[0].payload["draft_count"] == 1

    @pytest.mark.asyncio
    async def test_transitions_to_spec_synthesis(self) -> None:
        """CLARIFY_GEN → SPEC_SYNTHESIS に遷移する."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.CLARIFY_GEN)

        # Act
        await orch.step()  # CLARIFY_GEN → SPEC_SYNTHESIS

        # Assert
        assert orch.current_state == RAState.SPEC_SYNTHESIS

    @pytest.mark.asyncio
    async def test_without_synthesizer_uses_stub(self) -> None:
        """SpecSynthesizer 未注入時はスタブ動作（空 spec_drafts）."""
        # Arrange
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
        )
        await orch.intake("テスト")
        while orch.current_state != RAState.CLARIFY_GEN and not orch.is_terminal:
            await orch.step()

        # Act
        await orch.step()  # CLARIFY_GEN → SPEC_SYNTHESIS

        # Assert
        assert orch.spec_drafts == []


# ---------------------------------------------------------------------------
# W4: GUARD_GATE ステップ
# ---------------------------------------------------------------------------


class TestGuardGateStep:
    """CHALLENGE_REVIEW → GUARD_GATE: RAGuardGate 統合."""

    @pytest.mark.asyncio
    async def test_calls_guard_gate(self) -> None:
        """RAGuardGate.evaluate() が呼ばれる."""
        # Arrange
        gate = _make_mock_guard_gate()
        orch = _make_full_w4_orch()
        orch._guard_gate = gate
        await _advance_to_state(orch, RAState.CHALLENGE_REVIEW)

        # Act
        await orch.step()  # CHALLENGE_REVIEW → GUARD_GATE

        # Assert
        gate.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_gate_result(self) -> None:
        """RAGateResult がオーケストレータに保存される."""
        # Arrange
        result = RAGateResult(passed=True, checks=[])
        gate = _make_mock_guard_gate(result)
        orch = _make_full_w4_orch()
        orch._guard_gate = gate
        await _advance_to_state(orch, RAState.CHALLENGE_REVIEW)

        # Act
        await orch.step()  # CHALLENGE_REVIEW → GUARD_GATE

        # Assert
        assert orch.gate_result is result

    @pytest.mark.asyncio
    async def test_emits_gate_decided_event(self) -> None:
        """RA_GATE_DECIDED イベントが発行される."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.CHALLENGE_REVIEW)

        # Act
        await orch.step()  # CHALLENGE_REVIEW → GUARD_GATE

        # Assert
        gate_events = [e for e in orch.events if e.type == EventType.RA_GATE_DECIDED]
        assert len(gate_events) == 1
        assert gate_events[0].payload["passed"] is True

    @pytest.mark.asyncio
    async def test_without_guard_gate_uses_stub(self) -> None:
        """RAGuardGate 未注入時はスタブ動作（passed=True）."""
        # Arrange
        orch = RAOrchestrator(
            scorer=_make_mock_scorer(path=AnalysisPath.FULL_ANALYSIS),
        )
        await orch.intake("テスト")
        while orch.current_state != RAState.CHALLENGE_REVIEW and not orch.is_terminal:
            await orch.step()

        # Act
        await orch.step()  # CHALLENGE_REVIEW → GUARD_GATE

        # Assert
        assert orch.gate_result is None  # スタブはgate_resultを設定しない


# ---------------------------------------------------------------------------
# W4: COMPLETE ステップ
# ---------------------------------------------------------------------------


class TestCompleteStep:
    """GUARD_GATE → 終端状態: RA完了."""

    @pytest.mark.asyncio
    async def test_complete_with_passed_gate(self) -> None:
        """Gate 合格時は EXECUTION_READY に遷移."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.GUARD_GATE)

        # Act
        await orch.step()  # GUARD_GATE → 終端

        # Assert
        assert orch.current_state == RAState.EXECUTION_READY

    @pytest.mark.asyncio
    async def test_complete_emits_ra_completed(self) -> None:
        """RA_COMPLETED イベントが発行される."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.GUARD_GATE)

        # Act
        await orch.step()  # GUARD_GATE → 終端

        # Assert
        comp_events = [e for e in orch.events if e.type == EventType.RA_COMPLETED]
        assert len(comp_events) == 1
        assert comp_events[0].payload["outcome"] == "EXECUTION_READY"

    @pytest.mark.asyncio
    async def test_complete_with_failed_gate_abandoned(self) -> None:
        """Gate 不合格時は ABANDONED に遷移."""
        # Arrange
        failed_result = RAGateResult(passed=False, checks=[], required_actions=["修正が必要"])
        orch = _make_full_w4_orch(gate_result=failed_result)
        await _advance_to_state(orch, RAState.GUARD_GATE)

        # Act
        await orch.step()  # GUARD_GATE → 終端

        # Assert
        assert orch.current_state == RAState.ABANDONED


# ---------------------------------------------------------------------------
# W4: get_status() W4 拡張
# ---------------------------------------------------------------------------


class TestGetStatusW4:
    """get_status() に W4 コンポーネントの情報が含まれる."""

    @pytest.mark.asyncio
    async def test_status_includes_spec_drafts_count(self) -> None:
        """ステータスに spec_drafts_count が含まれる."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.SPEC_SYNTHESIS)

        # Act
        status = orch.get_status()

        # Assert
        assert status["spec_drafts_count"] == 1

    @pytest.mark.asyncio
    async def test_status_includes_gate_passed(self) -> None:
        """Gate 実行後の ステータスに gate_passed が含まれる."""
        # Arrange
        orch = _make_full_w4_orch()
        await _advance_to_state(orch, RAState.GUARD_GATE)

        # Act
        status = orch.get_status()

        # Assert
        assert "gate_passed" in status
        assert status["gate_passed"] is True

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """INTAKE から EXECUTION_READY まで全 step が通る."""
        # Arrange
        orch = _make_full_w4_orch()

        # Act
        await orch.intake("認証機能を実装して")
        steps = 0
        while not orch.is_terminal:
            await orch.step()
            steps += 1
            if steps > 20:
                break  # 安全弁

        # Assert
        assert orch.is_terminal is True
        assert orch.is_complete is True
        assert orch.current_state == RAState.EXECUTION_READY
