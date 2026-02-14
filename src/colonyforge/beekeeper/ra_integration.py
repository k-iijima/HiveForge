"""Beekeeper 要求分析統合Mixin

Beekeeperと実行Colonyの間にRA Colony（要求分析）を挿入する。
_delegate_to_queen 前に要求分析を実行し、ClarificationQuestions を
_ask_user() 経由でユーザーに提示する。

§2: 「即タスク化を防ぐゲート」
§10: UXパターン（質問提示、高速パス、サマリ表示）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from colonyforge.core.ar.projections import RAState
from colonyforge.requirement_analysis.models import (
    AnalysisPath,
    ClarificationRound,
    RAGateResult,
    SpecDraft,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator
from colonyforge.requirement_analysis.scorer import AmbiguityScorer

if TYPE_CHECKING:
    from colonyforge.core.events.base import BaseEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAAnalysisResult — 分析結果データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RAAnalysisResult:
    """RA Colony 分析結果.

    _analyze_requirements の戻り値。Beekeeper が委譲判断に使用する。
    """

    passed: bool
    """Guard Gate を通過したか"""

    analysis_path: AnalysisPath
    """判定された分析パス（INSTANT_PASS / ASSUMPTION_PASS / FULL_ANALYSIS）"""

    spec_draft: SpecDraft | None = None
    """生成された仕様草案（存在する場合）"""

    gate_result: RAGateResult | None = None
    """Guard Gate の詳細結果"""

    answers: dict[str, str] = field(default_factory=dict)
    """ClarificationQuestion ID → ユーザー回答のマッピング"""

    events: list[BaseEvent] = field(default_factory=list)
    """分析中に発行されたイベント群"""


# ---------------------------------------------------------------------------
# RequirementAnalysisMixin
# ---------------------------------------------------------------------------


class RequirementAnalysisMixin:
    """RA Colony 統合 — _delegate_to_queen 前の要求分析ゲート.

    BeekeeperMCPServer に Mixin として組み込み、タスク委譲前に
    RA Colony による要求分析を実行する。

    依存メソッド（他 Mixin が提供）:
    - _ask_user(question, options, timeout) → str
    """

    if TYPE_CHECKING:
        _ra_enabled: bool
        _ra_components: dict[str, Any]

        async def _ask_user(
            self,
            question: str,
            options: list[str] | None = None,
            timeout: float | None = None,
        ) -> str: ...

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def _analyze_requirements(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> RAAnalysisResult:
        """タスクを RA Colony で分析する.

        RAOrchestrator を生成して intake → step ループを実行し、
        CLARIFY_GEN 状態で質問が存在する場合は _ask_user() 経由で
        ユーザーに提示する。

        Args:
            task: 分析対象のタスク文字列
            context: 追加コンテキスト

        Returns:
            RAAnalysisResult（passed, spec_draft, gate_result, answers, events）
        """
        # RA 無効時は即パス
        if not getattr(self, "_ra_enabled", True):
            return RAAnalysisResult(
                passed=True,
                analysis_path=AnalysisPath.INSTANT_PASS,
            )

        orch = self._create_ra_orchestrator()
        await orch.intake(task)

        answers: dict[str, str] = {}

        while not orch.is_terminal:
            prev_state = orch.current_state
            await orch.step()

            # CLARIFY_GEN 到達時: 質問があればユーザーに提示
            if (
                prev_state == RAState.HYPOTHESIS_BUILD
                and orch.current_state == RAState.CLARIFY_GEN
                and orch.clarification_rounds
            ):
                latest_round = orch.clarification_rounds[-1]
                if latest_round.questions:
                    round_answers = await self._present_clarification_questions(latest_round)
                    answers.update(round_answers)

        return RAAnalysisResult(
            passed=orch.is_complete,
            analysis_path=orch.analysis_path or AnalysisPath.FULL_ANALYSIS,
            spec_draft=orch.spec_drafts[-1] if orch.spec_drafts else None,
            gate_result=orch.gate_result,
            answers=answers,
            events=list(orch.events),
        )

    async def _present_clarification_questions(
        self,
        round_: ClarificationRound,
    ) -> dict[str, str]:
        """ClarificationRound の質問をユーザーに提示して回答を収集する.

        各質問を _ask_user() 経由で順次提示し、回答を辞書として返す。

        Args:
            round_: 質問ラウンド

        Returns:
            {question_id: answer} のマッピング
        """
        answers: dict[str, str] = {}

        for question in round_.questions:
            options = question.options if question.options else None
            answer = await self._ask_user(
                question=question.text,
                options=options,
            )
            answers[question.question_id] = answer

        return answers

    def _format_analysis_summary(self, result: RAAnalysisResult) -> str:
        """分析結果をユーザー向けにフォーマットする.

        §10.1 のインタラクションパターンに準じた表示用サマリを返す。

        Args:
            result: RA分析結果

        Returns:
            フォーマットされたサマリ文字列
        """
        lines: list[str] = []

        if result.analysis_path == AnalysisPath.INSTANT_PASS:
            lines.append("✅ 要求を理解しました（即実行）")
            if result.spec_draft:
                lines.append(f"  Goal: {result.spec_draft.goal}")
            lines.append("  → 追加確認なしで実行します")
            return "\n".join(lines)

        if result.passed:
            lines.append("✅ 要求分析完了")
            if result.spec_draft:
                lines.append(f"  Goal: {result.spec_draft.goal}")
            if result.answers:
                lines.append(f"  確認事項: {len(result.answers)}件回答済み")
            return "\n".join(lines)

        # 失敗ケース
        lines.append("❌ 要求分析でブロックされました")
        if result.gate_result:
            for action in result.gate_result.required_actions:
                lines.append(f"  - {action}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # factory
    # ------------------------------------------------------------------

    def _create_ra_orchestrator(self) -> RAOrchestrator:
        """RAOrchestrator を生成する.

        _ra_components から注入されたコンポーネントを使用する。
        未設定のコンポーネントは None（スタブ動作）。

        Returns:
            設定済み RAOrchestrator
        """
        components = getattr(self, "_ra_components", {})
        return RAOrchestrator(
            scorer=components.get("scorer", AmbiguityScorer()),
            intent_miner=components.get("intent_miner"),
            assumption_mapper=components.get("assumption_mapper"),
            risk_challenger=components.get("risk_challenger"),
            clarify_generator=components.get("clarify_generator"),
            spec_synthesizer=components.get("spec_synthesizer"),
            guard_gate=components.get("guard_gate"),
        )
