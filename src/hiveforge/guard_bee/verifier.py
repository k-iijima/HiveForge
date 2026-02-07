"""Guard Bee 検証エンジン

成果物を受け取り、L1・L2の検証を実行し、
GuardBeeReportを生成する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..core import AkashicRecord, generate_event_id
from ..core.events import BaseEvent, EventType
from .models import (
    Evidence,
    GuardBeeReport,
    RuleResult,
    Verdict,
    VerificationLevel,
)
from .rules import RuleRegistry

logger = logging.getLogger(__name__)


class GuardBeeVerifier:
    """Guard Bee検証エンジン

    成果物に対してL1（ルール検証）→ L2（文脈検証）の
    2層検証を実行し、最終判定を下す。
    """

    def __init__(
        self,
        ar: AkashicRecord,
        rule_registry: RuleRegistry | None = None,
    ) -> None:
        self._ar = ar
        self._registry = rule_registry or RuleRegistry.create_default()

    def verify(
        self,
        colony_id: str,
        task_id: str,
        run_id: str,
        evidence: list[Evidence],
        context: dict[str, Any] | None = None,
    ) -> GuardBeeReport:
        """検証を実行しレポートを生成

        手順:
        1. 検証要求イベントをARに記録
        2. L1ルールを順番に実行
        3. L2ルールを順番に実行（L1全合格の場合のみ）
        4. 最終判定（Verdict）を決定
        5. 判定イベントをARに記録

        Args:
            colony_id: Colony ID
            task_id: Task ID
            run_id: Run ID
            evidence: 収集された証拠リスト
            context: 追加コンテキスト

        Returns:
            検証レポート
        """
        ctx = context or {}
        actor = f"guard-{colony_id}"

        # 検証要求イベント
        self._ar.append(
            BaseEvent(
                type=EventType.GUARD_VERIFICATION_REQUESTED,
                run_id=run_id,
                colony_id=colony_id,
                task_id=task_id,
                payload={
                    "colony_id": colony_id,
                    "task_id": task_id,
                    "evidence_count": len(evidence),
                },
                actor=actor,
            ),
            run_id=run_id,
        )

        # L1検証
        l1_rules = self._registry.get_rules(VerificationLevel.L1)
        l1_results = [rule.verify(evidence, ctx) for rule in l1_rules]
        l1_passed = all(r.passed for r in l1_results)

        # L2検証（L1全合格の場合のみ）
        l2_results: list[RuleResult] = []
        l2_passed = True
        if l1_passed:
            l2_rules = self._registry.get_rules(VerificationLevel.L2)
            l2_results = [rule.verify(evidence, ctx) for rule in l2_rules]
            l2_passed = all(r.passed for r in l2_results) if l2_results else True

        # 全ルール結果
        all_results = tuple(l1_results + l2_results)

        # 最終判定
        verdict, remand_reason, improvements = self._determine_verdict(
            l1_passed, l2_passed, all_results
        )

        report = GuardBeeReport(
            colony_id=colony_id,
            task_id=task_id,
            run_id=run_id,
            verdict=verdict,
            rule_results=all_results,
            evidence_count=len(evidence),
            l1_passed=l1_passed,
            l2_passed=l2_passed,
            remand_reason=remand_reason,
            improvement_instructions=improvements,
        )

        # 判定イベント
        event_type = self._verdict_to_event_type(verdict)
        self._ar.append(
            BaseEvent(
                type=event_type,
                run_id=run_id,
                colony_id=colony_id,
                task_id=task_id,
                payload=report.to_event_payload(),
                actor=actor,
            ),
            run_id=run_id,
        )

        logger.info(
            f"Guard Bee検証完了: {verdict.value} "
            f"(colony={colony_id}, task={task_id}, "
            f"L1={'OK' if l1_passed else 'NG'}, L2={'OK' if l2_passed else 'NG'})"
        )

        return report

    def _determine_verdict(
        self,
        l1_passed: bool,
        l2_passed: bool,
        results: tuple[RuleResult, ...],
    ) -> tuple[Verdict, str | None, list[str]]:
        """最終判定を決定

        Returns:
            (verdict, remand_reason, improvement_instructions)
        """
        failed_rules = [r for r in results if not r.passed]

        if not failed_rules:
            return Verdict.PASS, None, []

        # L1不合格 → FAIL
        l1_failed = [r for r in failed_rules if r.level == VerificationLevel.L1]
        if l1_failed:
            reasons = [f"{r.rule_name}: {r.message}" for r in l1_failed]
            remand = f"L1検証失敗: {', '.join(r.rule_name for r in l1_failed)}"
            return Verdict.FAIL, remand, reasons

        # L2のみ不合格 → CONDITIONAL_PASS
        l2_failed = [r for r in failed_rules if r.level == VerificationLevel.L2]
        reasons = [f"{r.rule_name}: {r.message}" for r in l2_failed]
        remand = f"L2検証に軽微な指摘: {', '.join(r.rule_name for r in l2_failed)}"
        return Verdict.CONDITIONAL_PASS, remand, reasons

    @staticmethod
    def _verdict_to_event_type(verdict: Verdict) -> EventType:
        """VerdictからEventTypeへの変換"""
        mapping = {
            Verdict.PASS: EventType.GUARD_PASSED,
            Verdict.CONDITIONAL_PASS: EventType.GUARD_CONDITIONAL_PASSED,
            Verdict.FAIL: EventType.GUARD_FAILED,
        }
        return mapping[verdict]
