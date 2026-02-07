"""Referee Bee: トーナメント選抜

候補スコアをランキングし、上位K件を選抜する。
"""

from __future__ import annotations

from .models import CandidateScore, ScoreWeights, SelectionResult


class Tournament:
    """トーナメント選抜ロジック

    CandidateScoreのリストを最終スコアでランキングし、
    上位K件を選抜する。
    """

    def __init__(self, k: int = 1, weights: ScoreWeights | None = None) -> None:
        self._k = k
        self._weights = weights

    def select(self, scores: list[CandidateScore]) -> SelectionResult:
        """スコアリストから上位K件を選抜

        Args:
            scores: 候補スコアのリスト

        Returns:
            SelectionResult
        """
        if not scores:
            return SelectionResult(
                selected_ids=[],
                rankings=[],
                reason="No candidates",
            )

        # スコア降順にソート
        ranked = sorted(
            scores,
            key=lambda s: s.final_score(self._weights),
            reverse=True,
        )

        if len(ranked) == 1:
            return SelectionResult(
                selected_ids=[ranked[0].candidate_id],
                rankings=ranked,
                reason="Single candidate — skip tournament",
            )

        # 上位K件を選抜
        selected = ranked[: self._k]
        selected_ids = [s.candidate_id for s in selected]

        top_score = selected[0].final_score(self._weights)
        return SelectionResult(
            selected_ids=selected_ids,
            rankings=ranked,
            reason=f"Top {self._k} selected (best score: {top_score:.4f})",
        )
