"""Scout Bee — 過去実績に基づく編成最適化

Honeycombの過去エピソードから類似タスクを検索し、
最適なColonyテンプレートをBeekeeperに推薦する。
"""

from __future__ import annotations

from hiveforge.core.honeycomb.models import Episode

from .analyzer import TemplateAnalyzer
from .matcher import EpisodeMatcher
from .models import OptimizationProposal, ScoutReport, ScoutVerdict

# Cold-start default template.
# When Honeycomb has insufficient data (< min_episodes) to make a
# data-driven recommendation, this safe-default template is returned.
# Intentional safe-side fallback — see AGENTS.md §3 (permitted case 1).
_DEFAULT_TEMPLATE = "balanced"


class ScoutBee:
    """Scout Bee（偵察蜂）

    1. 新タスクの特徴量で類似エピソードを検索
    2. テンプレート別の成功率を分析
    3. 最適テンプレートをBeekeeperに提案
    """

    def __init__(
        self,
        min_episodes: int = 5,
        top_k: int = 10,
        min_similarity: float = 0.3,
    ) -> None:
        """初期化

        Args:
            min_episodes: 推薦に必要な最低エピソード数
            top_k: 類似検索の最大取得数
            min_similarity: 類似度の最低閾値
        """
        self.min_episodes = min_episodes
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.matcher = EpisodeMatcher()
        self.analyzer = TemplateAnalyzer()

    def recommend(
        self,
        target_features: dict[str, float],
        episodes: list[Episode],
    ) -> ScoutReport:
        """テンプレート推薦を行う

        Args:
            target_features: 新タスクのSwarming特徴量
            episodes: Honeycombの全エピソード

        Returns:
            ScoutReport: 推薦レポート
        """
        # コールドスタート判定
        if len(episodes) < self.min_episodes:
            return ScoutReport(
                verdict=ScoutVerdict.COLD_START,
                recommended_template=_DEFAULT_TEMPLATE,
                similar_count=len(episodes),
            )

        # 類似エピソード検索
        similar = self.matcher.find_similar(
            target_features=target_features,
            episodes=episodes,
            top_k=self.top_k,
            min_similarity=self.min_similarity,
        )

        if not similar:
            return ScoutReport(
                verdict=ScoutVerdict.INSUFFICIENT_DATA,
                recommended_template=_DEFAULT_TEMPLATE,
                similar_count=0,
            )

        # 類似エピソードのテンプレート分析
        similar_episodes = [s.episode for s in similar]
        template_stats = self.analyzer.analyze(similar_episodes)
        best = self.analyzer.best_template(similar_episodes)
        recommended = best or _DEFAULT_TEMPLATE

        # 最適化提案を作成
        best_stats = template_stats.get(recommended)
        proposal = OptimizationProposal(
            template_name=recommended,
            success_rate=best_stats.success_rate if best_stats else 0.0,
            avg_duration_seconds=(best_stats.avg_duration_seconds if best_stats else 0.0),
            reason=self._build_reason(recommended, len(similar), best_stats),
            similar_episode_count=len(similar),
        )

        return ScoutReport(
            verdict=ScoutVerdict.RECOMMENDED,
            recommended_template=recommended,
            similar_count=len(similar),
            proposal=proposal,
            template_stats=template_stats,
        )

    @staticmethod
    def _build_reason(
        template: str,
        similar_count: int,
        stats: object | None,
    ) -> str:
        """推薦理由を生成"""
        if stats is None:
            return f"類似エピソード{similar_count}件に基づく推薦"

        from .models import TemplateStats

        if isinstance(stats, TemplateStats):
            rate_pct = int(stats.success_rate * 100)
            return f"類似タスク{similar_count}件中、{template}テンプレートの成功率{rate_pct}%"

        return f"類似エピソード{similar_count}件に基づく推薦"
