"""Referee Bee: スコアリングエンジン

メトリクス辞書からCandidateScoreを計算する。
"""

from __future__ import annotations

from typing import Any

from .models import CandidateScore


class ScoringEngine:
    """5次元スコアリングエンジン

    メトリクス辞書からCandidateScoreを計算する。
    各指標の計算ロジック:
    - Correctness: tests_passed / tests_total
    - Robustness: 1.0 - (mutation_survived / mutation_total)
    - Consistency: diff_match_ratio
    - Security: max(0, 1.0 - lint_violations * 0.1) capped at 0
    - Latency: latency_ratio (1.0 = 基準同等)
    """

    def compute(self, candidate_id: str, metrics: dict[str, Any]) -> CandidateScore:
        """メトリクスから候補スコアを計算"""
        correctness = self._calc_correctness(metrics)
        robustness = self._calc_robustness(metrics)
        consistency = self._calc_consistency(metrics)
        security = self._calc_security(metrics)
        latency = self._calc_latency(metrics)

        return CandidateScore(
            candidate_id=candidate_id,
            correctness=correctness,
            robustness=robustness,
            consistency=consistency,
            security=security,
            latency=latency,
        )

    def _calc_correctness(self, m: dict[str, Any]) -> float:
        """テスト合格率"""
        total = int(m.get("tests_total", 0))
        if total == 0:
            return 0.0
        return float(m.get("tests_passed", 0)) / total

    def _calc_robustness(self, m: dict[str, Any]) -> float:
        """変異テスト耐性: 1.0 - (survived / total)"""
        total = int(m.get("mutation_total", 0))
        if total == 0:
            return 0.0
        survived = float(m.get("mutation_survived", 0))
        return max(0.0, 1.0 - survived / total)

    def _calc_consistency(self, m: dict[str, Any]) -> float:
        """差分一致率"""
        return float(m.get("diff_match_ratio", 0.0))

    def _calc_security(self, m: dict[str, Any]) -> float:
        """セキュリティスコア: 1.0 - violations * 0.1"""
        violations = int(m.get("lint_violations", 0))
        if violations == 0 and "lint_violations" not in m:
            return 0.0
        return max(0.0, 1.0 - violations * 0.1)

    def _calc_latency(self, m: dict[str, Any]) -> float:
        """レイテンシスコア"""
        return float(m.get("latency_ratio", 0.0))
