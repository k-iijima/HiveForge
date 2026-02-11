"""Lineage - 因果リンク（親イベント）の自動解決

GitHub Issue #16: P1-15: Lineage 親イベント自動設定

イベント作成時に自動的に親イベントを設定する機能を提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from colonyforge.core.events import BaseEvent, EventType

if TYPE_CHECKING:
    from collections.abc import Sequence


class LineageResolver:
    """因果リンク（親イベント）の自動解決

    イベントの種類に応じて、自動的に親イベントを設定する。

    親設定ルール:
        - run.started: 親なし
        - task.created: run.started
        - task.assigned/progressed/completed/failed: task.created
        - run.completed: 全ての task.completed
    """

    def resolve_parents(
        self,
        event: BaseEvent,
        existing_events: Sequence[BaseEvent],
    ) -> list[str]:
        """イベントの親を解決する

        Args:
            event: 親を解決するイベント
            existing_events: 既存のイベントリスト（検索対象）

        Returns:
            親イベントIDのリスト
        """
        # 明示的に親が指定されている場合はそれを使う
        if event.parents:
            return list(event.parents)

        event_type = event.type

        # run.started は親なし
        if event_type == EventType.RUN_STARTED:
            return []

        # run.completed の親は全ての task.completed
        if event_type == EventType.RUN_COMPLETED:
            return self._find_all_task_completed(event.run_id, existing_events)

        # task.created の親は run.started
        if event_type == EventType.TASK_CREATED:
            return self._find_run_started(event.run_id, existing_events)

        # task.assigned/progressed/completed/failed の親は task.created
        if event_type in (
            EventType.TASK_ASSIGNED,
            EventType.TASK_PROGRESSED,
            EventType.TASK_COMPLETED,
            EventType.TASK_FAILED,
        ):
            return self._find_task_created(event.run_id, event.task_id, existing_events)

        # その他のイベントは親なし
        return []

    def _find_run_started(
        self,
        run_id: str | None,
        existing_events: Sequence[BaseEvent],
    ) -> list[str]:
        """run.started イベントを検索"""
        if run_id is None:
            return []

        for event in existing_events:
            if event.type == EventType.RUN_STARTED and event.run_id == run_id:
                return [event.id]
        return []

    def _find_task_created(
        self,
        run_id: str | None,
        task_id: str | None,
        existing_events: Sequence[BaseEvent],
    ) -> list[str]:
        """task.created イベントを検索"""
        if run_id is None or task_id is None:
            return []

        for event in existing_events:
            if (
                event.type == EventType.TASK_CREATED
                and event.run_id == run_id
                and event.task_id == task_id
            ):
                return [event.id]
        return []

    def _find_all_task_completed(
        self,
        run_id: str | None,
        existing_events: Sequence[BaseEvent],
    ) -> list[str]:
        """全ての task.completed イベントを検索"""
        if run_id is None:
            return []

        parents = []
        for event in existing_events:
            if event.type == EventType.TASK_COMPLETED and event.run_id == run_id:
                parents.append(event.id)
        return parents
