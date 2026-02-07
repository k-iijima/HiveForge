"""KPI Calculator — KPI算出

Honeycombに蓄積されたEpisodeデータからKPIを算出する。
5つのKPI: Correctness, Repeatability, Lead Time, Incident Rate, Recurrence Rate
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from typing import Any

from .models import Episode, FailureClass, KPIScores, Outcome
from .store import HoneycombStore

logger = logging.getLogger(__name__)


class KPICalculator:
    """KPI算出エンジン

    Honeycombのエピソードデータから5つのKPIを計算する。
    Colony単位、テンプレート単位での集計も可能。
    """

    def __init__(self, store: HoneycombStore) -> None:
        self.store = store

    def calculate_all(
        self,
        colony_id: str | None = None,
    ) -> KPIScores:
        """全KPIを統合スコアとして算出

        Args:
            colony_id: 指定時はそのColonyのみ集計。
                       未指定時は全体を集計。

        Returns:
            KPIScores with calculated values
        """
        episodes = self.store.replay_colony(colony_id) if colony_id else self.store.replay_all()

        if not episodes:
            return KPIScores()

        return KPIScores(
            correctness=self._calc_correctness(episodes),
            repeatability=self._calc_repeatability(episodes),
            lead_time_seconds=self._calc_lead_time(episodes),
            incident_rate=self._calc_incident_rate(episodes),
            recurrence_rate=self._calc_recurrence_rate(episodes),
        )

    def calculate_summary(self, colony_id: str | None = None) -> dict[str, Any]:
        """KPIサマリーをdict形式で取得"""
        episodes = self.store.replay_colony(colony_id) if colony_id else self.store.replay_all()

        if not episodes:
            return {
                "total_episodes": 0,
                "kpi": KPIScores().model_dump(),
            }

        scores = KPIScores(
            correctness=self._calc_correctness(episodes),
            repeatability=self._calc_repeatability(episodes),
            lead_time_seconds=self._calc_lead_time(episodes),
            incident_rate=self._calc_incident_rate(episodes),
            recurrence_rate=self._calc_recurrence_rate(episodes),
        )

        # 結果内訳
        outcome_counts = Counter(e.outcome for e in episodes)
        failure_counts = Counter(e.failure_class for e in episodes if e.failure_class)

        return {
            "total_episodes": len(episodes),
            "outcomes": {k.value: v for k, v in outcome_counts.items()},
            "failure_classes": {k.value: v for k, v in failure_counts.items()},
            "kpi": scores.model_dump(),
        }

    def _calc_correctness(self, episodes: list[Episode]) -> float | None:
        """正確性: 成功率（一次合格率）

        Guard Beeが未実装のため、現時点では成功/全体の比率を使用。
        """
        if not episodes:
            return None

        success_count = sum(1 for e in episodes if e.outcome == Outcome.SUCCESS)
        return success_count / len(episodes)

    def _calc_repeatability(self, episodes: list[Episode]) -> float | None:
        """再現性: 同一テンプレート使用時の成功率分散

        テンプレートごとの成功率を計算し、その標準偏差を返す。
        テンプレートが1種のみの場合は0.0（完全に再現可能）。
        """
        if len(episodes) < 2:
            return None

        # テンプレート別成功率を計算
        template_results: defaultdict[str, list[int]] = defaultdict(list)
        for e in episodes:
            template_results[e.template_used].append(1 if e.outcome == Outcome.SUCCESS else 0)

        success_rates = []
        for results in template_results.values():
            if len(results) >= 2:
                success_rates.append(sum(results) / len(results))

        if len(success_rates) < 2:
            return 0.0

        return statistics.stdev(success_rates)

    def _calc_lead_time(self, episodes: list[Episode]) -> float | None:
        """リードタイム: 平均所要時間（秒）"""
        durations = [e.duration_seconds for e in episodes if e.duration_seconds > 0]
        if not durations:
            return None
        return statistics.mean(durations)

    def _calc_incident_rate(self, episodes: list[Episode]) -> float | None:
        """インシデント率: 失敗またはPartialの比率

        Sentinel Hornet介入の直接計測は未実装のため、
        現時点では失敗系エピソードの比率で代替。
        """
        if not episodes:
            return None

        incident_count = sum(1 for e in episodes if e.outcome in (Outcome.FAILURE, Outcome.PARTIAL))
        return incident_count / len(episodes)

    def _calc_recurrence_rate(self, episodes: list[Episode]) -> float | None:
        """再発率: 同一FailureClassの再発頻度

        各FailureClassについて、初発後に同じ分類で失敗が再発する率。
        """
        if not episodes:
            return None

        # FailureClass別にエピソードを時系列で収集
        failure_timeline: defaultdict[FailureClass, list[Episode]] = defaultdict(list)
        for e in episodes:
            if e.failure_class:
                failure_timeline[e.failure_class].append(e)

        if not failure_timeline:
            return 0.0

        # 各FailureClassについて再発数を計算
        total_failures = 0
        total_recurrences = 0
        for failure_episodes in failure_timeline.values():
            count = len(failure_episodes)
            total_failures += count
            if count > 1:
                total_recurrences += count - 1  # 初発を除いた再発数

        if total_failures == 0:
            return 0.0

        return total_recurrences / total_failures
