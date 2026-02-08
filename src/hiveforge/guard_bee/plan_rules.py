"""Guard Bee プラン検証ルール

タスク分解結果（TaskPlan）の妥当性を検証するルール。
L1: 構造的妥当性（循環依存、参照整合性、重複チェック）
L2: ゴールカバレッジ（具体性、独自性）
"""

from __future__ import annotations

from typing import Any

from ..queen_bee.planner import PlannedTask, TaskPlan
from .models import (
    Evidence,
    EvidenceType,
    RuleResult,
    VerificationLevel,
)
from .rules import VerificationRule


# ─── ヘルパー ────────────────────────────────────────────


def create_plan_evidence(plan: TaskPlan, original_goal: str) -> Evidence:
    """TaskPlanからGuard Bee用のEvidenceを生成する

    Args:
        plan: 検証対象のタスク分解計画
        original_goal: 分解前の元のゴール

    Returns:
        PLAN_DECOMPOSITION型のEvidence
    """
    tasks_data = [
        {
            "task_id": t.task_id,
            "goal": t.goal,
            "depends_on": list(t.depends_on),
        }
        for t in plan.tasks
    ]

    return Evidence(
        evidence_type=EvidenceType.PLAN_DECOMPOSITION,
        source="task_planner",
        content={
            "original_goal": original_goal,
            "task_count": len(plan.tasks),
            "tasks": tasks_data,
            "reasoning": plan.reasoning,
        },
    )


# ─── L1: 構造的妥当性 ───────────────────────────────────


class PlanStructureRule(VerificationRule):
    """L1: タスク分解の構造的妥当性を検証

    チェック項目:
    - PLAN_DECOMPOSITION証拠の存在
    - 循環依存がないこと
    - depends_onが既知のタスクIDを参照すること
    - ゴールが重複しないこと
    """

    def __init__(self) -> None:
        super().__init__(
            name="plan_structure",
            level=VerificationLevel.L1,
            description="タスク分解の構造的妥当性を検証",
            required_evidence=(EvidenceType.PLAN_DECOMPOSITION,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        plan_ev = self._find_evidence(evidence, EvidenceType.PLAN_DECOMPOSITION)
        if plan_ev is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="プラン証拠なし",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
            )

        tasks_data = plan_ev.content.get("tasks", [])
        task_count = len(tasks_data)

        # TaskPlanを再構築して検証
        try:
            planned_tasks = [
                PlannedTask(
                    task_id=t["task_id"],
                    goal=t["goal"],
                    depends_on=t.get("depends_on", []),
                )
                for t in tasks_data
            ]
            plan = TaskPlan(tasks=planned_tasks)
        except Exception as e:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message=f"プラン再構築エラー: {e}",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
            )

        # 不明な依存参照チェック
        known_ids = {t.task_id for t in plan.tasks}
        invalid_deps: list[str] = []
        for task in plan.tasks:
            for dep in task.depends_on:
                if dep not in known_ids:
                    invalid_deps.append(f"{task.task_id}→{dep}")

        if invalid_deps:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message=f"不明な依存参照: {', '.join(invalid_deps)}",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"task_count": task_count, "invalid_deps": invalid_deps},
            )

        # 循環依存チェック
        try:
            plan.execution_order()
        except ValueError:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="循環依存が検出されました",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"task_count": task_count},
            )

        # ゴール重複チェック
        goals = [t.goal for t in plan.tasks]
        if len(goals) != len(set(goals)):
            duplicated = [g for g in goals if goals.count(g) > 1]
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message=f"ゴールが重複しています: {set(duplicated)}",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"task_count": task_count, "duplicated_goals": list(set(duplicated))},
            )

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=True,
            message=f"構造検証OK: {task_count}タスク",
            evidence_type=EvidenceType.PLAN_DECOMPOSITION,
            details={"task_count": task_count},
        )


# ─── L2: ゴールカバレッジ ────────────────────────────────


class PlanGoalCoverageRule(VerificationRule):
    """L2: タスクゴールの品質を検証

    チェック項目:
    - 複数タスクが元ゴールの繰り返しでないこと
    - ゴールが十分に具体的であること（最低5文字）
    """

    MIN_GOAL_LENGTH = 5
    """ゴールの最低文字数"""

    def __init__(self) -> None:
        super().__init__(
            name="plan_goal_coverage",
            level=VerificationLevel.L2,
            description="タスクゴールの品質・カバレッジを検証",
            required_evidence=(EvidenceType.PLAN_DECOMPOSITION,),
        )

    def verify(self, evidence: list[Evidence], context: dict[str, Any]) -> RuleResult:
        plan_ev = self._find_evidence(evidence, EvidenceType.PLAN_DECOMPOSITION)
        if plan_ev is None:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message="プラン証拠なし",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
            )

        tasks_data = plan_ev.content.get("tasks", [])
        original_goal = plan_ev.content.get("original_goal", "")
        task_count = len(tasks_data)

        # 単一タスクの場合はスキップ（分解不要と判断された）
        if task_count <= 1:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=True,
                message="単一タスク（分解不要）",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"original_goal": original_goal},
            )

        goals = [t["goal"] for t in tasks_data]

        # 元ゴールの繰り返しチェック
        repeat_count = sum(1 for g in goals if original_goal in g)
        if repeat_count > task_count // 2:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message=f"タスクの過半数が元ゴールの繰り返しです（{repeat_count}/{task_count}）",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"original_goal": original_goal, "repeat_count": repeat_count},
            )

        # 具体性チェック（極端に短いゴール）
        short_goals = [g for g in goals if len(g) < self.MIN_GOAL_LENGTH]
        if short_goals:
            return RuleResult(
                rule_name=self.name,
                level=self.level,
                passed=False,
                message=f"具体性が不十分な短いゴールがあります: {short_goals}",
                evidence_type=EvidenceType.PLAN_DECOMPOSITION,
                details={"original_goal": original_goal, "short_goals": short_goals},
            )

        return RuleResult(
            rule_name=self.name,
            level=self.level,
            passed=True,
            message=f"ゴール品質OK: {task_count}タスク",
            evidence_type=EvidenceType.PLAN_DECOMPOSITION,
            details={"original_goal": original_goal},
        )
