"""Queen Bee 承認フローのテスト

M4-1-d: タスク分解結果の承認フロー（ActionClass連携）。
PlanApprovalGate のリスク分類・承認要否判定・イベント記録テスト。
"""

from __future__ import annotations

import pytest

from hiveforge.core.models.action_class import ActionClass, TrustLevel
from hiveforge.queen_bee.approval import (
    ApprovalDecision,
    PlanApprovalGate,
    PlanApprovalRequest,
)
from hiveforge.queen_bee.planner import PlannedTask, TaskPlan


# =========================================================================
# PlanApprovalGate.classify_plan のテスト
# =========================================================================


class TestClassifyPlan:
    """プランのリスク分類テスト"""

    @pytest.fixture
    def gate(self):
        return PlanApprovalGate()

    def test_single_task_is_reversible(self, gate):
        """単一タスクのプランはREVERSIBLE（デフォルト）"""
        # Arrange
        plan = TaskPlan(tasks=[PlannedTask(task_id="t1", goal="テスト実装")])

        # Act
        action_class = gate.classify_plan(plan)

        # Assert
        assert action_class == ActionClass.REVERSIBLE

    def test_multi_task_is_reversible(self, gate):
        """複数タスクの通常プランはREVERSIBLE"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装"),
                PlannedTask(task_id="t3", goal="テスト作成"),
            ]
        )

        # Act
        action_class = gate.classify_plan(plan)

        # Assert
        assert action_class == ActionClass.REVERSIBLE

    def test_destructive_goal_is_irreversible(self, gate):
        """破壊的キーワードを含むゴールはIRREVERSIBLE"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="本番データベースのマイグレーション実行"),
                PlannedTask(task_id="t2", goal="デプロイの実行"),
            ]
        )

        # Act
        action_class = gate.classify_plan(plan)

        # Assert
        assert action_class == ActionClass.IRREVERSIBLE

    def test_read_only_goals(self, gate):
        """読み取り専用のゴールのみの場合はREAD_ONLY"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="コードの分析と調査"),
                PlannedTask(task_id="t2", goal="ログの確認とレビュー"),
            ]
        )

        # Act
        action_class = gate.classify_plan(plan)

        # Assert
        assert action_class == ActionClass.READ_ONLY

    def test_mixed_goals_takes_highest_risk(self, gate):
        """異なるリスクレベルが混在する場合は最も高いリスクを採用"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="コードの調査"),
                PlannedTask(task_id="t2", goal="ファイルの編集"),
                PlannedTask(task_id="t3", goal="本番へのデプロイ"),
            ]
        )

        # Act
        action_class = gate.classify_plan(plan)

        # Assert
        assert action_class == ActionClass.IRREVERSIBLE


# =========================================================================
# PlanApprovalGate.check_approval のテスト
# =========================================================================


class TestCheckApproval:
    """承認要否判定のテスト"""

    @pytest.fixture
    def gate(self):
        return PlanApprovalGate()

    def test_read_only_no_approval(self, gate):
        """READ_ONLYプランはどのTrustLevelでも承認不要"""
        # Arrange
        plan = TaskPlan(
            tasks=[PlannedTask(task_id="t1", goal="コードの分析と調査")]
        )

        # Act
        request = gate.check_approval(plan, TrustLevel.REPORT_ONLY, "テスト")

        # Assert
        assert request.requires_approval is False

    def test_reversible_low_trust_requires_approval(self, gate):
        """REVERSIBLE + Level 0 → 承認必要"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="ファイルの編集と修正"),
                PlannedTask(task_id="t2", goal="テスト追加"),
            ]
        )

        # Act
        request = gate.check_approval(plan, TrustLevel.REPORT_ONLY, "テスト")

        # Assert
        assert request.requires_approval is True
        assert request.action_class == ActionClass.REVERSIBLE

    def test_reversible_high_trust_no_approval(self, gate):
        """REVERSIBLE + Level 2 → 承認不要"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="ファイルの編集と修正"),
            ]
        )

        # Act
        request = gate.check_approval(plan, TrustLevel.AUTO_NOTIFY, "テスト")

        # Assert
        assert request.requires_approval is False

    def test_irreversible_requires_approval(self, gate):
        """IRREVERSIBLEプランはLevel 3でも承認必要"""
        # Arrange
        plan = TaskPlan(
            tasks=[PlannedTask(task_id="t1", goal="本番DBのデプロイ実行")]
        )

        # Act
        request = gate.check_approval(plan, TrustLevel.FULL_DELEGATION, "テスト")

        # Assert
        assert request.requires_approval is True

    def test_request_contains_plan_summary(self, gate):
        """承認リクエストにプラン概要が含まれる"""
        # Arrange
        plan = TaskPlan(
            tasks=[
                PlannedTask(task_id="t1", goal="DB設計"),
                PlannedTask(task_id="t2", goal="API実装"),
            ],
            reasoning="2ステップに分解",
        )

        # Act
        request = gate.check_approval(plan, TrustLevel.PROPOSE_CONFIRM, "ECサイト構築")

        # Assert
        assert request.original_goal == "ECサイト構築"
        assert request.task_count == 2
        assert request.reasoning == "2ステップに分解"


# =========================================================================
# PlanApprovalRequest モデルのテスト
# =========================================================================


class TestPlanApprovalRequest:
    """PlanApprovalRequestデータモデルのテスト"""

    def test_create_approval_required(self):
        """承認必要なリクエストの作成"""
        # Act
        request = PlanApprovalRequest(
            requires_approval=True,
            action_class=ActionClass.REVERSIBLE,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            original_goal="テスト",
            task_count=2,
            reasoning="分解理由",
            task_goals=["タスク1", "タスク2"],
        )

        # Assert
        assert request.requires_approval is True
        assert request.action_class == ActionClass.REVERSIBLE
        assert request.task_count == 2

    def test_frozen(self):
        """PlanApprovalRequestはイミュータブル"""
        # Arrange
        request = PlanApprovalRequest(
            requires_approval=False,
            action_class=ActionClass.READ_ONLY,
            trust_level=TrustLevel.FULL_DELEGATION,
            original_goal="テスト",
            task_count=1,
            task_goals=["テスト"],
        )

        # Act & Assert
        with pytest.raises(Exception):
            request.requires_approval = True  # type: ignore

    def test_to_event_payload(self):
        """イベントペイロードに変換できる"""
        # Arrange
        request = PlanApprovalRequest(
            requires_approval=True,
            action_class=ActionClass.IRREVERSIBLE,
            trust_level=TrustLevel.PROPOSE_CONFIRM,
            original_goal="デプロイ",
            task_count=3,
            reasoning="段階的に実行",
            task_goals=["準備", "実行", "確認"],
        )

        # Act
        payload = request.to_event_payload()

        # Assert
        assert payload["requires_approval"] is True
        assert payload["action_class"] == "irreversible"
        assert payload["trust_level"] == 1
        assert payload["task_count"] == 3


# =========================================================================
# ApprovalDecision モデルのテスト
# =========================================================================


class TestApprovalDecision:
    """ApprovalDecisionデータモデルのテスト"""

    def test_approved(self):
        """承認の作成"""
        # Act
        decision = ApprovalDecision(approved=True, reason="問題なし")

        # Assert
        assert decision.approved is True
        assert decision.reason == "問題なし"

    def test_rejected(self):
        """却下の作成"""
        # Act
        decision = ApprovalDecision(approved=False, reason="リスクが高い")

        # Assert
        assert decision.approved is False

    def test_default_reason(self):
        """reasonのデフォルトは空文字"""
        # Act
        decision = ApprovalDecision(approved=True)

        # Assert
        assert decision.reason == ""

    def test_frozen(self):
        """ApprovalDecisionはイミュータブル"""
        # Arrange
        decision = ApprovalDecision(approved=True)

        # Act & Assert
        with pytest.raises(Exception):
            decision.approved = False  # type: ignore
