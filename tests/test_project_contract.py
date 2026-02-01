"""ProjectContract スキーマのテスト

外部フィードバック対応: 構造化されたプロジェクトコンテキスト共有スキーマ。
"""

import pytest
from pydantic import ValidationError

from hiveforge.core.models.project_contract import (
    DecisionRef,
    ProjectContract,
)


class TestDecisionRef:
    """DecisionRef（決定参照）のテスト"""

    def test_create_decision_ref(self):
        """決定参照を生成できる"""
        # Arrange & Act
        ref = DecisionRef(
            id="dec-001",
            summary="モバイルファースト設計を採用",
            decided_at="2026-02-01T10:00:00Z",
        )

        # Assert
        assert ref.id == "dec-001"
        assert ref.summary == "モバイルファースト設計を採用"
        assert ref.decided_at == "2026-02-01T10:00:00Z"

    def test_decision_ref_requires_id(self):
        """DecisionRefはidが必須"""
        # Act & Assert
        with pytest.raises(ValidationError):
            DecisionRef(
                summary="test",
                decided_at="2026-02-01T10:00:00Z",
            )

    def test_decision_ref_requires_summary(self):
        """DecisionRefはsummaryが必須"""
        # Act & Assert
        with pytest.raises(ValidationError):
            DecisionRef(
                id="dec-001",
                decided_at="2026-02-01T10:00:00Z",
            )


class TestProjectContract:
    """ProjectContract（プロジェクト契約）のテスト"""

    def test_create_project_contract_minimal(self):
        """最小限のProjectContractを生成できる

        全てのフィールドは空リストでも可。
        """
        # Arrange & Act
        contract = ProjectContract(
            goals=[],
            constraints=[],
            non_goals=[],
            decisions=[],
            open_questions=[],
        )

        # Assert
        assert contract.goals == []
        assert contract.constraints == []
        assert contract.non_goals == []
        assert contract.decisions == []
        assert contract.open_questions == []

    def test_create_project_contract_full(self):
        """完全なProjectContractを生成できる"""
        # Arrange
        decision_ref = DecisionRef(
            id="dec-001",
            summary="Stripe決済を採用",
            decided_at="2026-02-01T10:00:00Z",
        )

        # Act
        contract = ProjectContract(
            goals=["ECサイトを3月末までにリリース", "モバイルファーストで設計"],
            constraints=["予算500万円以内", "既存DBを活用"],
            non_goals=["B2B機能は対象外", "多言語対応は次フェーズ"],
            decisions=[decision_ref],
            open_questions=["在庫管理の要否", "ポイント機能の優先度"],
        )

        # Assert
        assert len(contract.goals) == 2
        assert len(contract.constraints) == 2
        assert len(contract.non_goals) == 2
        assert len(contract.decisions) == 1
        assert contract.decisions[0].id == "dec-001"
        assert len(contract.open_questions) == 2

    def test_project_contract_goals_required(self):
        """ProjectContractはgoalsが必須"""
        # Act & Assert
        with pytest.raises(ValidationError):
            ProjectContract(
                constraints=[],
                non_goals=[],
                decisions=[],
                open_questions=[],
            )

    def test_project_contract_decisions_must_be_decision_ref(self):
        """decisionsはDecisionRefのリストでなければならない"""
        # Act & Assert
        with pytest.raises(ValidationError):
            ProjectContract(
                goals=["test"],
                constraints=[],
                non_goals=[],
                decisions=["not a DecisionRef"],  # 文字列ではダメ
                open_questions=[],
            )

    def test_project_contract_is_immutable(self):
        """ProjectContractはイミュータブル"""
        # Arrange
        contract = ProjectContract(
            goals=["test"],
            constraints=[],
            non_goals=[],
            decisions=[],
            open_questions=[],
        )

        # Act & Assert
        with pytest.raises(ValidationError):
            contract.goals = ["changed"]

    def test_project_contract_to_dict(self):
        """ProjectContractをdictに変換できる"""
        # Arrange
        decision_ref = DecisionRef(
            id="dec-001",
            summary="test decision",
            decided_at="2026-02-01T10:00:00Z",
        )
        contract = ProjectContract(
            goals=["goal1"],
            constraints=["constraint1"],
            non_goals=["non_goal1"],
            decisions=[decision_ref],
            open_questions=["question1"],
        )

        # Act
        data = contract.model_dump()

        # Assert
        assert data["goals"] == ["goal1"]
        assert data["decisions"][0]["id"] == "dec-001"

    def test_project_contract_from_dict(self):
        """dictからProjectContractを生成できる"""
        # Arrange
        data = {
            "goals": ["goal1"],
            "constraints": ["constraint1"],
            "non_goals": [],
            "decisions": [
                {
                    "id": "dec-001",
                    "summary": "test",
                    "decided_at": "2026-02-01T10:00:00Z",
                }
            ],
            "open_questions": [],
        }

        # Act
        contract = ProjectContract.model_validate(data)

        # Assert
        assert contract.goals == ["goal1"]
        assert isinstance(contract.decisions[0], DecisionRef)
        assert contract.decisions[0].id == "dec-001"
