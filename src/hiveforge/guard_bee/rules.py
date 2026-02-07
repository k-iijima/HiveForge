"""Guard Bee 検証ルール定義フレームワーク

検証ルールを定義・登録・実行するためのフレームワーク。
L1（ルール検証）とL2（文脈検証）の2層構造。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .models import Evidence, EvidenceType, RuleResult, VerificationLevel

logger = logging.getLogger(__name__)


class VerificationRule(ABC):
    """検証ルールの基底クラス

    全ての検証ルールはこのクラスを継承する。
    """

    def __init__(
        self,
        name: str,
        level: VerificationLevel,
        description: str = "",
        required_evidence: tuple[EvidenceType, ...] = (),
    ) -> None:
        self.name = name
        self.level = level
        self.description = description
        self.required_evidence = required_evidence

    @abstractmethod
    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        """検証を実行

        Args:
            evidence: 収集された証拠リスト
            context: 追加コンテキスト

        Returns:
            検証結果
        """
        ...

    def _find_evidence(
        self, evidence: list[Evidence], evidence_type: EvidenceType
    ) -> Evidence | None:
        """指定タイプの証拠を検索"""
        for e in evidence:
            if e.evidence_type == evidence_type:
                return e
        return None


# =============================================================================
# L1 組み込みルール
# =============================================================================


class LintCleanRule(VerificationRule):
    """L1: Lint結果が警告0であること"""

    def __init__(self) -> None:
        super().__init__(
            name="lint_clean",
            level=VerificationLevel.L1,
            description="Lint結果にエラー・警告がないこと",
            required_evidence=(EvidenceType.LINT_RESULT,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        lint = self._find_evidence(evidence, EvidenceType.LINT_RESULT)
        if lint is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="Lint結果の証拠がありません",
                evidence_type=EvidenceType.LINT_RESULT,
            )

        errors = lint.content.get("errors", 0)
        warnings = lint.content.get("warnings", 0)
        passed = errors == 0 and warnings == 0

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=passed,
            message=f"errors={errors}, warnings={warnings}" if not passed else "Clean",
            evidence_type=EvidenceType.LINT_RESULT,
            details={"errors": errors, "warnings": warnings},
        )


class AllTestsPassRule(VerificationRule):
    """L1: 全テストがパスしていること"""

    def __init__(self) -> None:
        super().__init__(
            name="tests_pass",
            level=VerificationLevel.L1,
            description="全テストがパスしていること",
            required_evidence=(EvidenceType.TEST_RESULT,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        test = self._find_evidence(evidence, EvidenceType.TEST_RESULT)
        if test is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="テスト結果の証拠がありません",
                evidence_type=EvidenceType.TEST_RESULT,
            )

        total = test.content.get("total", 0)
        passed_count = test.content.get("passed", 0)
        failed = test.content.get("failed", 0)
        passed = failed == 0 and total > 0

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=passed,
            message=f"{passed_count}/{total} passed, {failed} failed"
            if not passed
            else f"{passed_count}/{total} passed",
            evidence_type=EvidenceType.TEST_RESULT,
            details={"total": total, "passed": passed_count, "failed": failed},
        )


class CoverageThresholdRule(VerificationRule):
    """L1: テストカバレッジが閾値以上であること"""

    def __init__(self, threshold: float = 80.0) -> None:
        super().__init__(
            name="coverage_threshold",
            level=VerificationLevel.L1,
            description=f"テストカバレッジが{threshold}%以上であること",
            required_evidence=(EvidenceType.TEST_COVERAGE,),
        )
        self.threshold = threshold

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        coverage = self._find_evidence(evidence, EvidenceType.TEST_COVERAGE)
        if coverage is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="カバレッジ結果の証拠がありません",
                evidence_type=EvidenceType.TEST_COVERAGE,
            )

        coverage_pct = coverage.content.get("coverage_percent", 0.0)
        passed = coverage_pct >= self.threshold

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=passed,
            message=f"Coverage {coverage_pct:.1f}% (threshold: {self.threshold}%)",
            evidence_type=EvidenceType.TEST_COVERAGE,
            details={"coverage_percent": coverage_pct, "threshold": self.threshold},
        )


class DiffExistsRule(VerificationRule):
    """L1: 変更差分（diff）が存在すること"""

    def __init__(self) -> None:
        super().__init__(
            name="diff_exists",
            level=VerificationLevel.L1,
            description="成果物に変更差分があること",
            required_evidence=(EvidenceType.DIFF,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        diff = self._find_evidence(evidence, EvidenceType.DIFF)
        if diff is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="差分の証拠がありません",
                evidence_type=EvidenceType.DIFF,
            )

        files_changed = diff.content.get("files_changed", 0)
        passed = files_changed > 0

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=passed,
            message=f"{files_changed} files changed" if passed else "No changes detected",
            evidence_type=EvidenceType.DIFF,
            details={"files_changed": files_changed},
        )


class TypeCheckRule(VerificationRule):
    """L1: 型チェックがパスしていること"""

    def __init__(self) -> None:
        super().__init__(
            name="type_check",
            level=VerificationLevel.L1,
            description="型チェック（mypy等）がパスしていること",
            required_evidence=(EvidenceType.TYPE_CHECK,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        tc = self._find_evidence(evidence, EvidenceType.TYPE_CHECK)
        if tc is None:
            # 型チェックはオプション - 証拠なしでもPASS
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=True,
                message="型チェック結果なし（スキップ）",
                evidence_type=EvidenceType.TYPE_CHECK,
            )

        errors = tc.content.get("errors", 0)
        passed = errors == 0

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=passed,
            message=f"Type errors: {errors}" if not passed else "Clean",
            evidence_type=EvidenceType.TYPE_CHECK,
            details={"errors": errors},
        )


# =============================================================================
# ルールレジストリ
# =============================================================================


class RuleRegistry:
    """検証ルールのレジストリ

    L1/L2のルールを登録し、レベル別に取得する。
    """

    def __init__(self) -> None:
        self._rules: list[VerificationRule] = []

    def register(self, rule: VerificationRule) -> None:
        """ルールを登録"""
        self._rules.append(rule)

    def get_rules(self, level: VerificationLevel | None = None) -> list[VerificationRule]:
        """指定レベルのルール一覧を取得（Noneで全ルール）"""
        if level is None:
            return list(self._rules)
        return [r for r in self._rules if r.level == level]

    def get_rule_names(self) -> list[str]:
        """登録済みルール名一覧"""
        return [r.name for r in self._rules]

    @classmethod
    def create_default(cls, coverage_threshold: float = 80.0) -> "RuleRegistry":
        """デフォルトのL1ルールセットを構築"""
        registry = cls()
        registry.register(DiffExistsRule())
        registry.register(LintCleanRule())
        registry.register(AllTestsPassRule())
        registry.register(CoverageThresholdRule(threshold=coverage_threshold))
        registry.register(TypeCheckRule())
        return registry
