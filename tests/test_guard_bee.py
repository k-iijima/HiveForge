"""Guard Bee テスト

品質検証エージェントのテスト。
M3-3 完了条件:
- Colonyの成果物がGuard Beeによって検証される
- 証拠（diff, テスト結果, カバレッジ）に基づいて合格/差戻しが判定される
- 検証結果がARイベントとして記録される
"""

from __future__ import annotations

import pytest

from hiveforge.core import AkashicRecord
from hiveforge.core.events import EventType
from hiveforge.guard_bee.models import (
    Evidence,
    EvidenceType,
    GuardBeeReport,
    RuleResult,
    Verdict,
    VerificationLevel,
)
from hiveforge.guard_bee.rules import (
    AllTestsPassRule,
    CoverageThresholdRule,
    DiffExistsRule,
    LintCleanRule,
    RuleRegistry,
    TypeCheckRule,
)
from hiveforge.guard_bee.verifier import GuardBeeVerifier

# =========================================================================
# Verdict / VerificationLevel 列挙型テスト
# =========================================================================


class TestEnums:
    """列挙型のテスト"""

    def test_verdict_values(self):
        """Verdictの3値が正しい"""
        assert Verdict.PASS.value == "pass"
        assert Verdict.CONDITIONAL_PASS.value == "conditional_pass"
        assert Verdict.FAIL.value == "fail"

    def test_verification_level_values(self):
        """VerificationLevelの2レベルが正しい"""
        assert VerificationLevel.L1.value == "L1"
        assert VerificationLevel.L2.value == "L2"

    def test_evidence_type_values(self):
        """EvidenceTypeの全種別"""
        assert len(EvidenceType) == 7


# =========================================================================
# Evidence モデルテスト
# =========================================================================


class TestEvidence:
    """証拠データモデルのテスト"""

    def test_create_evidence(self):
        """証拠を作成できる"""
        # Act
        evidence = Evidence(
            evidence_type=EvidenceType.LINT_RESULT,
            source="ruff",
            content={"errors": 0, "warnings": 0},
        )

        # Assert
        assert evidence.evidence_type == EvidenceType.LINT_RESULT
        assert evidence.source == "ruff"
        assert evidence.content["errors"] == 0

    def test_evidence_frozen(self):
        """証拠はイミュータブル"""
        evidence = Evidence(
            evidence_type=EvidenceType.DIFF,
            source="git",
        )
        with pytest.raises(Exception):
            evidence.source = "other"  # type: ignore

    def test_evidence_default_timestamp(self):
        """証拠にデフォルトのタイムスタンプが設定される"""
        evidence = Evidence(
            evidence_type=EvidenceType.DIFF,
            source="git",
        )
        assert evidence.collected_at is not None


# =========================================================================
# RuleResult モデルテスト
# =========================================================================


class TestRuleResult:
    """個別検証結果のテスト"""

    def test_create_passed_result(self):
        """合格結果を作成"""
        result = RuleResult(
            rule_name="test_rule",
            level=VerificationLevel.L1,
            passed=True,
            message="OK",
        )
        assert result.passed is True
        assert result.level == VerificationLevel.L1

    def test_create_failed_result(self):
        """不合格結果を作成"""
        result = RuleResult(
            rule_name="lint_clean",
            level=VerificationLevel.L1,
            passed=False,
            message="3 errors found",
            evidence_type=EvidenceType.LINT_RESULT,
        )
        assert result.passed is False
        assert result.evidence_type == EvidenceType.LINT_RESULT


# =========================================================================
# GuardBeeReport モデルテスト
# =========================================================================


class TestGuardBeeReport:
    """検証レポートのテスト"""

    def test_create_pass_report(self):
        """PASS判定のレポートを作成"""
        report = GuardBeeReport(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-1",
            verdict=Verdict.PASS,
            l1_passed=True,
            l2_passed=True,
            evidence_count=3,
        )
        assert report.verdict == Verdict.PASS
        assert report.remand_reason is None

    def test_create_fail_report(self):
        """FAIL判定のレポートを作成"""
        report = GuardBeeReport(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-1",
            verdict=Verdict.FAIL,
            l1_passed=False,
            l2_passed=False,
            remand_reason="テストが失敗",
            improvement_instructions=["テストを修正してください"],
        )
        assert report.verdict == Verdict.FAIL
        assert report.remand_reason == "テストが失敗"
        assert len(report.improvement_instructions) == 1

    def test_to_event_payload(self):
        """イベントペイロードへの変換"""
        # Arrange
        results = (
            RuleResult(rule_name="r1", level=VerificationLevel.L1, passed=True),
            RuleResult(rule_name="r2", level=VerificationLevel.L1, passed=False, message="NG"),
        )
        report = GuardBeeReport(
            colony_id="c1",
            task_id="t1",
            run_id="run-1",
            verdict=Verdict.FAIL,
            rule_results=results,
            evidence_count=2,
            l1_passed=False,
            l2_passed=False,
            remand_reason="L1失敗",
        )

        # Act
        payload = report.to_event_payload()

        # Assert
        assert payload["verdict"] == "fail"
        assert payload["rules_total"] == 2
        assert payload["rules_passed"] == 1
        assert payload["colony_id"] == "c1"
        assert payload["remand_reason"] == "L1失敗"


# =========================================================================
# 組み込みルールのテスト
# =========================================================================


class TestLintCleanRule:
    """Lintクリーンルールのテスト"""

    def test_pass_when_clean(self):
        """エラー0/警告0でPASS"""
        # Arrange
        rule = LintCleanRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.LINT_RESULT,
                source="ruff",
                content={"errors": 0, "warnings": 0},
            )
        ]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is True

    def test_fail_when_errors(self):
        """エラーがあればFAIL"""
        rule = LintCleanRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.LINT_RESULT,
                source="ruff",
                content={"errors": 3, "warnings": 0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False

    def test_fail_when_no_evidence(self):
        """証拠なしでFAIL"""
        rule = LintCleanRule()
        result = rule.verify([], {})
        assert result.passed is False


class TestTestPassRule:
    """テストパスルールのテスト"""

    def test_pass_when_all_pass(self):
        """全テストパスでPASS"""
        rule = AllTestsPassRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_RESULT,
                source="pytest",
                content={"total": 100, "passed": 100, "failed": 0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True

    def test_fail_when_some_fail(self):
        """失敗テストがあるとFAIL"""
        rule = AllTestsPassRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_RESULT,
                source="pytest",
                content={"total": 100, "passed": 98, "failed": 2},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False

    def test_fail_when_no_tests(self):
        """テスト0件でFAIL"""
        rule = AllTestsPassRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_RESULT,
                source="pytest",
                content={"total": 0, "passed": 0, "failed": 0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False


class TestCoverageThresholdRule:
    """カバレッジ閾値ルールのテスト"""

    def test_pass_above_threshold(self):
        """閾値以上でPASS"""
        rule = CoverageThresholdRule(threshold=80.0)
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 95.0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True

    def test_fail_below_threshold(self):
        """閾値未満でFAIL"""
        rule = CoverageThresholdRule(threshold=80.0)
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 70.0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False

    def test_pass_exactly_at_threshold(self):
        """閾値ちょうどでPASS"""
        rule = CoverageThresholdRule(threshold=80.0)
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 80.0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True

    def test_custom_threshold(self):
        """カスタム閾値"""
        rule = CoverageThresholdRule(threshold=50.0)
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 60.0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True


class TestDiffExistsRule:
    """差分存在確認ルールのテスト"""

    def test_pass_with_diff(self):
        """差分ありでPASS"""
        rule = DiffExistsRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.DIFF,
                source="git",
                content={"files_changed": 3},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True

    def test_fail_no_diff(self):
        """差分なしでFAIL"""
        rule = DiffExistsRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.DIFF,
                source="git",
                content={"files_changed": 0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False


class TestTypeCheckRule:
    """型チェックルールのテスト"""

    def test_pass_no_errors(self):
        """エラー0でPASS"""
        rule = TypeCheckRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TYPE_CHECK,
                source="mypy",
                content={"errors": 0},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is True

    def test_skip_when_no_evidence(self):
        """証拠なしでもPASS（型チェックはオプション）"""
        rule = TypeCheckRule()
        result = rule.verify([], {})
        assert result.passed is True

    def test_fail_with_errors(self):
        """型エラーありでFAIL"""
        rule = TypeCheckRule()
        evidence = [
            Evidence(
                evidence_type=EvidenceType.TYPE_CHECK,
                source="mypy",
                content={"errors": 5},
            )
        ]
        result = rule.verify(evidence, {})
        assert result.passed is False


# =========================================================================
# RuleRegistry テスト
# =========================================================================


class TestRuleRegistry:
    """ルールレジストリのテスト"""

    def test_create_default(self):
        """デフォルトレジストリは5ルール"""
        registry = RuleRegistry.create_default()
        assert len(registry.get_rules()) == 5

    def test_default_rule_names(self):
        """デフォルトルール名"""
        registry = RuleRegistry.create_default()
        names = registry.get_rule_names()
        assert "diff_exists" in names
        assert "lint_clean" in names
        assert "tests_pass" in names
        assert "coverage_threshold" in names
        assert "type_check" in names

    def test_filter_by_level(self):
        """レベルでフィルタリング"""
        registry = RuleRegistry.create_default()
        l1_rules = registry.get_rules(VerificationLevel.L1)
        assert all(r.level == VerificationLevel.L1 for r in l1_rules)

    def test_custom_threshold(self):
        """カスタムカバレッジ閾値"""
        registry = RuleRegistry.create_default(coverage_threshold=90.0)
        coverage_rule = [r for r in registry.get_rules() if r.name == "coverage_threshold"][0]
        assert isinstance(coverage_rule, CoverageThresholdRule)
        assert coverage_rule.threshold == 90.0


# =========================================================================
# GuardBeeVerifier テスト
# =========================================================================


class TestGuardBeeVerifier:
    """検証エンジンのテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path)

    @pytest.fixture
    def verifier(self, ar):
        return GuardBeeVerifier(ar=ar)

    def _make_passing_evidence(self) -> list[Evidence]:
        """全ルール合格する証拠セット"""
        return [
            Evidence(
                evidence_type=EvidenceType.DIFF,
                source="git",
                content={"files_changed": 2},
            ),
            Evidence(
                evidence_type=EvidenceType.LINT_RESULT,
                source="ruff",
                content={"errors": 0, "warnings": 0},
            ),
            Evidence(
                evidence_type=EvidenceType.TEST_RESULT,
                source="pytest",
                content={"total": 50, "passed": 50, "failed": 0},
            ),
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 95.0},
            ),
        ]

    def _make_failing_evidence(self) -> list[Evidence]:
        """テスト失敗する証拠セット"""
        return [
            Evidence(
                evidence_type=EvidenceType.DIFF,
                source="git",
                content={"files_changed": 2},
            ),
            Evidence(
                evidence_type=EvidenceType.LINT_RESULT,
                source="ruff",
                content={"errors": 3, "warnings": 1},
            ),
            Evidence(
                evidence_type=EvidenceType.TEST_RESULT,
                source="pytest",
                content={"total": 50, "passed": 48, "failed": 2},
            ),
            Evidence(
                evidence_type=EvidenceType.TEST_COVERAGE,
                source="pytest-cov",
                content={"coverage_percent": 70.0},
            ),
        ]

    def test_verify_all_pass(self, verifier):
        """全証拠合格でPASS判定"""
        # Arrange
        evidence = self._make_passing_evidence()

        # Act
        report = verifier.verify(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-1",
            evidence=evidence,
        )

        # Assert
        assert report.verdict == Verdict.PASS
        assert report.l1_passed is True
        assert report.remand_reason is None

    def test_verify_fail_records_reason(self, verifier):
        """L1失敗でFAIL判定と差戻し理由"""
        # Arrange
        evidence = self._make_failing_evidence()

        # Act
        report = verifier.verify(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-1",
            evidence=evidence,
        )

        # Assert
        assert report.verdict == Verdict.FAIL
        assert report.l1_passed is False
        assert report.remand_reason is not None
        assert len(report.improvement_instructions) > 0

    def test_verify_records_events_in_ar(self, verifier, ar):
        """検証結果がARイベントとして記録される"""
        # Arrange
        evidence = self._make_passing_evidence()

        # Act
        verifier.verify(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-1",
            evidence=evidence,
        )

        # Assert: 検証要求 + 判定の2イベント
        events = list(ar.replay("run-1"))
        event_types = [e.type for e in events]
        assert EventType.GUARD_VERIFICATION_REQUESTED in event_types
        assert EventType.GUARD_PASSED in event_types

    def test_verify_fail_records_fail_event(self, verifier, ar):
        """FAIL判定がARにguard.failedとして記録される"""
        # Arrange
        evidence = self._make_failing_evidence()

        # Act
        verifier.verify(
            colony_id="colony-1",
            task_id="task-1",
            run_id="run-fail-1",
            evidence=evidence,
        )

        # Assert
        events = list(ar.replay("run-fail-1"))
        event_types = [e.type for e in events]
        assert EventType.GUARD_FAILED in event_types

    def test_report_has_evidence_count(self, verifier):
        """レポートに証拠数が記録される"""
        evidence = self._make_passing_evidence()
        report = verifier.verify(colony_id="c1", task_id="t1", run_id="r1", evidence=evidence)
        assert report.evidence_count == 4

    def test_report_has_rule_results(self, verifier):
        """レポートに全ルール結果が記録される"""
        evidence = self._make_passing_evidence()
        report = verifier.verify(colony_id="c1", task_id="t1", run_id="r1", evidence=evidence)
        # デフォルト5ルール
        assert len(report.rule_results) == 5

    def test_empty_evidence_fails(self, verifier):
        """証拠なしでFAIL"""
        report = verifier.verify(colony_id="c1", task_id="t1", run_id="r1", evidence=[])
        assert report.verdict == Verdict.FAIL

    def test_actor_format(self, verifier, ar):
        """ARイベントのactorフォーマット"""
        evidence = self._make_passing_evidence()
        verifier.verify(
            colony_id="col-test",
            task_id="t1",
            run_id="run-actor",
            evidence=evidence,
        )
        events = list(ar.replay("run-actor"))
        assert all(e.actor == "guard-col-test" for e in events)

    def test_verify_with_custom_registry(self, ar):
        """カスタムルールレジストリで検証"""
        # Arrange: Lintだけのレジストリ
        registry = RuleRegistry()
        registry.register(LintCleanRule())

        verifier = GuardBeeVerifier(ar=ar, rule_registry=registry)
        evidence = [
            Evidence(
                evidence_type=EvidenceType.LINT_RESULT,
                source="ruff",
                content={"errors": 0, "warnings": 0},
            )
        ]

        # Act
        report = verifier.verify(colony_id="c1", task_id="t1", run_id="r1", evidence=evidence)

        # Assert
        assert report.verdict == Verdict.PASS
        assert len(report.rule_results) == 1


# =========================================================================
# Guard Bee EventType テスト
# =========================================================================


class TestGuardBeeEvents:
    """Guard Bee用EventTypeの定義確認"""

    def test_guard_event_types_exist(self):
        """Guard Bee用の4つのEventTypeが定義されている"""
        assert hasattr(EventType, "GUARD_VERIFICATION_REQUESTED")
        assert hasattr(EventType, "GUARD_PASSED")
        assert hasattr(EventType, "GUARD_CONDITIONAL_PASSED")
        assert hasattr(EventType, "GUARD_FAILED")

    def test_guard_event_type_values(self):
        """Guard Beeイベントの値が正しい"""
        assert EventType.GUARD_VERIFICATION_REQUESTED.value == "guard.verification_requested"
        assert EventType.GUARD_PASSED.value == "guard.passed"
        assert EventType.GUARD_CONDITIONAL_PASSED.value == "guard.conditional_passed"
        assert EventType.GUARD_FAILED.value == "guard.failed"
