"""Worker Bee データモデル

Worker Beeの状態管理に使用するEnum・データクラスを定義する。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkerState(StrEnum):
    """Worker Beeの状態"""

    IDLE = "idle"  # タスク待ち
    WORKING = "working"  # 作業中
    ERROR = "error"  # エラー状態


@dataclass
class WorkerContext:
    """Worker Beeのコンテキスト"""

    worker_id: str
    state: WorkerState = WorkerState.IDLE
    current_task_id: str | None = None
    current_run_id: str | None = None
    progress: int = 0
