"""Hive/Colony 投影 (Projections)

イベントストリームからHive/Colonyの現在状態を計算する投影機能。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..events import BaseEvent, EventType
from .projections import ColonyState, HiveState


@dataclass
class ColonyProjection:
    """Colonyの現在状態"""

    colony_id: str
    hive_id: str
    goal: str = ""
    state: ColonyState = ColonyState.PENDING
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    run_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HiveProjection:
    """Hiveの現在状態"""

    hive_id: str
    name: str = ""
    state: HiveState = HiveState.ACTIVE
    created_at: datetime | None = None
    closed_at: datetime | None = None
    colonies: dict[str, ColonyProjection] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class HiveAggregate:
    """Hive集約

    イベント列からHiveの現在状態を投影する。
    Colonyの管理も含む。
    """

    def __init__(self, hive_id: str):
        self.hive_id = hive_id
        self._projection = HiveProjection(hive_id=hive_id)

    @property
    def state(self) -> HiveState:
        """Hiveの状態"""
        return self._projection.state

    @property
    def name(self) -> str:
        """Hiveの名前"""
        return self._projection.name

    @property
    def colonies(self) -> dict[str, ColonyProjection]:
        """Colony一覧"""
        return self._projection.colonies

    @property
    def active_colonies(self) -> list[ColonyProjection]:
        """アクティブなColony一覧（PENDING または IN_PROGRESS）"""
        return [
            c
            for c in self._projection.colonies.values()
            if c.state in (ColonyState.PENDING, ColonyState.IN_PROGRESS)
        ]

    @property
    def projection(self) -> HiveProjection:
        """現在の投影を取得"""
        return self._projection

    def apply(self, event: BaseEvent) -> None:
        """イベントを適用して状態を更新

        Args:
            event: 適用するイベント
        """
        handler = self._handlers.get(event.type)
        if handler:
            handler(self, event)

    def _apply_hive_created(self, event: BaseEvent) -> None:
        """Hive作成イベントを適用"""
        self._projection.state = HiveState.ACTIVE
        self._projection.name = event.payload.get("name", "")
        self._projection.created_at = event.timestamp
        self._projection.metadata["description"] = event.payload.get("description")

    def _apply_hive_closed(self, event: BaseEvent) -> None:
        """Hive終了イベントを適用"""
        self._projection.state = HiveState.CLOSED
        self._projection.closed_at = event.timestamp

    def _apply_colony_created(self, event: BaseEvent) -> None:
        """Colony作成イベントを適用"""
        colony_id = event.payload.get("colony_id", "")
        if not colony_id:
            return

        colony = ColonyProjection(
            colony_id=colony_id,
            hive_id=self.hive_id,
            goal=event.payload.get("goal", ""),
            state=ColonyState.PENDING,
            created_at=event.timestamp,
        )
        colony.metadata["name"] = event.payload.get("name", "")
        self._projection.colonies[colony_id] = colony

    def _apply_colony_started(self, event: BaseEvent) -> None:
        """Colony開始イベントを適用"""
        colony_id = event.payload.get("colony_id", "")
        if colony_id not in self._projection.colonies:
            return

        colony = self._projection.colonies[colony_id]
        colony.state = ColonyState.IN_PROGRESS
        colony.started_at = event.timestamp

    def _apply_colony_completed(self, event: BaseEvent) -> None:
        """Colony完了イベントを適用"""
        colony_id = event.payload.get("colony_id", "")
        if colony_id not in self._projection.colonies:
            return

        colony = self._projection.colonies[colony_id]
        colony.state = ColonyState.COMPLETED
        colony.completed_at = event.timestamp

    def _apply_colony_failed(self, event: BaseEvent) -> None:
        """Colony失敗イベントを適用"""
        colony_id = event.payload.get("colony_id", "")
        if colony_id not in self._projection.colonies:
            return

        colony = self._projection.colonies[colony_id]
        colony.state = ColonyState.FAILED
        colony.error = event.payload.get("error", "")
        colony.completed_at = event.timestamp

    def _apply_colony_suspended(self, event: BaseEvent) -> None:
        """Colony一時停止イベントを適用"""
        colony_id = event.payload.get("colony_id", "")
        if colony_id not in self._projection.colonies:
            return

        colony = self._projection.colonies[colony_id]
        colony.state = ColonyState.SUSPENDED

    # イベントタイプからハンドラへのマッピング
    _handlers = {
        EventType.HIVE_CREATED: _apply_hive_created,
        EventType.HIVE_CLOSED: _apply_hive_closed,
        EventType.COLONY_CREATED: _apply_colony_created,
        EventType.COLONY_STARTED: _apply_colony_started,
        EventType.COLONY_COMPLETED: _apply_colony_completed,
        EventType.COLONY_FAILED: _apply_colony_failed,
        EventType.COLONY_SUSPENDED: _apply_colony_suspended,
    }


def build_hive_aggregate(hive_id: str, events: Iterable[BaseEvent]) -> HiveAggregate:
    """イベント列からHive集約を構築

    Args:
        hive_id: Hive ID
        events: イベント列

    Returns:
        構築されたHive集約
    """
    aggregate = HiveAggregate(hive_id)
    for event in events:
        aggregate.apply(event)
    return aggregate
