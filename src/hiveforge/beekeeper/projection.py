"""Beekeeper状態の投影

イベントからBeekeeperの状態を再構築する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.events import BaseEvent, EventType
from .session import SessionState


@dataclass
class BeekeeperProjection:
    """Beekeeperの状態投影

    イベントから構築されるBeekeeperの現在状態。
    """

    session_id: str = ""
    hive_id: str | None = None
    state: SessionState = SessionState.IDLE
    active_colonies: list[str] = field(default_factory=list)
    pending_instructions: list[str] = field(default_factory=list)
    completed_instructions: int = 0
    failed_instructions: int = 0
    last_activity: datetime | None = None
    escalations_received: int = 0

    def apply_event(self, event: BaseEvent) -> None:
        """イベントを適用"""
        self.last_activity = event.timestamp

        if event.type == EventType.HIVE_CREATED:
            # hive_idはdataまたはpayloadから取得
            self.hive_id = event.payload.get("hive_id") or event.colony_id
            self.state = SessionState.ACTIVE

        elif event.type == EventType.COLONY_CREATED:
            if event.colony_id and event.colony_id not in self.active_colonies:
                self.active_colonies.append(event.colony_id)

        elif event.type == EventType.REQUIREMENT_CREATED:
            # ユーザーからの要求 = 指示
            if event.id:
                self.pending_instructions.append(event.id)

        elif event.type == EventType.REQUIREMENT_APPROVED:
            # 指示完了
            if event.id and event.id in self.pending_instructions:
                self.pending_instructions.remove(event.id)
                self.completed_instructions += 1

        elif event.type == EventType.REQUIREMENT_REJECTED:
            # 指示失敗
            if event.id and event.id in self.pending_instructions:
                self.pending_instructions.remove(event.id)
                self.failed_instructions += 1

        elif event.type == EventType.EMERGENCY_STOP:
            self.state = SessionState.SUSPENDED


def build_beekeeper_projection(events: list[BaseEvent]) -> BeekeeperProjection:
    """イベントからBeekeeperProjectionを構築

    Args:
        events: イベントリスト

    Returns:
        構築されたBeekeeperProjection
    """
    projection = BeekeeperProjection()
    for event in events:
        projection.apply_event(event)
    return projection


@dataclass
class HiveOverview:
    """Hive全体の概要"""

    hive_id: str
    name: str = ""
    colony_count: int = 0
    active_run_count: int = 0
    total_task_count: int = 0
    completed_task_count: int = 0
    pending_requirements: int = 0
    status: str = "active"


def build_hive_overview(events: list[BaseEvent]) -> HiveOverview | None:
    """イベントからHive概要を構築

    Args:
        events: イベントリスト

    Returns:
        HiveOverview or None
    """
    if not events:
        return None

    hive_id = ""
    name = ""
    colonies: set[str] = set()
    active_runs: set[str] = set()
    tasks: set[str] = set()
    completed_tasks: set[str] = set()
    pending_reqs: set[str] = set()
    status = "active"

    for event in events:
        if event.type == EventType.HIVE_CREATED:
            hive_id = event.payload.get("hive_id", "") or event.colony_id or ""
            name = event.payload.get("name", "")

        elif event.type == EventType.COLONY_CREATED:
            if event.colony_id:
                colonies.add(event.colony_id)

        elif event.type == EventType.RUN_STARTED:
            if event.run_id:
                active_runs.add(event.run_id)

        elif event.type == EventType.RUN_COMPLETED:
            if event.run_id:
                active_runs.discard(event.run_id)

        elif event.type == EventType.TASK_CREATED:
            if event.task_id:
                tasks.add(event.task_id)

        elif event.type == EventType.TASK_COMPLETED:
            if event.task_id:
                completed_tasks.add(event.task_id)

        elif event.type == EventType.REQUIREMENT_CREATED:
            if event.id:
                pending_reqs.add(event.id)

        elif event.type in (
            EventType.REQUIREMENT_APPROVED,
            EventType.REQUIREMENT_REJECTED,
        ):
            if event.id:
                pending_reqs.discard(event.id)

        elif event.type == EventType.EMERGENCY_STOP:
            status = "stopped"

    if not hive_id:
        return None

    return HiveOverview(
        hive_id=hive_id,
        name=name,
        colony_count=len(colonies),
        active_run_count=len(active_runs),
        total_task_count=len(tasks),
        completed_task_count=len(completed_tasks),
        pending_requirements=len(pending_reqs),
        status=status,
    )
