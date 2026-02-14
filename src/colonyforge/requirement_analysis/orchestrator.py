"""RAOrchestrator — 要求分析プロセスの状態遷移エンジン（§4）.

RAStateMachine を駆動し、各ステップのコンポーネント（AmbiguityScorer,
IntentMiner, AssumptionMapper, RiskChallenger, ClarifyGenerator 等）を
協調させて要求分析ライフサイクルを管理する。

W2: コアの状態遷移管理・イベント発行・高速パス判定を実装。
W3: AssumptionMapper, RiskChallenger, ClarifyGenerator を統合。
W4: SpecSynthesizer, RAGuardGate (Req版) を統合。
W5: ContextForager, WEB_RESEARCH/WEB_SKIPPED, RefereeComparer を統合。
"""

from __future__ import annotations

from typing import Any

from colonyforge.core.ar.projections import RAState
from colonyforge.core.events.base import BaseEvent, generate_event_id
from colonyforge.core.events.ra import (
    RAChallengeReviewedEvent,
    RAClarifyGeneratedEvent,
    RACompletedEvent,
    RAContextEnrichedEvent,
    RAGateDecidedEvent,
    RAHypothesisBuiltEvent,
    RAIntakeReceivedEvent,
    RARefereeComparedEvent,
    RASpecSynthesizedEvent,
    RATriageCompletedEvent,
    RAUserRespondedEvent,
    RAWebResearchedEvent,
    RAWebSkippedEvent,
)
from colonyforge.core.events.types import EventType
from colonyforge.core.state.machines import RAStateMachine
from colonyforge.requirement_analysis.context_forager import ContextForager
from colonyforge.requirement_analysis.models import (
    AmbiguityScores,
    AnalysisPath,
    Assumption,
    ClarificationRound,
    EvidencePack,
    FailureHypothesis,
    IntentGraph,
    RAGateResult,
    RefereeResult,
    SpecDraft,
    WebEvidencePack,
)
from colonyforge.requirement_analysis.referee_comparer import RefereeComparer
from colonyforge.requirement_analysis.scorer import AmbiguityScorer

# ---------------------------------------------------------------------------
# 終端状態
# ---------------------------------------------------------------------------

_TERMINAL_STATES: frozenset[RAState] = frozenset(
    {RAState.EXECUTION_READY, RAState.EXECUTION_READY_WITH_RISKS, RAState.ABANDONED}
)

_COMPLETE_STATES: frozenset[RAState] = frozenset(
    {RAState.EXECUTION_READY, RAState.EXECUTION_READY_WITH_RISKS}
)

# ---------------------------------------------------------------------------
# EventType → Event Class マッピング（ステップ実行用）
# ---------------------------------------------------------------------------

_EVENT_CLASS_MAP: dict[EventType, type[BaseEvent]] = {
    EventType.RA_INTAKE_RECEIVED: RAIntakeReceivedEvent,
    EventType.RA_TRIAGE_COMPLETED: RATriageCompletedEvent,
    EventType.RA_CONTEXT_ENRICHED: RAContextEnrichedEvent,
    EventType.RA_HYPOTHESIS_BUILT: RAHypothesisBuiltEvent,
    EventType.RA_CLARIFY_GENERATED: RAClarifyGeneratedEvent,
    EventType.RA_USER_RESPONDED: RAUserRespondedEvent,
    EventType.RA_SPEC_SYNTHESIZED: RASpecSynthesizedEvent,
    EventType.RA_CHALLENGE_REVIEWED: RAChallengeReviewedEvent,
    EventType.RA_GATE_DECIDED: RAGateDecidedEvent,
    EventType.RA_COMPLETED: RACompletedEvent,
    EventType.RA_WEB_RESEARCHED: RAWebResearchedEvent,
    EventType.RA_WEB_SKIPPED: RAWebSkippedEvent,
    EventType.RA_REFEREE_COMPARED: RARefereeComparedEvent,
}


class RAOrchestrator:
    """要求分析プロセスの状態遷移エンジン.

    RAStateMachine を内部で駆動し、各状態に応じたコンポーネントを起動する。
    イベントを発行・蓄積し、状態遷移の完全な履歴を保持する。

    Usage:
        orch = RAOrchestrator(scorer=scorer, intent_miner=miner)
        await orch.intake("ログイン機能を作って")
        while not orch.is_terminal:
            await orch.step()
    """

    def __init__(
        self,
        *,
        scorer: AmbiguityScorer | None = None,
        intent_miner: Any | None = None,
        assumption_mapper: Any | None = None,
        risk_challenger: Any | None = None,
        clarify_generator: Any | None = None,
        spec_synthesizer: Any | None = None,
        guard_gate: Any | None = None,
        context_forager: ContextForager | None = None,
        referee_comparer: RefereeComparer | None = None,
        request_id: str | None = None,
    ) -> None:
        self._state_machine = RAStateMachine()
        self._scorer: AmbiguityScorer = scorer or AmbiguityScorer()
        self._intent_miner = intent_miner
        self._assumption_mapper = assumption_mapper
        self._risk_challenger = risk_challenger
        self._clarify_generator = clarify_generator
        self._spec_synthesizer = spec_synthesizer
        self._guard_gate = guard_gate
        self._context_forager = context_forager
        self._referee_comparer = referee_comparer
        self.request_id: str = request_id or generate_event_id()
        self.raw_input: str = ""
        self.ambiguity_scores: AmbiguityScores | None = None
        self.analysis_path: AnalysisPath | None = None
        self.intent_graph: IntentGraph | None = None
        self.assumptions: list[Assumption] = []
        self.failure_hypotheses: list[FailureHypothesis] = []
        self.clarification_rounds: list[ClarificationRound] = []
        self.spec_drafts: list[SpecDraft] = []
        self.gate_result: RAGateResult | None = None
        self.evidence_pack: EvidencePack | None = None
        self.web_evidence_pack: WebEvidencePack | None = None
        self.referee_result: RefereeResult | None = None
        self.events: list[BaseEvent] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> RAState:
        """現在の状態."""
        return self._state_machine.current_state  # type: ignore[return-value]

    @property
    def is_terminal(self) -> bool:
        """終端状態かどうか."""
        return self.current_state in _TERMINAL_STATES

    @property
    def is_complete(self) -> bool:
        """正常完了かどうか（ABANDONED は含まない）."""
        return self.current_state in _COMPLETE_STATES

    # ------------------------------------------------------------------
    # intake() — 受領 + トリアージ
    # ------------------------------------------------------------------

    async def intake(self, text: str) -> None:
        """生テキストを受領してトリアージを実行する.

        INTAKE → TRIAGE に遷移し、AmbiguityScores と AnalysisPath を算出する。

        Args:
            text: ユーザーの生テキスト
        """
        self.raw_input = text

        # AmbiguityScores + AnalysisPath を算出
        self.ambiguity_scores, self.analysis_path = self._scorer.score_and_determine(text)

        # INTAKE_RECEIVED イベント発行
        self._emit_event(
            RAIntakeReceivedEvent,
            payload={
                "raw_input": text,
                "ambiguity_scores": self.ambiguity_scores.model_dump(),
                "analysis_path": self.analysis_path.value,
            },
        )

        # INTAKE → TRIAGE 遷移
        triage_event = self._emit_event(
            RATriageCompletedEvent,
            payload={
                "analysis_path": self.analysis_path.value,
            },
        )
        self._state_machine.transition(triage_event)

    # ------------------------------------------------------------------
    # step() — 次のステップを実行
    # ------------------------------------------------------------------

    async def step(self) -> None:
        """現在の状態に基づいて次のステップを実行する.

        終端状態の場合は何もしない。各状態に応じたコンポーネントを起動し、
        適切なイベントを発行して状態遷移を行う。

        W2 ではスタブ実装（各ステップは最小限のイベント発行のみ）。
        W3-W4 で Assumption Mapper, Risk Challenger 等のロールを追加。
        """
        if self.is_terminal:
            return

        state = self.current_state

        if state == RAState.TRIAGE:
            await self._step_context_enrich()
        elif state == RAState.CONTEXT_ENRICH:
            await self._step_web_decision()
        elif state == RAState.WEB_RESEARCH:
            await self._step_after_web()
        elif state == RAState.HYPOTHESIS_BUILD:
            await self._step_clarify_gen()
        elif state == RAState.CLARIFY_GEN:
            await self._step_spec_synthesis()
        elif state == RAState.SPEC_SYNTHESIS:
            await self._step_challenge_review()
        elif state == RAState.CHALLENGE_REVIEW:
            await self._step_challenge_review_or_referee()
        elif state == RAState.REFEREE_COMPARE:
            await self._step_after_referee()
        elif state == RAState.GUARD_GATE:
            await self._step_complete()
        # W3-W4 で追加: USER_FEEDBACK, SPEC_PERSIST, USER_EDIT

    # ------------------------------------------------------------------
    # get_status() — ステータスサマリ
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """現在の分析状態のサマリ情報を返す."""
        status: dict[str, Any] = {
            "request_id": self.request_id,
            "state": self.current_state,
            "is_terminal": self.is_terminal,
            "is_complete": self.is_complete,
            "event_count": len(self.events),
        }
        if self.raw_input:
            status["raw_input"] = self.raw_input
        if self.analysis_path is not None:
            status["analysis_path"] = self.analysis_path
        if self.ambiguity_scores is not None:
            status["ambiguity_scores"] = self.ambiguity_scores.model_dump()
        if self.assumptions:
            status["assumptions_count"] = len(self.assumptions)
        if self.failure_hypotheses:
            status["failure_hypotheses_count"] = len(self.failure_hypotheses)
        if self.clarification_rounds:
            status["clarification_rounds_count"] = len(self.clarification_rounds)
        if self.spec_drafts:
            status["spec_drafts_count"] = len(self.spec_drafts)
        if self.gate_result is not None:
            status["gate_passed"] = self.gate_result.passed
        if self.evidence_pack is not None:
            status["evidence_count"] = (
                len(self.evidence_pack.related_decisions)
                + len(self.evidence_pack.past_runs)
                + len(self.evidence_pack.failure_history)
                + len(self.evidence_pack.code_context)
                + len(self.evidence_pack.similar_episodes)
            )
        if self.web_evidence_pack is not None:
            status["web_search_performed"] = not self.web_evidence_pack.skipped
        if self.referee_result is not None:
            status["referee_selected_draft"] = self.referee_result.selected_draft_id
        return status

    # ------------------------------------------------------------------
    # private — ステップ実装（W2 スタブ）
    # ------------------------------------------------------------------

    async def _step_context_enrich(self) -> None:
        """TRIAGE → CONTEXT_ENRICH: コンテキスト収集.

        ContextForager 注入時は AR イベントから証拠を収集する。
        未注入時はスタブ動作（空の EvidencePack）。
        """
        if self._context_forager is not None:
            self.evidence_pack = self._context_forager.forage(
                self.raw_input,
                intent_graph=self.intent_graph,
            )
        else:
            self.evidence_pack = EvidencePack()

        evidence_count = (
            len(self.evidence_pack.related_decisions)
            + len(self.evidence_pack.past_runs)
            + len(self.evidence_pack.failure_history)
            + len(self.evidence_pack.code_context)
            + len(self.evidence_pack.similar_episodes)
        )

        event = self._emit_event(
            RAContextEnrichedEvent,
            payload={
                "source": "context_forager" if self._context_forager else "stub",
                "evidence_count": evidence_count,
            },
        )
        self._state_machine.transition(event)

    async def _step_web_decision(self) -> None:
        """CONTEXT_ENRICH → WEB_RESEARCH or HYPOTHESIS_BUILD: WEB検索判定.

        ContextForager の should_search_web() で判定し、
        必要なら WEB_RESEARCH へ遷移（次 step で仮説構築）、
        不要なら RA_WEB_SKIPPED を記録後、直接仮説構築を実行して
        HYPOTHESIS_BUILD へ遷移する。
        """
        forager = self._context_forager or ContextForager()
        needed, reason = forager.should_search_web(
            self.raw_input,
            intent_graph=self.intent_graph,
        )

        if needed:
            # WEB検索を実施（スタブ: 空のWebEvidencePack）
            self.web_evidence_pack = WebEvidencePack(
                trigger_reason=reason,
                skipped=False,
            )
            event = self._emit_event(
                RAWebResearchedEvent,
                payload={
                    "trigger_reason": reason,
                    "findings_count": 0,
                },
            )
            self._state_machine.transition(event)
        else:
            # WEB検索スキップ（記録のみ、状態遷移なし）
            self._emit_event(
                RAWebSkippedEvent,
                payload={"reason": reason},
            )
            # そのまま仮説構築へ（CONTEXT_ENRICH → HYPOTHESIS_BUILD）
            await self._step_hypothesis_build()

    async def _step_after_web(self) -> None:
        """WEB_RESEARCH → HYPOTHESIS_BUILD: WEB検索後に仮説構築へ."""
        await self._step_hypothesis_build()

    async def _step_hypothesis_build(self) -> None:
        """CONTEXT_ENRICH → HYPOTHESIS_BUILD: 仮説構築.

        AssumptionMapper で推定事項を抽出し、RiskChallenger で失敗仮説を生成する。
        コンポーネント未注入時はスタブ動作（空リスト）。
        """
        # AssumptionMapper: IntentGraph → Assumption リスト
        if self._assumption_mapper is not None:
            self.assumptions = await self._assumption_mapper.extract(
                self.intent_graph or IntentGraph(goals=[self.raw_input]),
            )
        else:
            self.assumptions = []

        # RiskChallenger: IntentGraph + Assumptions → FailureHypothesis リスト
        if self._risk_challenger is not None:
            self.failure_hypotheses = await self._risk_challenger.challenge(
                self.intent_graph or IntentGraph(goals=[self.raw_input]),
                assumptions=self.assumptions,
            )
        else:
            self.failure_hypotheses = []

        event = self._emit_event(
            RAHypothesisBuiltEvent,
            payload={
                "assumptions_count": len(self.assumptions),
                "failure_hypotheses_count": len(self.failure_hypotheses),
            },
        )
        self._state_machine.transition(event)

    async def _step_clarify_gen(self) -> None:
        """HYPOTHESIS_BUILD → CLARIFY_GEN: 質問生成.

        ClarifyGenerator で質問を生成する。質問が存在する場合は
        skip_to_spec=False としてユーザーフィードバックを要求する。
        コンポーネント未注入時はスタブ動作（skip_to_spec=True）。
        """
        questions_count = 0
        skip_to_spec = True

        if self._clarify_generator is not None:
            round_ = await self._clarify_generator.generate(
                self.intent_graph or IntentGraph(goals=[self.raw_input]),
                assumptions=self.assumptions,
                failure_hypotheses=self.failure_hypotheses,
                round_number=len(self.clarification_rounds) + 1,
            )
            if round_.questions:
                self.clarification_rounds.append(round_)
                questions_count = len(round_.questions)
                skip_to_spec = False

        event = self._emit_event(
            RAClarifyGeneratedEvent,
            payload={
                "questions_count": questions_count,
                "skip_to_spec": skip_to_spec,
            },
        )
        self._state_machine.transition(event)

    async def _step_spec_synthesis(self) -> None:
        """CLARIFY_GEN → SPEC_SYNTHESIS: 仕様草案統合.

        SpecSynthesizer 注入時は LLM で SpecDraft を生成する。
        未注入時はスタブ動作（空 spec_drafts）。
        """
        draft_count = 0
        version = len(self.spec_drafts) + 1

        if self._spec_synthesizer is not None:
            spec = await self._spec_synthesizer.synthesize(
                self.intent_graph or IntentGraph(goals=[self.raw_input]),
                assumptions=self.assumptions,
                failure_hypotheses=self.failure_hypotheses,
                version=version,
            )
            self.spec_drafts.append(spec)
            draft_count = len(self.spec_drafts)

        event = self._emit_event(
            RASpecSynthesizedEvent,
            payload={"draft_count": draft_count, "version": version},
        )
        self._state_machine.transition(event)

    async def _step_challenge_review(self) -> None:
        """SPEC_SYNTHESIS → CHALLENGE_REVIEW: Challenge Review."""
        event = self._emit_event(
            RAChallengeReviewedEvent,
            payload={"verdict": "pass_with_risks", "challenges_count": 0},
        )
        self._state_machine.transition(event)

    async def _step_challenge_review_or_referee(self) -> None:
        """CHALLENGE_REVIEW → REFEREE_COMPARE or GUARD_GATE.

        複数 spec_drafts があり referee_comparer が注入されていれば
        REFEREE_COMPARE へ、そうでなければ GUARD_GATE へ遷移する。
        """
        if self._referee_comparer is not None and len(self.spec_drafts) >= 2:  # noqa: PLR2004
            # Referee 比較を実施
            draft_ids = [d.draft_id for d in self.spec_drafts]
            self.referee_result = self._referee_comparer.compare(
                self.spec_drafts,
                draft_ids=draft_ids,
            )
            event = self._emit_event(
                RARefereeComparedEvent,
                payload={
                    "selected_draft_id": self.referee_result.selected_draft_id,
                    "drafts_compared": len(self.spec_drafts),
                },
            )
            self._state_machine.transition(event)
        else:
            await self._step_guard_gate()

    async def _step_after_referee(self) -> None:
        """REFEREE_COMPARE → GUARD_GATE: Referee 比較後にゲート判定へ."""
        await self._step_guard_gate()

    async def _step_guard_gate(self) -> None:
        """CHALLENGE_REVIEW → GUARD_GATE: ゲート判定.

        RAGuardGate 注入時は SpecDraft に対してルールベースチェックを実行する。
        未注入時はスタブ動作（passed=True）。
        """
        passed = True
        checks_count = 0

        if self._guard_gate is not None and self.spec_drafts:
            latest_spec = self.spec_drafts[-1]
            self.gate_result = self._guard_gate.evaluate(
                spec=latest_spec,
                ambiguity_scores=self.ambiguity_scores,
                failure_hypotheses=self.failure_hypotheses,
            )
            passed = self.gate_result.passed
            checks_count = len(self.gate_result.checks)

        event = self._emit_event(
            RAGateDecidedEvent,
            payload={"passed": passed, "checks_count": checks_count},
        )
        self._state_machine.transition(event)

    async def _step_complete(self) -> None:
        """GUARD_GATE → 終端状態: RA完了.

        gate_result の結果に基づいて終端状態を決定する。
        passed=True → EXECUTION_READY, passed=False → ABANDONED.
        """
        if self.gate_result is not None and not self.gate_result.passed:
            outcome = "ABANDONED"
        else:
            outcome = "EXECUTION_READY"

        event = self._emit_event(
            RACompletedEvent,
            payload={"outcome": outcome},
        )
        self._state_machine.transition(event)

    # ------------------------------------------------------------------
    # private — イベント発行ヘルパー
    # ------------------------------------------------------------------

    def _emit_event(
        self,
        event_class: type[BaseEvent],
        *,
        payload: dict[str, Any] | None = None,
    ) -> BaseEvent:
        """イベントを生成して履歴に追加する.

        Args:
            event_class: 発行するイベントクラス
            payload: イベントペイロード

        Returns:
            生成されたイベント
        """
        event_payload = {"request_id": self.request_id}
        if payload:
            event_payload.update(payload)

        prev_hash = self.events[-1].hash if self.events else None

        event = event_class(  # type: ignore[call-arg]  # subclass provides type default
            payload=event_payload,
            prev_hash=prev_hash,
        )
        self.events.append(event)
        return event
