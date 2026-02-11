"""KPI Calculator — KPI算出

Honeycombに蓄積されたEpisodeデータからKPIを算出する。

基本KPI (5指標):
  Correctness, Repeatability, Lead Time, Incident Rate, Recurrence Rate

協調メトリクス:
  Rework Rate, Escalation Ratio, N-Proposal Yield,
  Cost Per Task (tokens), Collaboration Overhead

ゲート精度メトリクス:
  Guard Pass/Conditional/Fail Rate, Sentinel Detection/FalseAlarm Rate

参考:
  AgentBench (Liu et al., ICLR 2024) — 失敗分類・成功率
  Mixture-of-Agents (Wang et al., 2024) — 協調効率
  AgentVerse (Chen et al., 2023) — 動的構成評価
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from typing import Any

from .models import (
    CollaborationMetrics,
    Episode,
    EvaluationSummary,
    FailureClass,
    GateAccuracyMetrics,
    KPIScores,
    Outcome,
)
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

        成功/全体の比率を使用。Guard Bee検証結果との連携は
        将来的に一次合格率（first-pass yield）に拡張予定。
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
        """インシデント率: 失敗/Partial またはSentinel Hornet介入があったエピソードの比率

        インシデントの定義:
        - outcome が FAILURE または PARTIAL
        - sentinel_intervention_count > 0 (成功でもSentinel介入があればインシデント)

        いずれかに該当するエピソードが全体に占める割合を返す。
        失敗かつSentinel介入のエピソードは重複カウントしない。
        """
        if not episodes:
            return None

        incident_count = sum(
            1
            for e in episodes
            if e.outcome in (Outcome.FAILURE, Outcome.PARTIAL) or e.sentinel_intervention_count > 0
        )
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

    # ------------------------------------------------------------------
    # 協調品質メトリクス (Collaboration Metrics)
    # ------------------------------------------------------------------

    def calculate_collaboration(
        self,
        colony_id: str | None = None,
        *,
        guard_reject_count: int = 0,
        guard_total_count: int = 0,
        escalation_count: int = 0,
        decision_count: int = 0,
        referee_selected_count: int = 0,
        referee_candidate_count: int = 0,
    ) -> CollaborationMetrics:
        """協調品質メトリクスを算出

        Episode データと外部カウンタから協調品質を計算する。

        Args:
            colony_id: Colony ID（未指定時は全体）
            guard_reject_count: Guard Bee差戻し回数
            guard_total_count: Guard Bee検証総回数
            escalation_count: Queen Bee→Beekeeperエスカレーション回数
            decision_count: 全意思決定回数
            referee_selected_count: Referee Bee選抜候補数
            referee_candidate_count: Referee Bee検討候補総数

        Returns:
            CollaborationMetrics
        """
        episodes = self.store.replay_colony(colony_id) if colony_id else self.store.replay_all()

        return CollaborationMetrics(
            rework_rate=self._calc_rework_rate(guard_reject_count, guard_total_count),
            escalation_ratio=self._calc_escalation_ratio(escalation_count, decision_count),
            n_proposal_yield=self._calc_n_proposal_yield(
                referee_selected_count, referee_candidate_count
            ),
            cost_per_task_tokens=self._calc_cost_per_task(episodes),
            collaboration_overhead=self._calc_collaboration_overhead(episodes),
        )

    def _calc_rework_rate(self, reject_count: int, total_count: int) -> float | None:
        """再作業率: Guard Bee差戻し / 全検証"""
        if total_count == 0:
            return None
        return reject_count / total_count

    def _calc_escalation_ratio(self, escalation_count: int, decision_count: int) -> float | None:
        """エスカレーション率: Queen Bee→Beekeeper委譲 / 全意思決定"""
        if decision_count == 0:
            return None
        return escalation_count / decision_count

    def _calc_n_proposal_yield(self, selected: int, total: int) -> float | None:
        """N案歩留まり: 選抜数 / 候補総数"""
        if total == 0:
            return None
        return selected / total

    def _calc_cost_per_task(self, episodes: list[Episode]) -> float | None:
        """タスク当たり平均トークン消費"""
        if not episodes:
            return None
        tokens = [e.token_count for e in episodes if e.token_count > 0]
        if not tokens:
            return None
        return statistics.mean(tokens)

    def _calc_collaboration_overhead(self, episodes: list[Episode]) -> float | None:
        """協調オーバーヘッド: Sentinel介入 + 失敗 / 全エピソード

        失敗とSentinel介入が多いほどオーバーヘッドが高い。
        """
        if not episodes:
            return None
        overhead_count = sum(
            1 for e in episodes if e.outcome == Outcome.FAILURE or e.sentinel_intervention_count > 0
        )
        return overhead_count / len(episodes)

    # ------------------------------------------------------------------
    # ゲート精度メトリクス (Gate Accuracy Metrics)
    # ------------------------------------------------------------------

    def calculate_gate_accuracy(
        self,
        *,
        guard_pass_count: int = 0,
        guard_conditional_count: int = 0,
        guard_fail_count: int = 0,
        sentinel_alert_count: int = 0,
        sentinel_false_alarm_count: int = 0,
        total_monitoring_periods: int = 0,
    ) -> GateAccuracyMetrics:
        """ゲート精度メトリクスを算出

        外部から収集したGuard Bee/Sentinel Hornetのカウンタから算出。

        Args:
            guard_pass_count: Guard Bee PASS数
            guard_conditional_count: Guard Bee CONDITIONAL_PASS数
            guard_fail_count: Guard Bee FAIL数
            sentinel_alert_count: Sentinel alert発出数
            sentinel_false_alarm_count: Sentinel 誤検知数
            total_monitoring_periods: Sentinel監視した総イベント期間数

        Returns:
            GateAccuracyMetrics
        """
        guard_total = guard_pass_count + guard_conditional_count + guard_fail_count

        return GateAccuracyMetrics(
            guard_pass_rate=(guard_pass_count / guard_total if guard_total > 0 else None),
            guard_conditional_pass_rate=(
                guard_conditional_count / guard_total if guard_total > 0 else None
            ),
            guard_fail_rate=(guard_fail_count / guard_total if guard_total > 0 else None),
            sentinel_detection_rate=(
                sentinel_alert_count / total_monitoring_periods
                if total_monitoring_periods > 0
                else None
            ),
            sentinel_false_alarm_rate=(
                sentinel_false_alarm_count / sentinel_alert_count
                if sentinel_alert_count > 0
                else None
            ),
        )

    # ------------------------------------------------------------------
    # 包括的評価サマリー (EvaluationSummary)
    # ------------------------------------------------------------------

    def calculate_evaluation(
        self,
        colony_id: str | None = None,
        *,
        guard_pass_count: int = 0,
        guard_conditional_count: int = 0,
        guard_fail_count: int = 0,
        guard_reject_count: int = 0,
        guard_total_count: int = 0,
        escalation_count: int = 0,
        decision_count: int = 0,
        referee_selected_count: int = 0,
        referee_candidate_count: int = 0,
        sentinel_alert_count: int = 0,
        sentinel_false_alarm_count: int = 0,
        total_monitoring_periods: int = 0,
    ) -> EvaluationSummary:
        """包括的評価サマリーを算出

        基本KPI + 協調品質 + ゲート精度を統合した
        ダッシュボード用データを返す。

        Args:
            colony_id: Colony ID（未指定時は全体）
            guard_*: Guard Bee関連カウンタ
            escalation_count: エスカレーション回数
            decision_count: 意思決定回数
            referee_*: Referee Bee関連カウンタ
            sentinel_*: Sentinel Hornet関連カウンタ
            total_monitoring_periods: Sentinel監視期間数

        Returns:
            EvaluationSummary
        """
        episodes = self.store.replay_colony(colony_id) if colony_id else self.store.replay_all()

        # 基本KPI
        kpi = self.calculate_all(colony_id=colony_id)

        # 協調メトリクス
        collaboration = CollaborationMetrics(
            rework_rate=self._calc_rework_rate(guard_reject_count, guard_total_count),
            escalation_ratio=self._calc_escalation_ratio(escalation_count, decision_count),
            n_proposal_yield=self._calc_n_proposal_yield(
                referee_selected_count, referee_candidate_count
            ),
            cost_per_task_tokens=self._calc_cost_per_task(episodes),
            collaboration_overhead=self._calc_collaboration_overhead(episodes),
        )

        # ゲート精度
        gate_accuracy = self.calculate_gate_accuracy(
            guard_pass_count=guard_pass_count,
            guard_conditional_count=guard_conditional_count,
            guard_fail_count=guard_fail_count,
            sentinel_alert_count=sentinel_alert_count,
            sentinel_false_alarm_count=sentinel_false_alarm_count,
            total_monitoring_periods=total_monitoring_periods,
        )

        # 内訳
        outcome_counts = Counter(e.outcome for e in episodes)
        failure_counts = Counter(e.failure_class for e in episodes if e.failure_class)

        return EvaluationSummary(
            total_episodes=len(episodes),
            colony_count=len(self.store.list_colonies()),
            kpi=kpi,
            collaboration=collaboration,
            gate_accuracy=gate_accuracy,
            outcomes={k.value: v for k, v in outcome_counts.items()},
            failure_classes={k.value: v for k, v in failure_counts.items()},
        )
