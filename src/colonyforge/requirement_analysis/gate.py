"""RAGuardGate — §7 Guard Gate 条件（要求分析版）.

実行 Colony への投入前にルールベースの品質ゲートチェックを実施する。
8つのチェックを実行し RAGateResult を返す。

チェック一覧:
1. goal_clarity        — ゴールが明確で空でないこと
2. success_testability — 全 AcceptanceCriterion が measurable=True かつ metric 非空
3. constraints_explicit — 制約条件が1件以上あること
4. unknowns_managed    — 未解決事項が全て管理されていること
5. risks_addressed     — HIGH の FailureHypothesis に全て mitigation があること
6. challenges_resolved — ChallengeReport の verdict が BLOCK でないこと
7. ambiguity_threshold — AmbiguityScores.ambiguity < 0.5
8. web_evidence_fresh  — Web エビデンスが最新であること（Phase 2: スタブ）
"""

from __future__ import annotations

from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    AmbiguityScores,
    ChallengeReport,
    ChallengeVerdict,
    FailureHypothesis,
    GateCheck,
    RAGateResult,
    SpecDraft,
)


class RAGuardGate:
    """ルールベースの品質ゲート（§7）.

    SpecDraft と分析コンテキストを受け取り、8つのチェックを実行する。
    LLM は使用しない。全てプログラマティックな判定。
    """

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def evaluate(
        self,
        spec: SpecDraft,
        *,
        ambiguity_scores: AmbiguityScores | None = None,
        failure_hypotheses: list[FailureHypothesis] | None = None,
        challenge_report: ChallengeReport | None = None,
    ) -> RAGateResult:
        """SpecDraft に対し 8 チェックを実行して RAGateResult を返す."""
        checks = [
            self._check_goal_clarity(spec),
            self._check_success_testability(spec),
            self._check_constraints_explicit(spec),
            self._check_unknowns_managed(spec),
            self._check_risks_addressed(failure_hypotheses or []),
            self._check_challenges_resolved(challenge_report),
            self._check_ambiguity_threshold(ambiguity_scores),
            self._check_web_evidence_fresh(),
        ]

        passed = all(c.passed for c in checks)
        required_actions = [c.reason for c in checks if not c.passed]

        return RAGateResult(
            passed=passed,
            checks=checks,
            required_actions=required_actions,
        )

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_goal_clarity(self, spec: SpecDraft) -> GateCheck:
        """goal_clarity: ゴールが空でなく明確であること."""
        ok = len(spec.goal.strip()) > 0
        return GateCheck(
            name="goal_clarity",
            passed=ok,
            reason="ゴールが明確" if ok else "ゴールが空または不明確",
        )

    def _check_success_testability(self, spec: SpecDraft) -> GateCheck:
        """success_testability: 全 AcceptanceCriterion が measurable=True かつ metric 非空."""
        if not spec.acceptance_criteria:
            return GateCheck(
                name="success_testability",
                passed=False,
                reason="受入基準が存在しない",
            )

        for item in spec.acceptance_criteria:
            if isinstance(item, AcceptanceCriterion):
                if not item.measurable or not item.metric:
                    return GateCheck(
                        name="success_testability",
                        passed=False,
                        reason="measurable=False または metric 未設定の受入基準が存在",
                    )
            else:
                # str 型 — measurable 判定不能
                return GateCheck(
                    name="success_testability",
                    passed=False,
                    reason="文字列型の受入基準が存在（構造化されていない）",
                )

        return GateCheck(
            name="success_testability",
            passed=True,
            reason="全受入基準が measurable かつ metric 設定済み",
        )

    def _check_constraints_explicit(self, spec: SpecDraft) -> GateCheck:
        """constraints_explicit: 制約条件が1件以上存在すること."""
        ok = len(spec.constraints) >= 1
        return GateCheck(
            name="constraints_explicit",
            passed=ok,
            reason="制約条件あり" if ok else "制約条件が未定義",
        )

    def _check_unknowns_managed(self, spec: SpecDraft) -> GateCheck:
        """unknowns_managed: 未解決事項が残っていないこと."""
        ok = len(spec.open_items) == 0
        return GateCheck(
            name="unknowns_managed",
            passed=ok,
            reason="未解決事項なし" if ok else f"未解決事項が{len(spec.open_items)}件残存",
        )

    def _check_risks_addressed(self, hypotheses: list[FailureHypothesis]) -> GateCheck:
        """risks_addressed: HIGH の FailureHypothesis に全て mitigation があること."""
        high_without = [h for h in hypotheses if h.severity.upper() == "HIGH" and not h.mitigation]
        ok = len(high_without) == 0
        return GateCheck(
            name="risks_addressed",
            passed=ok,
            reason=(
                "HIGH リスク全対処済み" if ok else f"未対処の HIGH リスクが{len(high_without)}件"
            ),
        )

    def _check_challenges_resolved(self, report: ChallengeReport | None) -> GateCheck:
        """challenges_resolved: ChallengeReport の verdict が BLOCK でないこと."""
        if report is None:
            return GateCheck(
                name="challenges_resolved",
                passed=True,
                reason="ChallengeReport なし（チェック不要）",
            )
        ok = report.verdict != ChallengeVerdict.BLOCK
        return GateCheck(
            name="challenges_resolved",
            passed=ok,
            reason=(f"verdict={report.verdict.value}" if ok else "verdict=BLOCK — 反証が未解決"),
        )

    def _check_ambiguity_threshold(self, scores: AmbiguityScores | None) -> GateCheck:
        """ambiguity_threshold: AmbiguityScores.ambiguity < 0.5."""
        if scores is None:
            return GateCheck(
                name="ambiguity_threshold",
                passed=True,
                reason="AmbiguityScores なし（チェック不要）",
            )
        ok = scores.ambiguity < 0.5
        return GateCheck(
            name="ambiguity_threshold",
            passed=ok,
            reason=(
                f"ambiguity={scores.ambiguity:.2f} (< 0.5)"
                if ok
                else f"ambiguity={scores.ambiguity:.2f} (>= 0.5)"
            ),
        )

    def _check_web_evidence_fresh(self) -> GateCheck:
        """web_evidence_fresh: Phase 2 スタブ — 常に合格."""
        return GateCheck(
            name="web_evidence_fresh",
            passed=True,
            reason="Phase 2: Web エビデンス鮮度チェックは未実装（常に合格）",
        )
