"""RefereeComparer — Best-of-N Spec 比較（§5.7）.

複数の SpecDraft を4軸（testability, risk_coverage, clarity, completeness）で
ルールベース採点し、最高スコアの草案を選択して RefereeResult を返す。

重み: testability=0.3, risk_coverage=0.25, clarity=0.2, completeness=0.25
"""

from __future__ import annotations

from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    RefereeResult,
    SpecDraft,
    SpecScore,
)

# ---------------------------------------------------------------------------
# 加重平均の重み
# ---------------------------------------------------------------------------

_WEIGHT_TESTABILITY: float = 0.30
_WEIGHT_RISK_COVERAGE: float = 0.25
_WEIGHT_CLARITY: float = 0.20
_WEIGHT_COMPLETENESS: float = 0.25

# ---------------------------------------------------------------------------
# しきい値・飽和パラメータ
# ---------------------------------------------------------------------------

_MEASURABLE_SATURATE: int = 5
"""measurable 受入基準がこの数以上でテスト可能性 = 1.0."""

_HYPOTHESIS_SATURATE: int = 4
"""失敗仮説がこの数以上でリスクカバレッジ = 1.0."""

_CLARITY_CHARS: int = 100
"""説明文字数がこの数以上で clarity = 1.0."""


class RefereeComparer:
    """Referee Bee — 複数の SpecDraft を比較して最良を選択する.

    4軸のルールベーススコアを算出し、加重平均で総合スコアを計算、
    最高スコアの草案を選択する。
    """

    def compare(
        self,
        drafts: list[SpecDraft],
        *,
        draft_ids: list[str],
    ) -> RefereeResult:
        """SpecDraft リストを比較して RefereeResult を返す.

        Args:
            drafts: 比較する草案リスト
            draft_ids: 各草案に対応する ID リスト（同じ長さ）

        Returns:
            RefereeResult: 選択された草案 ID とスコア一覧

        Raises:
            ValueError: drafts が空、または draft_ids と長さが異なる場合
        """
        if not drafts:
            raise ValueError("drafts must not be empty")
        if len(drafts) != len(draft_ids):
            raise ValueError(
                f"drafts and draft_ids must have the same length "
                f"(got {len(drafts)} vs {len(draft_ids)})"
            )

        scores: list[SpecScore] = []
        for draft, draft_id in zip(drafts, draft_ids, strict=True):
            score = self._score_draft(draft, draft_id)
            scores.append(score)

        best = max(scores, key=lambda s: s.total)
        return RefereeResult(
            selected_draft_id=best.draft_id,
            scores=scores,
        )

    # ------------------------------------------------------------------
    # private — 個別草案の採点
    # ------------------------------------------------------------------

    def _score_draft(self, draft: SpecDraft, draft_id: str) -> SpecScore:
        """SpecDraft を4軸で採点し SpecScore を返す."""
        t = self._testability(draft)
        r = self._risk_coverage(draft)
        c = self._clarity(draft)
        comp = self._completeness(draft)

        total = (
            t * _WEIGHT_TESTABILITY
            + r * _WEIGHT_RISK_COVERAGE
            + c * _WEIGHT_CLARITY
            + comp * _WEIGHT_COMPLETENESS
        )

        return SpecScore(
            draft_id=draft_id,
            testability=round(t, 4),
            risk_coverage=round(r, 4),
            clarity=round(c, 4),
            completeness=round(comp, 4),
            total=round(total, 4),
        )

    # ------------------------------------------------------------------
    # private — 各軸のスコア算出
    # ------------------------------------------------------------------

    @staticmethod
    def _testability(draft: SpecDraft) -> float:
        """テスト可能性: measurable な受入基準の比率 + 件数の飽和."""
        criteria = draft.acceptance_criteria
        if not criteria:
            return 0.0
        measurable_count = sum(
            1 for c in criteria if isinstance(c, AcceptanceCriterion) and c.measurable
        )
        ratio = measurable_count / len(criteria)
        # 件数の飽和（多いほど高い、上限あり）
        volume = min(measurable_count / _MEASURABLE_SATURATE, 1.0)
        return (ratio + volume) / 2.0

    @staticmethod
    def _risk_coverage(draft: SpecDraft) -> float:
        """リスクカバレッジ: リスク緩和策の件数の飽和."""
        count = len(draft.risk_mitigations)
        return min(count / _HYPOTHESIS_SATURATE, 1.0)

    @staticmethod
    def _clarity(draft: SpecDraft) -> float:
        """明瞭性: goal 文字数の飽和."""
        goal_len = len(draft.goal)
        return min(goal_len / _CLARITY_CHARS, 1.0)

    @staticmethod
    def _completeness(draft: SpecDraft) -> float:
        """完全性: 各セクションの有無を加点.

        - acceptance_criteria に measurable あり: +0.3
        - constraints あり: +0.2
        - risk_mitigations あり: +0.3
        - non_goals あり: +0.2
        """
        score = 0.0
        if any(
            isinstance(c, AcceptanceCriterion) and c.measurable for c in draft.acceptance_criteria
        ):
            score += 0.3
        if draft.constraints:
            score += 0.2
        if draft.risk_mitigations:
            score += 0.3
        if draft.non_goals:
            score += 0.2
        return score
