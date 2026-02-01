"""投影 (Projections)

イベントソーシングにおける投影（読み取りモデル）。
イベントを適用して現在の状態を再構築する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hiveforge.core.events import EventType

if TYPE_CHECKING:
    from hiveforge.core.events import BaseEvent


class RunColonyProjection:
    """Colony-Run紐付け投影

    RunStartedEventのcolony_idからColony → Run[]のマッピングを構築。
    """

    def __init__(self) -> None:
        """投影を初期化"""
        # colony_id -> [run_id, ...]
        self.colony_runs: dict[str, list[str]] = {}
        # colony_idがNoneのRun（v4互換）
        self.orphan_runs: list[str] = []

    def apply(self, event: BaseEvent) -> None:
        """イベントを適用して状態を更新

        Args:
            event: 適用するイベント
        """
        if event.type != EventType.RUN_STARTED:
            return

        run_id = event.run_id
        colony_id = event.colony_id

        if run_id is None:
            return

        if colony_id is None:
            # v4互換: colony_idなしは独立Run
            if run_id not in self.orphan_runs:
                self.orphan_runs.append(run_id)
        else:
            # ColonyにRunを紐付け
            if colony_id not in self.colony_runs:
                self.colony_runs[colony_id] = []
            if run_id not in self.colony_runs[colony_id]:
                self.colony_runs[colony_id].append(run_id)

    def get_runs_by_colony(self, colony_id: str) -> list[str]:
        """ColonyIDからRun一覧を取得

        Args:
            colony_id: ColonyのID

        Returns:
            Run IDのリスト（存在しない場合は空リスト）
        """
        return self.colony_runs.get(colony_id, [])
