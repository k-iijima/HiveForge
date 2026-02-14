"""Episode Recorder — エピソード記録

Run/Taskの完了時にEpisodeを作成してHoneycombに記録する。
ARイベントからEpisodeを自動生成する。
"""

from __future__ import annotations

import logging
from typing import Any

from ...core import AkashicRecord, generate_event_id
from ...core.events import EventType
from .models import Episode, FailureClass, KPIScores, Outcome
from .store import HoneycombStore

logger = logging.getLogger(__name__)


class EpisodeRecorder:
    """エピソードレコーダー

    Run/Taskの完了時にEpisodeを自動記録する。
    ARイベントを分析してEpisodeを構築する。
    """

    def __init__(self, honeycomb_store: HoneycombStore, ar: AkashicRecord) -> None:
        self.store = honeycomb_store
        self.ar = ar

    def record_run_episode(
        self,
        run_id: str,
        colony_id: str,
        goal: str = "",
        template_used: str = "balanced",
        task_features: dict[str, float] | None = None,
        parent_episode_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Episode:
        """Run完了時にEpisodeを記録

        ARからそのRunのイベントを取得し、結果を分析して
        Episodeを構築・永続化する。

        Args:
            run_id: Run ID
            colony_id: Colony ID
            goal: タスクの目標
            template_used: 使用したColonyテンプレート
            task_features: タスク特徴量
            parent_episode_ids: 前回試行のEpisode ID
            metadata: 追加メタデータ

        Returns:
            記録されたEpisode
        """
        events = list(self.ar.replay(run_id))

        # 結果の判定
        outcome = self._determine_outcome(events)

        # 所要時間の計算
        duration = self._calculate_duration(events)

        # 失敗分類
        failure_class = self._classify_failure(events) if outcome != Outcome.SUCCESS else None

        # KPIスコアの算出
        kpi_scores = self._calculate_kpi_scores(events, duration)

        # Sentinel Hornet 介入回数
        sentinel_count = self._count_sentinel_interventions(events)

        episode = Episode(
            episode_id=generate_event_id(),
            run_id=run_id,
            colony_id=colony_id,
            template_used=template_used,
            task_features=task_features or {},
            outcome=outcome,
            duration_seconds=duration,
            token_count=self._count_tokens(events),
            failure_class=failure_class,
            sentinel_intervention_count=sentinel_count,
            kpi_scores=kpi_scores,
            parent_episode_ids=parent_episode_ids or [],
            goal=goal,
            metadata=dict((metadata or {}).items()),
        )

        self.store.append(episode)
        logger.info(
            f"Episode記録完了: {episode.episode_id} (run={run_id}, outcome={outcome.value})"
        )
        return episode

    def _determine_outcome(self, events: list[Any]) -> Outcome:
        """ARイベントから結果を判定"""
        event_types = {e.type for e in events}

        if EventType.RUN_COMPLETED in event_types:
            # 全タスク成功
            return Outcome.SUCCESS
        elif EventType.RUN_FAILED in event_types:
            # RunFailed イベントがある場合
            # タスクの成功/失敗比率で partial を判定
            task_completed = sum(1 for e in events if e.type == EventType.TASK_COMPLETED)
            task_failed = sum(1 for e in events if e.type == EventType.TASK_FAILED)
            if task_completed > 0 and task_failed > 0:
                return Outcome.PARTIAL
            return Outcome.FAILURE
        elif EventType.RUN_ABORTED in event_types:
            return Outcome.FAILURE
        else:
            # イベントが不完全な場合
            return Outcome.PARTIAL

    def _calculate_duration(self, events: list[Any]) -> float:
        """イベントのタイムスタンプから所要時間を計算"""
        if len(events) < 2:
            return 0.0

        # イベントのタイムスタンプ（created_at）が利用可能な場合
        timestamps = []
        for e in events:
            if hasattr(e, "created_at") and e.created_at:
                timestamps.append(e.created_at)

        if len(timestamps) >= 2:
            # ISO形式のタイムスタンプから秒数を計算
            from datetime import datetime

            try:
                first = datetime.fromisoformat(timestamps[0])
                last = datetime.fromisoformat(timestamps[-1])
                return max(0.0, (last - first).total_seconds())
            except (ValueError, TypeError):
                pass

        return 0.0

    def _classify_failure(self, events: list[Any]) -> FailureClass | None:
        """イベントから失敗分類を推定"""
        for event in reversed(events):
            if event.type in (EventType.TASK_FAILED, EventType.RUN_FAILED):
                reason = event.payload.get("reason", "").lower()

                if "timeout" in reason or "time" in reason:
                    return FailureClass.TIMEOUT
                elif "connect" in reason or "network" in reason or "environment" in reason:
                    return FailureClass.ENVIRONMENT_ERROR
                elif "integration" in reason or "merge" in reason:
                    return FailureClass.INTEGRATION_ERROR
                elif "compile" in reason or "syntax" in reason or "import" in reason:
                    return FailureClass.IMPLEMENTATION_ERROR
                elif "design" in reason or "architecture" in reason:
                    return FailureClass.DESIGN_ERROR
                elif "spec" in reason or "requirement" in reason or "ambiguous" in reason:
                    return FailureClass.SPECIFICATION_ERROR

                # デフォルトはIMPLEMENTATION_ERROR
                return FailureClass.IMPLEMENTATION_ERROR

        return None

    def _count_tokens(self, events: list[Any]) -> int:
        """イベントからトークン使用量を算出"""
        total = 0
        for event in events:
            if event.type == EventType.WORKER_COMPLETED:
                total += event.payload.get("token_count", 0)
            elif event.type == EventType.WORKER_PROGRESS:
                total += event.payload.get("tokens_used", 0)
        return total

    # Sentinel Hornet 介入としてカウントするイベントタイプ
    _SENTINEL_INTERVENTION_TYPES = frozenset(
        {
            EventType.SENTINEL_ALERT_RAISED,
            EventType.SENTINEL_ROLLBACK,
            EventType.SENTINEL_QUARANTINE,
            EventType.SENTINEL_KPI_DEGRADATION,
            EventType.EMERGENCY_STOP,
        }
    )

    def _count_sentinel_interventions(self, events: list[Any]) -> int:
        """イベントからSentinel Hornet介入回数を算出

        定期レポート（SENTINEL_REPORT）は介入ではないためカウントしない。
        カウント対象:
        - SENTINEL_ALERT_RAISED: アラート発行
        - SENTINEL_ROLLBACK: ロールバック実行
        - SENTINEL_QUARANTINE: 隔離実行
        - SENTINEL_KPI_DEGRADATION: KPI劣化検出
        - EMERGENCY_STOP: 緊急停止
        """
        return sum(1 for e in events if e.type in self._SENTINEL_INTERVENTION_TYPES)

    def _calculate_kpi_scores(self, events: list[Any], duration: float) -> KPIScores:
        """イベントからKPIスコアを算出

        単一Episodeレベルで算出可能なKPIを計算:
        - correctness: outcome に基づく (SUCCESS=1.0, PARTIAL=0.5, FAILURE=0.0)
        - lead_time_seconds: 所要時間
        - incident_rate: 失敗系outcome なら 1.0, 成功なら 0.0

        repeatability / recurrence_rate は複数Episode集約が必要なため
        KPICalculator に委ねる。
        """
        outcome = self._determine_outcome(events)

        # correctness: outcome に基づく一次判定
        correctness_map = {
            Outcome.SUCCESS: 1.0,
            Outcome.PARTIAL: 0.5,
            Outcome.FAILURE: 0.0,
        }
        correctness = float(correctness_map.get(outcome, 0.0))

        # incident_rate: 失敗/部分失敗を 1.0, 成功を 0.0
        incident_rate = 0.0 if outcome == Outcome.SUCCESS else 1.0

        return KPIScores(
            correctness=correctness,
            lead_time_seconds=duration if duration > 0 else None,
            incident_rate=incident_rate,
        )
