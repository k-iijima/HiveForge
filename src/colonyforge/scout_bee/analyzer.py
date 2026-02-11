"""テンプレート成功率分析 — TemplateAnalyzer

エピソードのテンプレート別集計を行い、成功率・所要時間等の
統計情報を算出する。
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from colonyforge.core.honeycomb.models import Episode, Outcome

from .models import TemplateStats


class TemplateAnalyzer:
    """テンプレート成功率分析

    エピソードをテンプレート別に集計し、
    成功率・平均所要時間などの統計を算出する。
    """

    def analyze(self, episodes: list[Episode]) -> dict[str, TemplateStats]:
        """テンプレート別統計を算出

        Args:
            episodes: 分析対象のエピソード一覧

        Returns:
            テンプレート名 → TemplateStats のマッピング
        """
        if not episodes:
            return {}

        # テンプレート別に集計
        groups: defaultdict[str, list[Episode]] = defaultdict(list)
        for ep in episodes:
            groups[ep.template_used].append(ep)

        stats: dict[str, TemplateStats] = {}
        for template_name, group_episodes in groups.items():
            total = len(group_episodes)
            success = sum(1 for e in group_episodes if e.outcome == Outcome.SUCCESS)
            durations = [e.duration_seconds for e in group_episodes if e.duration_seconds > 0]
            avg_duration = statistics.mean(durations) if durations else 0.0

            stats[template_name] = TemplateStats(
                template_name=template_name,
                total_count=total,
                success_count=success,
                success_rate=success / total if total > 0 else 0.0,
                avg_duration_seconds=avg_duration,
            )

        return stats

    def best_template(self, episodes: list[Episode]) -> str | None:
        """成功率が最も高いテンプレートを返す

        Args:
            episodes: 分析対象のエピソード一覧

        Returns:
            最適テンプレート名。エピソードなしの場合はNone。
        """
        stats = self.analyze(episodes)
        if not stats:
            return None

        return max(
            stats.values(),
            key=lambda s: (s.success_rate, -s.avg_duration_seconds),
        ).template_name
