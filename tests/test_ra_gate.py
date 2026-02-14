"""RAGuardGate テスト — §7 Guard Gate 条件（要求分析版）.

RAGuardGate は実行 Colony への投入前に品質ゲートチェックを実施する。
ルールベースの8チェックで SpecDraft + 分析コンテキストを検証する。
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

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_spec(
    *,
    goal: str = "ユーザー認証機能を実装する",
    acceptance_criteria: list | None = None,
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
    open_items: list[str] | None = None,
    risk_mitigations: list[str] | None = None,
) -> SpecDraft:
    """テスト用 SpecDraft を生成."""
    if acceptance_criteria is None:
        acceptance_criteria = [
            AcceptanceCriterion(
                text="ログイン成功時にJWT発行",
                measurable=True,
                metric="JWT発行有無",
                threshold="成功時に必ず発行",
            )
        ]
    return SpecDraft(
        draft_id="d1",
        version=1,
        goal=goal,
        acceptance_criteria=acceptance_criteria,
        constraints=["HTTPS必須"] if constraints is None else constraints,
        non_goals=non_goals if non_goals is not None else [],
        open_items=open_items if open_items is not None else [],
        risk_mitigations=risk_mitigations if risk_mitigations is not None else [],
    )


def _make_scores(
    *,
    ambiguity: float = 0.3,
    context_sufficiency: float = 0.8,
    execution_risk: float = 0.2,
) -> AmbiguityScores:
    """テスト用 AmbiguityScores を生成."""
    return AmbiguityScores(
        ambiguity=ambiguity,
        context_sufficiency=context_sufficiency,
        execution_risk=execution_risk,
    )


# ---------------------------------------------------------------------------
# 初期化テスト
# ---------------------------------------------------------------------------


class TestRAGuardGateInit:
    """RAGuardGate の初期化."""

    def test_create_gate(self) -> None:
        """インスタンスを生成できる."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange & Act
        gate = RAGuardGate()

        # Assert
        assert gate is not None


# ---------------------------------------------------------------------------
# evaluate() — 全体テスト
# ---------------------------------------------------------------------------


class TestGuardGateEvaluate:
    """RAGuardGate.evaluate() のテスト."""

    def test_pass_with_good_spec(self) -> None:
        """全チェック合格時は passed=True."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec()
        scores = _make_scores()

        # Act
        result = gate.evaluate(
            spec=spec,
            ambiguity_scores=scores,
        )

        # Assert
        assert isinstance(result, RAGateResult)
        assert result.passed is True
        assert all(c.passed for c in result.checks)

    def test_returns_gate_checks(self) -> None:
        """結果に個別の GateCheck が含まれる."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()

        # Act
        result = gate.evaluate(spec=_make_spec(), ambiguity_scores=_make_scores())

        # Assert
        assert len(result.checks) > 0
        assert all(isinstance(c, GateCheck) for c in result.checks)


# ---------------------------------------------------------------------------
# 個別チェックテスト
# ---------------------------------------------------------------------------


class TestGoalClarity:
    """goal_clarity チェック — goalが適切か."""

    def test_clear_goal_passes(self) -> None:
        """明確なゴールは合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(goal="ユーザー認証機能を実装する")

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "goal_clarity")
        assert check.passed is True


class TestSuccessTestability:
    """success_testability チェック — 全 AcceptanceCriterion が measurable."""

    def test_measurable_criteria_passes(self) -> None:
        """全基準が measurable=True なら合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(
            acceptance_criteria=[
                AcceptanceCriterion(text="AC1", measurable=True, metric="m", threshold="t"),
            ]
        )

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "success_testability")
        assert check.passed is True

    def test_unmeasurable_criteria_fails(self) -> None:
        """measurable=False の基準があると不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(
            acceptance_criteria=[
                AcceptanceCriterion(text="AC1", measurable=False),
            ]
        )

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "success_testability")
        assert check.passed is False

    def test_string_criteria_fails(self) -> None:
        """文字列の基準はmeasurable判定不能で不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(acceptance_criteria=["テストが通る"])

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "success_testability")
        assert check.passed is False


class TestConstraintsExplicit:
    """constraints_explicit チェック — 制約が1件以上."""

    def test_with_constraints_passes(self) -> None:
        """制約条件が存在すれば合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(constraints=["HTTPS必須"])

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "constraints_explicit")
        assert check.passed is True

    def test_without_constraints_fails(self) -> None:
        """制約条件が空だと不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(constraints=[])

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        check = next(c for c in result.checks if c.name == "constraints_explicit")
        assert check.passed is False


class TestRisksAddressed:
    """risks_addressed チェック — HIGH の FailureHypothesis 全件に mitigation."""

    def test_no_hypotheses_passes(self) -> None:
        """失敗仮説なしなら合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            failure_hypotheses=[],
        )

        # Assert
        check = next(c for c in result.checks if c.name == "risks_addressed")
        assert check.passed is True

    def test_high_with_mitigation_passes(self) -> None:
        """HIGH 仮説に mitigation があれば合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        hypotheses = [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="攻撃リスク",
                severity="HIGH",
                mitigation="レート制限",
            ),
        ]

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            failure_hypotheses=hypotheses,
        )

        # Assert
        check = next(c for c in result.checks if c.name == "risks_addressed")
        assert check.passed is True

    def test_high_without_mitigation_fails(self) -> None:
        """HIGH 仮説に mitigation がないと不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        hypotheses = [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="攻撃リスク",
                severity="HIGH",
            ),
        ]

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            failure_hypotheses=hypotheses,
        )

        # Assert
        check = next(c for c in result.checks if c.name == "risks_addressed")
        assert check.passed is False

    def test_medium_without_mitigation_passes(self) -> None:
        """MEDIUM 仮説に mitigation がなくても合格（HiGHのみチェック）."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        hypotheses = [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="軽微リスク",
                severity="MEDIUM",
            ),
        ]

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            failure_hypotheses=hypotheses,
        )

        # Assert
        check = next(c for c in result.checks if c.name == "risks_addressed")
        assert check.passed is True


class TestAmbiguityThreshold:
    """ambiguity_threshold チェック — AmbiguityScore.ambiguity < 0.5."""

    def test_low_ambiguity_passes(self) -> None:
        """ambiguity < 0.5 なら合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        scores = _make_scores(ambiguity=0.3)

        # Act
        result = gate.evaluate(spec=_make_spec(), ambiguity_scores=scores)

        # Assert
        check = next(c for c in result.checks if c.name == "ambiguity_threshold")
        assert check.passed is True

    def test_high_ambiguity_fails(self) -> None:
        """ambiguity >= 0.5 なら不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        scores = _make_scores(ambiguity=0.6)

        # Act
        result = gate.evaluate(spec=_make_spec(), ambiguity_scores=scores)

        # Assert
        check = next(c for c in result.checks if c.name == "ambiguity_threshold")
        assert check.passed is False

    def test_boundary_ambiguity_fails(self) -> None:
        """ambiguity == 0.5 は不合格（境界値）."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        scores = _make_scores(ambiguity=0.5)

        # Act
        result = gate.evaluate(spec=_make_spec(), ambiguity_scores=scores)

        # Assert
        check = next(c for c in result.checks if c.name == "ambiguity_threshold")
        assert check.passed is False


class TestChallengesResolved:
    """challenges_resolved チェック — ChallengeReport の verdict が BLOCK でない."""

    def test_no_report_passes(self) -> None:
        """ChallengeReport なしなら合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
        )

        # Assert
        check = next(c for c in result.checks if c.name == "challenges_resolved")
        assert check.passed is True

    def test_pass_with_risks_passes(self) -> None:
        """verdict=PASS_WITH_RISKS なら合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        report = ChallengeReport(
            report_id="cr1",
            draft_id="d1",
            verdict=ChallengeVerdict.PASS_WITH_RISKS,
            summary="LOW残存のみ",
        )

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            challenge_report=report,
        )

        # Assert
        check = next(c for c in result.checks if c.name == "challenges_resolved")
        assert check.passed is True

    def test_block_verdict_fails(self) -> None:
        """verdict=BLOCK なら不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        report = ChallengeReport(
            report_id="cr1",
            draft_id="d1",
            verdict=ChallengeVerdict.BLOCK,
            summary="HIGH未対処",
        )

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            challenge_report=report,
        )

        # Assert
        check = next(c for c in result.checks if c.name == "challenges_resolved")
        assert check.passed is False


# ---------------------------------------------------------------------------
# 全体不合格時のテスト
# ---------------------------------------------------------------------------


class TestGuardGateOverallFailure:
    """1つ以上のチェックが不合格なら全体不合格."""

    def test_any_failure_fails_overall(self) -> None:
        """制約なし → constraints_explicit 不合格 → 全体不合格."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        spec = _make_spec(constraints=[])

        # Act
        result = gate.evaluate(spec=spec, ambiguity_scores=_make_scores())

        # Assert
        assert result.passed is False

    def test_required_actions_populated(self) -> None:
        """不合格時に required_actions が設定される."""
        from colonyforge.requirement_analysis.gate import RAGuardGate

        # Arrange
        gate = RAGuardGate()
        hypotheses = [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="攻撃リスク",
                severity="HIGH",
            ),
        ]

        # Act
        result = gate.evaluate(
            spec=_make_spec(),
            ambiguity_scores=_make_scores(),
            failure_hypotheses=hypotheses,
        )

        # Assert
        assert len(result.required_actions) > 0
