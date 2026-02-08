"""Guard Bee プラン検証ルールのテスト

M4-1-c: LLMによるタスク分解結果をGuard Beeで妥当性検証する。
PlanStructureRule (L1) と PlanGoalCoverageRule (L2) のテスト。
TaskPlanner.validate() の統合テスト。
"""

from __future__ import annotations

import pytest

from hiveforge.guard_bee.models import (
    Evidence,
    EvidenceType,
    Verdict,
    VerificationLevel,
)
from hiveforge.guard_bee.plan_rules import (
    PlanGoalCoverageRule,
    PlanStructureRule,
    create_plan_evidence,
)
from hiveforge.guard_bee.rules import RuleRegistry
from hiveforge.guard_bee.verifier import GuardBeeVerifier
from hiveforge.queen_bee.planner import PlannedTask, TaskPlan, TaskPlanner

# =========================================================================
# create_plan_evidence ヘルパーのテスト
# =========================================================================


class TestCreatePlanEvidence:
    """create_plan_evidence ヘルパー関数のテスト"""

    def test_creates_evidence_with_plan_data(self):
        """TaskPlanからEvidence（PLAN_DECOMPOSITION型）が作成される"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
            ],
            reasoning="2ステップに分解",
        )

        # Act
        evidence = create_plan_evidence(plan, original_goal="ECサイト構築")

        # Assert
        assert evidence.evidence_type == EvidenceType.PLAN_DECOMPOSITION
        assert evidence.source == "task_planner"
        assert evidence.content["original_goal"] == "ECサイト構築"
        assert evidence.content["task_count"] == 2
        assert len(evidence.content["tasks"]) == 2
        assert evidence.content["tasks"][0]["task_id"] == "t1"
        assert evidence.content["tasks"][1]["depends_on"] == ["t1"]
        assert evidence.content["reasoning"] == "2ステップに分解"

    def test_single_task_plan(self):
        """単一タスクプランでも正しくEvidence化される"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト実行")])

        # Act
        evidence = create_plan_evidence(plan, original_goal="テスト実行")

        # Assert
        assert evidence.content["task_count"] == 1


# =========================================================================
# PlanStructureRule (L1) のテスト
# =========================================================================


class TestPlanStructureRule:
    """PlanStructureRule — 構造的妥当性の検証 (L1)"""

    @pytest.fixture
    def rule(self):
        return PlanStructureRule()

    def test_metadata(self, rule):
        """ルールのメタデータが正しい"""
        # Assert
        assert rule.name == "plan_structure"
        assert rule.level == VerificationLevel.L1

    def test_pass_valid_plan(self, rule):
        """有効なプランはPASS"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
            ]
        )
        evidence = [create_plan_evidence(plan, "システム構築")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is True

    def test_pass_single_task(self, rule):
        """単一タスクもPASS"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト")])
        evidence = [create_plan_evidence(plan, "テスト")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is True

    def test_fail_no_evidence(self, rule):
        """PLAN_DECOMPOSITION証拠がない場合はFAIL"""
        # Act
        result = rule.verify([], {})

        # Assert
        assert result.passed is False
        assert "証拠なし" in result.message

    def test_fail_circular_dependency(self, rule):
        """循環依存があるプランはFAIL"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="タスクA", depends_on=["t2"]),
                PlannedTask(task_id="t2", goal="タスクB", depends_on=["t1"]),
            ]
        )
        evidence = [create_plan_evidence(plan, "テスト")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "循環依存" in result.message

    def test_fail_invalid_dependency_reference(self, rule):
        """存在しないタスクへの依存参照はFAIL"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="テスト", depends_on=["nonexistent"]),
            ]
        )
        evidence = [create_plan_evidence(plan, "テスト")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "不明な依存" in result.message

    def test_fail_duplicate_goals(self, rule):
        """同じゴール文言が複数タスクにある場合はFAIL"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="テストを書く"),
                PlannedTask(task_id="t2", goal="テストを書く"),
            ]
        )
        evidence = [create_plan_evidence(plan, "テスト")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "重複" in result.message

    def test_pass_details_include_task_count(self, rule):
        """結果のdetailsにタスク数が含まれる"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装"),
            ]
        )
        evidence = [create_plan_evidence(plan, "システム構築")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.details["task_count"] == 2

    def test_fail_malformed_evidence_data(self, rule):
        """Evidence内のタスクデータが不正な場合はFAIL（再構築エラー）"""
        # Arrange: goalキーが欠けた不正データ
        evidence = [
            Evidence(
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                source="task_planner",
                content={
                    "original_goal": "テスト",
                    "task_count": 1,
                    "tasks": [{"task_id": "t1"}],  # goalが欠けている
                    "reasoning": "",
                },
            )
        ]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "エラー" in result.message


# =========================================================================
# PlanGoalCoverageRule (L2) のテスト
# =========================================================================


class TestPlanGoalCoverageRule:
    """PlanGoalCoverageRule — ゴールカバレッジの検証 (L2)"""

    @pytest.fixture
    def rule(self):
        return PlanGoalCoverageRule()

    def test_metadata(self, rule):
        """ルールのメタデータが正しい"""
        # Assert
        assert rule.name == "plan_goal_coverage"
        assert rule.level == VerificationLevel.L2

    def test_pass_distinct_goals(self, rule):
        """各タスクのゴールが異なる場合はPASS"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="データベーススキーマ設計"),
                PlannedTask(task_id="t2", goal="REST API実装"),
                PlannedTask(task_id="t3", goal="ユニットテスト作成"),
            ]
        )
        evidence = [create_plan_evidence(plan, "ECサイト構築")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is True

    def test_fail_no_evidence(self, rule):
        """PLAN_DECOMPOSITION証拠がない場合はFAIL"""
        # Act
        result = rule.verify([], {})

        # Assert
        assert result.passed is False

    def test_fail_goal_repeats_original(self, rule):
        """タスクのゴールが元のゴールをそのまま繰り返すだけの場合はFAIL

        分解の意味がない（ゴールをそのまま1タスクにするのは許容されるが、
        複数タスクが全て元ゴールの繰り返しは不正）。
        """
        # Arrange
        original = "ECサイトを構築する"
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="ECサイトを構築する"),
                PlannedTask(task_id="t2", goal="ECサイトを構築する作業"),
            ]
        )
        evidence = [create_plan_evidence(plan, original)]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "元ゴール" in result.message or "繰り返し" in result.message

    def test_pass_single_task_same_goal(self, rule):
        """単一タスクが元ゴールと同じでもPASS（分解不要と判断された場合）"""
        # Arrange
        original = "テスト実行"
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト実行")])
        evidence = [create_plan_evidence(plan, original)]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is True

    def test_fail_trivially_short_goals(self, rule):
        """極端に短いゴール（3文字以下）が含まれる場合はFAIL"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計とスキーマ策定"),
                PlannedTask(task_id="t2", goal="テスト"),
            ]
        )
        evidence = [create_plan_evidence(plan, "システム構築")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert result.passed is False
        assert "短い" in result.message or "具体性" in result.message

    def test_details_contain_analysis(self, rule):
        """結果のdetailsに分析結果が含まれる"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="データベース設計"),
                PlannedTask(task_id="t2", goal="API実装"),
            ]
        )
        evidence = [create_plan_evidence(plan, "システム構築")]

        # Act
        result = rule.verify(evidence, {})

        # Assert
        assert "original_goal" in result.details


# =========================================================================
# TaskPlanner.validate() 統合テスト
# =========================================================================


class TestTaskPlannerValidate:
    """TaskPlanner.validate() — Guard Bee連携の統合テスト"""

    @pytest.fixture
    def plan_verifier(self, tmp_path):
        """プラン検証用のGuardBeeVerifierを構築"""
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(vault_path=tmp_path)
        registry = RuleRegistry()
        registry.register(PlanStructureRule())
        registry.register(PlanGoalCoverageRule())
        return GuardBeeVerifier(ar=ar, rule_registry=registry)

    def test_validate_valid_plan_passes(self, plan_verifier):
        """有効なプランはPASS判定"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="データベース設計"),
                PlannedTask(task_id="t2", goal="API実装", depends_on=["t1"]),
                PlannedTask(task_id="t3", goal="テスト作成", depends_on=["t2"]),
            ],
            reasoning="3層に分解",
        )

        # Act
        report = TaskPlanner.validate(
            plan=plan,
            original_goal="ECサイト構築",
            verifier=plan_verifier,
            colony_id="colony-1",
            task_id="task-parent",
            run_id="run-1",
        )

        # Assert
        assert report.verdict == Verdict.PASS
        assert report.l1_passed is True
        assert report.l2_passed is True

    def test_validate_circular_dependency_fails(self, plan_verifier):
        """循環依存のあるプランはFAIL判定"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="タスクA", depends_on=["t2"]),
                PlannedTask(task_id="t2", goal="タスクB", depends_on=["t1"]),
            ]
        )

        # Act
        report = TaskPlanner.validate(
            plan=plan,
            original_goal="テスト",
            verifier=plan_verifier,
            colony_id="colony-1",
            task_id="task-parent",
            run_id="run-1",
        )

        # Assert
        assert report.verdict == Verdict.FAIL
        assert report.l1_passed is False

    def test_validate_records_ar_events(self, plan_verifier):
        """検証結果がARにイベントとして記録される"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト実装")])

        # Act
        TaskPlanner.validate(
            plan=plan,
            original_goal="テスト",
            verifier=plan_verifier,
            colony_id="colony-1",
            task_id="task-parent",
            run_id="run-1",
        )

        # Assert: ARにイベントが記録されている
        events = list(plan_verifier._ar.replay("run-1"))
        assert len(events) >= 2  # 検証要求 + 判定結果

    def test_validate_short_goals_conditional_pass(self, plan_verifier):
        """L1パスだがL2失敗（短いゴール）→ CONDITIONAL_PASS"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計とスキーマ策定"),
                PlannedTask(task_id="t2", goal="テスト"),
            ]
        )

        # Act
        report = TaskPlanner.validate(
            plan=plan,
            original_goal="システム構築",
            verifier=plan_verifier,
            colony_id="colony-1",
            task_id="task-parent",
            run_id="run-1",
        )

        # Assert: L1はPASSだがL2でFAIL → CONDITIONAL_PASS
        assert report.l1_passed is True
        assert report.l2_passed is False
        assert report.verdict == Verdict.CONDITIONAL_PASS
