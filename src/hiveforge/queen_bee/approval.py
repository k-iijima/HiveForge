"""Queen Bee 承認フロー — タスク分解計画の承認ゲート

ActionClass × TrustLevel に基づいて、タスク分解計画の
承認要否を判定し、承認リクエストを生成する。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hiveforge.core.models.action_class import (
    ActionClass,
    TrustLevel,
    requires_confirmation,
)
from hiveforge.queen_bee.planner import TaskPlan

logger = logging.getLogger(__name__)


# ─── ゴール分類用キーワード ─────────────────────────────

_READ_ONLY_PATTERNS = re.compile(
    r"分析|調査|確認|レビュー|読み|検索|参照|一覧|閲覧|監視|チェック",
)

_IRREVERSIBLE_PATTERNS = re.compile(
    r"デプロイ|deploy|本番|production|マイグレーション|migration"
    r"|削除.*データ|公開|publish|リリース|release|送信|メール",
)


# ─── Pydantic モデル ────────────────────────────────────


class PlanApprovalRequest(BaseModel):
    """タスク分解計画の承認リクエスト"""

    model_config = ConfigDict(strict=True, frozen=True)

    requires_approval: bool = Field(..., description="承認が必要か")
    action_class: ActionClass = Field(..., description="プランのリスク分類")
    trust_level: TrustLevel = Field(..., description="現在のTrustLevel")
    original_goal: str = Field(..., description="元のゴール")
    task_count: int = Field(..., description="タスク数")
    reasoning: str = Field(default="", description="分解の理由")
    task_goals: list[str] = Field(default_factory=list, description="各タスクのゴール一覧")

    def to_event_payload(self) -> dict[str, Any]:
        """イベントペイロードに変換"""
        return {
            "requires_approval": self.requires_approval,
            "action_class": self.action_class.value,
            "trust_level": self.trust_level.value,
            "original_goal": self.original_goal,
            "task_count": self.task_count,
            "reasoning": self.reasoning,
            "task_goals": list(self.task_goals),
        }


class ApprovalDecision(BaseModel):
    """承認の判定結果"""

    model_config = ConfigDict(strict=True, frozen=True)

    approved: bool = Field(..., description="承認されたか")
    reason: str = Field(default="", description="判定理由")


# ─── PlanApprovalGate ───────────────────────────────────


class PlanApprovalGate:
    """タスク分解計画の承認ゲート

    プラン内の各タスクゴールをキーワードベースで分類し、
    ActionClass × TrustLevel で承認要否を判定する。
    """

    def classify_plan(self, plan: TaskPlan) -> ActionClass:
        """プラン全体のActionClassを決定する

        各タスクゴールをキーワードベースで分類し、
        最もリスクの高いActionClassを採用する。

        Args:
            plan: タスク分解計画

        Returns:
            プラン全体のActionClass
        """
        classes = [self._classify_goal(t.goal) for t in plan.tasks]

        # 最もリスクが高いものを採用
        if ActionClass.IRREVERSIBLE in classes:
            return ActionClass.IRREVERSIBLE
        if ActionClass.REVERSIBLE in classes:
            return ActionClass.REVERSIBLE
        return ActionClass.READ_ONLY

    def check_approval(
        self,
        plan: TaskPlan,
        trust_level: TrustLevel,
        original_goal: str,
    ) -> PlanApprovalRequest:
        """プランの承認要否を判定する

        Args:
            plan: タスク分解計画
            trust_level: 現在のTrustLevel
            original_goal: 元のゴール

        Returns:
            PlanApprovalRequest（承認要否・リスク分類等）
        """
        action_class = self.classify_plan(plan)
        needs_approval = requires_confirmation(trust_level, action_class)

        return PlanApprovalRequest(
            requires_approval=needs_approval,
            action_class=action_class,
            trust_level=trust_level,
            original_goal=original_goal,
            task_count=len(plan.tasks),
            reasoning=plan.reasoning,
            task_goals=[t.goal for t in plan.tasks],
        )

    @staticmethod
    def _classify_goal(goal: str) -> ActionClass:
        """個別ゴールのActionClassをキーワードベースで分類"""
        if _IRREVERSIBLE_PATTERNS.search(goal):
            return ActionClass.IRREVERSIBLE
        if _READ_ONLY_PATTERNS.search(goal):
            return ActionClass.READ_ONLY
        return ActionClass.REVERSIBLE
