"""Colony進捗追跡

Colony配下のRun/Task完了時に Colony の進捗を自動更新する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from colonyforge.core.events import EventType

if TYPE_CHECKING:
    from colonyforge.core.events import BaseEvent


class ColonyProgressTracker:
    """Colony進捗を追跡

    Run開始/完了/失敗イベントを監視し、Colony全体の進捗状態を管理。
    """

    def __init__(self) -> None:
        """トラッカーを初期化"""
        # colony_id -> {"runs": {run_id: status, ...}, "status": "..."}
        self.colonies: dict[str, dict[str, Any]] = {}
        # run_id -> colony_id のマッピング
        self._run_to_colony: dict[str, str] = {}

    def apply(self, event: BaseEvent) -> None:
        """イベントを適用して状態を更新

        Args:
            event: 適用するイベント
        """
        if event.type == EventType.RUN_STARTED:
            self._handle_run_started(event)
        elif event.type == EventType.RUN_COMPLETED:
            self._handle_run_completed(event)
        elif event.type == EventType.RUN_FAILED:
            self._handle_run_failed(event)

    def _handle_run_started(self, event: BaseEvent) -> None:
        """Run開始を処理"""
        run_id = event.run_id
        colony_id = event.colony_id

        if run_id is None or colony_id is None:
            return

        # Colonyを初期化
        if colony_id not in self.colonies:
            self.colonies[colony_id] = {"runs": {}, "status": "running"}

        # Runを追加（初期状態: running）
        self.colonies[colony_id]["runs"][run_id] = "running"
        self._run_to_colony[run_id] = colony_id

    def _handle_run_completed(self, event: BaseEvent) -> None:
        """Run完了を処理"""
        run_id = event.run_id
        if run_id is None or run_id not in self._run_to_colony:
            return

        colony_id = self._run_to_colony[run_id]
        self.colonies[colony_id]["runs"][run_id] = "completed"
        self._update_colony_status(colony_id)

    def _handle_run_failed(self, event: BaseEvent) -> None:
        """Run失敗を処理"""
        run_id = event.run_id
        if run_id is None or run_id not in self._run_to_colony:
            return

        colony_id = self._run_to_colony[run_id]
        self.colonies[colony_id]["runs"][run_id] = "failed"
        self._update_colony_status(colony_id)

    def _update_colony_status(self, colony_id: str) -> None:
        """Colonyのステータスを更新"""
        if colony_id not in self.colonies:
            return

        runs = self.colonies[colony_id]["runs"]
        statuses = list(runs.values())

        # 失敗が1つでもあればfailed
        if "failed" in statuses:
            self.colonies[colony_id]["status"] = "failed"
        # 全て完了していればcompleted
        elif all(s == "completed" for s in statuses):
            self.colonies[colony_id]["status"] = "completed"
        # それ以外はrunning
        else:
            self.colonies[colony_id]["status"] = "running"

    def get_colony_status(self, colony_id: str) -> str:
        """Colonyのステータスを取得

        Args:
            colony_id: ColonyのID

        Returns:
            ステータス文字列（running, completed, failed）
        """
        if colony_id not in self.colonies:
            return "unknown"
        return self.colonies[colony_id]["status"]  # type: ignore[no-any-return]

    def should_emit_colony_event(self, event: BaseEvent) -> str | None:
        """イベント適用後にColonyイベントを発行すべきか判定

        Args:
            event: 適用するイベント

        Returns:
            発行すべきイベントタイプ（"colony.completed", "colony.failed"）
            またはNone
        """
        # 先にイベントを適用
        self.apply(event)

        run_id = event.run_id
        if run_id is None or run_id not in self._run_to_colony:
            return None

        colony_id = self._run_to_colony[run_id]
        status = self.get_colony_status(colony_id)

        if status == "completed":
            return "colony.completed"
        elif status == "failed":
            return "colony.failed"

        return None
