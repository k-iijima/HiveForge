"""Colony スケジューラー

複数Colonyの優先度制御とリソース配分を管理する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ColonyPriority(str, Enum):
    """Colony優先度"""

    CRITICAL = "critical"  # 最優先
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"  # 最低優先


# 優先度の数値マッピング（大きいほど優先）
PRIORITY_WEIGHT = {
    ColonyPriority.CRITICAL: 100,
    ColonyPriority.HIGH: 75,
    ColonyPriority.NORMAL: 50,
    ColonyPriority.LOW: 25,
    ColonyPriority.BACKGROUND: 10,
}


@dataclass
class ColonyConfig:
    """Colony設定"""

    colony_id: str
    priority: ColonyPriority = ColonyPriority.NORMAL
    max_workers: int = 5
    min_workers: int = 1
    enabled: bool = True


@dataclass
class ResourceAllocation:
    """リソース配分結果"""

    colony_id: str
    allocated_workers: int
    priority: ColonyPriority


@dataclass
class ColonyScheduler:
    """Colonyスケジューラー

    複数Colonyの優先度に基づいてリソースを配分する。
    """

    total_workers: int = 10
    _colonies: dict[str, ColonyConfig] = field(default_factory=dict)

    def register_colony(
        self,
        colony_id: str,
        priority: ColonyPriority = ColonyPriority.NORMAL,
        max_workers: int = 5,
        min_workers: int = 1,
    ) -> None:
        """Colonyを登録"""
        self._colonies[colony_id] = ColonyConfig(
            colony_id=colony_id,
            priority=priority,
            max_workers=max_workers,
            min_workers=min_workers,
        )

    def unregister_colony(self, colony_id: str) -> None:
        """Colonyを登録解除"""
        if colony_id in self._colonies:
            del self._colonies[colony_id]

    def set_priority(self, colony_id: str, priority: ColonyPriority) -> bool:
        """Colonyの優先度を変更"""
        if colony_id not in self._colonies:
            return False
        self._colonies[colony_id].priority = priority
        return True

    def get_colony(self, colony_id: str) -> ColonyConfig | None:
        """Colony設定を取得"""
        return self._colonies.get(colony_id)

    def get_active_colonies(self) -> list[ColonyConfig]:
        """有効なColony一覧を取得"""
        return [c for c in self._colonies.values() if c.enabled]

    def enable_colony(self, colony_id: str) -> bool:
        """Colonyを有効化"""
        if colony_id not in self._colonies:
            return False
        self._colonies[colony_id].enabled = True
        return True

    def disable_colony(self, colony_id: str) -> bool:
        """Colonyを無効化"""
        if colony_id not in self._colonies:
            return False
        self._colonies[colony_id].enabled = False
        return True

    def allocate_workers(self) -> list[ResourceAllocation]:
        """優先度に基づいてWorkerを配分

        Returns:
            各Colonyへの配分結果
        """
        active = self.get_active_colonies()
        if not active:
            return []

        # 優先度でソート（高い順）
        sorted_colonies = sorted(
            active,
            key=lambda c: PRIORITY_WEIGHT[c.priority],
            reverse=True,
        )

        allocations: list[ResourceAllocation] = []
        remaining = self.total_workers

        # まず最小Workerを確保
        for colony in sorted_colonies:
            allocated = min(colony.min_workers, remaining)
            if allocated > 0:
                allocations.append(
                    ResourceAllocation(
                        colony_id=colony.colony_id,
                        allocated_workers=allocated,
                        priority=colony.priority,
                    )
                )
                remaining -= allocated

        # 残りを優先度に応じて配分
        if remaining > 0:
            total_weight = sum(PRIORITY_WEIGHT[c.priority] for c in sorted_colonies)
            for i, colony in enumerate(sorted_colonies):
                if remaining <= 0:
                    break

                # 優先度に応じた追加配分
                weight_ratio = PRIORITY_WEIGHT[colony.priority] / total_weight
                additional = int(remaining * weight_ratio)

                # max_workersを超えないように
                current = next((a for a in allocations if a.colony_id == colony.colony_id), None)
                current_allocated = current.allocated_workers if current else 0
                can_add = colony.max_workers - current_allocated
                additional = min(additional, can_add)

                if additional > 0 and current:
                    current.allocated_workers += additional

        return allocations

    def get_execution_order(self) -> list[str]:
        """実行順序を取得（優先度順）"""
        active = self.get_active_colonies()
        sorted_colonies = sorted(
            active,
            key=lambda c: PRIORITY_WEIGHT[c.priority],
            reverse=True,
        )
        return [c.colony_id for c in sorted_colonies]

    def should_preempt(self, running_colony_id: str, waiting_colony_id: str) -> bool:
        """プリエンプション判定

        待機中のColonyが実行中のColonyより優先度が高い場合True
        """
        running = self._colonies.get(running_colony_id)
        waiting = self._colonies.get(waiting_colony_id)

        if not running or not waiting:
            return False

        return PRIORITY_WEIGHT[waiting.priority] > PRIORITY_WEIGHT[running.priority]
