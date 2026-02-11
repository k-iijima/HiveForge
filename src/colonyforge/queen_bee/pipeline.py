"""Queen Bee 実行パイプライン — ゲート統合

Plan → Validate → Approve → Execute → Report の各段階を
ARイベントとして記録し、問題を隠蔽しない実行フローを提供する。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from colonyforge.core.ar.storage import AkashicRecord
from colonyforge.core.events.base import BaseEvent, generate_event_id
from colonyforge.core.events.types import EventType
from colonyforge.core.models.action_class import TrustLevel
from colonyforge.guard_bee.models import GuardBeeReport, Verdict
from colonyforge.guard_bee.plan_rules import create_plan_evidence
from colonyforge.guard_bee.rules import RuleRegistry
from colonyforge.guard_bee.verifier import GuardBeeVerifier
from colonyforge.queen_bee.approval import (
    ApprovalDecision,
    PlanApprovalGate,
    PlanApprovalRequest,
)
from colonyforge.queen_bee.orchestrator import ColonyOrchestrator
from colonyforge.queen_bee.planner import TaskPlan
from colonyforge.queen_bee.result import ColonyResult, ColonyResultBuilder

logger = logging.getLogger(__name__)


# ─── パイプライン例外 ───────────────────────────────────


class PipelineError(Exception):
    """パイプライン実行エラーの基底"""


class PlanValidationFailedError(PipelineError):
    """Guard Bee検証失敗"""

    def __init__(self, report: GuardBeeReport) -> None:
        self.report = report
        reasons = report.remand_reason or "検証失敗"
        super().__init__(f"プラン検証失敗: {reasons}")


class ApprovalRequiredError(PipelineError):
    """承認が必要"""

    def __init__(self, approval_request: PlanApprovalRequest) -> None:
        self.approval_request = approval_request
        super().__init__(
            f"承認が必要です: {approval_request.action_class.value} "
            f"(trust_level={approval_request.trust_level.value})"
        )


# ─── ExecutionPipeline ──────────────────────────────────


class ExecutionPipeline:
    """ゲート統合型実行パイプライン

    各段階でARイベントを記録し、監査可能な実行フローを提供する。

    段階:
    1. Pipeline Started（開始記録）
    2. Fallback Check（フォールバック発動の記録）
    3. Plan Validation（Guard Bee検証）
    4. Approval Gate（承認判定）
    5. Execute（ColonyOrchestrator並列実行）
    6. Pipeline Completed（結果記録）
    """

    def __init__(
        self,
        ar: AkashicRecord,
        trust_level: TrustLevel = TrustLevel.PROPOSE_CONFIRM,
    ) -> None:
        self._ar = ar
        self._trust_level = trust_level
        self._approval_gate = PlanApprovalGate()
        self._orchestrator = ColonyOrchestrator()

    async def run(
        self,
        plan: TaskPlan,
        execute_fn: Callable[..., Any],
        colony_id: str,
        run_id: str,
        original_goal: str,
        approval_decision: ApprovalDecision | None = None,
        is_fallback: bool = False,
    ) -> ColonyResult:
        """パイプラインを実行する

        Args:
            plan: 実行するタスクプラン
            execute_fn: タスク実行関数
            colony_id: Colony ID
            run_id: Run ID
            original_goal: 元の目標
            approval_decision: 事前承認（None の場合は承認ゲートで判定）
            is_fallback: フォールバックプランか

        Returns:
            ColonyResult

        Raises:
            PlanValidationFailedError: Guard Bee検証失敗
            ApprovalRequiredError: 承認が必要
        """
        actor = f"pipeline-{colony_id}"

        # 1. Pipeline Started
        self._record_event(
            EventType.PIPELINE_STARTED,
            run_id=run_id,
            colony_id=colony_id,
            actor=actor,
            payload={
                "original_goal": original_goal,
                "task_count": len(plan.tasks),
                "is_fallback": is_fallback,
            },
        )

        # 2. フォールバック記録
        if is_fallback:
            self._record_event(
                EventType.PLAN_FALLBACK_ACTIVATED,
                run_id=run_id,
                colony_id=colony_id,
                actor=actor,
                payload={
                    "original_goal": original_goal,
                    "reasoning": plan.reasoning,
                    "task_count": len(plan.tasks),
                },
            )
            logger.error(
                "フォールバックプラン発動: goal=%s reasoning=%s",
                original_goal,
                plan.reasoning,
            )

        # 3. Guard Bee検証
        report = self._validate_plan(plan, original_goal, colony_id, run_id)
        if report.verdict == Verdict.FAIL:
            self._record_event(
                EventType.PLAN_VALIDATION_FAILED,
                run_id=run_id,
                colony_id=colony_id,
                actor=actor,
                payload={
                    "original_goal": original_goal,
                    "verdict": report.verdict.value,
                    "remand_reason": report.remand_reason,
                },
            )
            raise PlanValidationFailedError(report)

        # 4. 承認ゲート
        approval_request = self._approval_gate.check_approval(
            plan, self._trust_level, original_goal
        )
        if approval_request.requires_approval and (
            approval_decision is None or not approval_decision.approved
        ):
            self._record_event(
                EventType.PLAN_APPROVAL_REQUIRED,
                run_id=run_id,
                colony_id=colony_id,
                actor=actor,
                payload=approval_request.to_event_payload(),
            )
            raise ApprovalRequiredError(approval_request)

        # 5. 実行
        ctx = await self._orchestrator.execute_plan(
            plan=plan,
            execute_fn=execute_fn,
            original_goal=original_goal,
            run_id=run_id,
        )

        # 6. 結果集約
        result = ColonyResultBuilder.build(ctx, colony_id=colony_id)

        self._record_event(
            EventType.PIPELINE_COMPLETED,
            run_id=run_id,
            colony_id=colony_id,
            actor=actor,
            payload=result.to_event_data(),
        )

        return result

    def _validate_plan(
        self,
        plan: TaskPlan,
        original_goal: str,
        colony_id: str,
        run_id: str,
    ) -> GuardBeeReport:
        """Guard Beeでプランを検証する"""
        from colonyforge.guard_bee.plan_rules import (
            PlanGoalCoverageRule,
            PlanStructureRule,
        )

        registry = RuleRegistry()
        registry.register(PlanStructureRule())
        registry.register(PlanGoalCoverageRule())

        verifier = GuardBeeVerifier(ar=self._ar, rule_registry=registry)
        evidence = [create_plan_evidence(plan, original_goal)]

        return verifier.verify(
            colony_id=colony_id,
            task_id="plan-validation",
            run_id=run_id,
            evidence=evidence,
        )

    def _record_event(
        self,
        event_type: EventType,
        run_id: str,
        colony_id: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        """ARにイベントを記録する"""
        event = BaseEvent(
            id=generate_event_id(),
            type=event_type,
            run_id=run_id,
            colony_id=colony_id,
            actor=actor,
            payload=payload,
        )
        self._ar.append(event, run_id)
