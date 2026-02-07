"""Guard Bee データモデル

品質検証のためのデータモデル。
Evidence-first原則: 意見ではなく証拠で判定する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Verdict(str, Enum):
    """検証判定結果

    3値判定:
    - PASS: 全検証項目をクリア
    - CONDITIONAL_PASS: 軽微な指摘あり（期限付き承認）
    - FAIL: 重大な問題あり（差戻し）
    """

    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"


class VerificationLevel(str, Enum):
    """検証レベル

    - L1: ルール検証（機械判定: lint, カバレッジ閾値, スキーマ準拠）
    - L2: 文脈検証（設計意図, リスク, 既存Decisionとの整合性）
    """

    L1 = "L1"
    L2 = "L2"


class EvidenceType(str, Enum):
    """証拠の種類"""

    DIFF = "diff"
    LINT_RESULT = "lint_result"
    TEST_RESULT = "test_result"
    TEST_COVERAGE = "test_coverage"
    TYPE_CHECK = "type_check"
    SECURITY_SCAN = "security_scan"
    CUSTOM = "custom"


class Evidence(BaseModel):
    """検証用の証拠データ

    Guard Beeが検証に使用する具体的な証拠。
    """

    model_config = ConfigDict(frozen=True)

    evidence_type: EvidenceType = Field(..., description="証拠の種類")
    source: str = Field(..., description="証拠の出所（ファイルパス、ツール名等）")
    content: dict[str, Any] = Field(default_factory=dict, description="証拠データ")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="証拠収集日時",
    )


class RuleResult(BaseModel):
    """個別検証ルールの結果"""

    model_config = ConfigDict(frozen=True)

    rule_name: str = Field(..., description="ルール名")
    level: VerificationLevel = Field(..., description="検証レベル")
    passed: bool = Field(..., description="合格したか")
    message: str = Field(default="", description="結果メッセージ")
    evidence_type: EvidenceType | None = Field(
        default=None, description="使用した証拠の種類"
    )
    details: dict[str, Any] = Field(default_factory=dict, description="詳細データ")


class GuardBeeReport(BaseModel):
    """Guard Bee検証レポート

    検証の最終判定と全ルール結果を保持する。
    Honeycombに記録され、KPI算出に使用される。
    """

    model_config = ConfigDict(frozen=True)

    colony_id: str = Field(..., description="検証対象Colony ID")
    task_id: str = Field(..., description="検証対象Task ID")
    run_id: str = Field(..., description="Run ID")
    verdict: Verdict = Field(..., description="最終判定")
    rule_results: tuple[RuleResult, ...] = Field(
        default=(), description="個別ルールの結果"
    )
    evidence_count: int = Field(default=0, ge=0, description="収集した証拠数")
    l1_passed: bool = Field(default=False, description="L1（ルール検証）合格")
    l2_passed: bool = Field(default=False, description="L2（文脈検証）合格")
    remand_reason: str | None = Field(
        default=None, description="差戻し理由（FAILの場合）"
    )
    improvement_instructions: list[str] = Field(
        default_factory=list, description="改善指示（FAIL/CONDITIONAL_PASSの場合）"
    )
    verified_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="検証日時",
    )

    def to_event_payload(self) -> dict[str, Any]:
        """ARイベント用ペイロードに変換"""
        return {
            "colony_id": self.colony_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "verdict": self.verdict.value,
            "l1_passed": self.l1_passed,
            "l2_passed": self.l2_passed,
            "evidence_count": self.evidence_count,
            "rules_total": len(self.rule_results),
            "rules_passed": sum(1 for r in self.rule_results if r.passed),
            "remand_reason": self.remand_reason,
            "improvement_instructions": self.improvement_instructions,
        }
