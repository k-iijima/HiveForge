"""Worker Bee プロセス管理

Worker Beeをサブプロセスとして起動・監視・再起動する。
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ulid import ULID


class WorkerProcessState(StrEnum):
    """Worker プロセスの状態"""

    STARTING = "starting"  # 起動中
    RUNNING = "running"  # 稼働中
    STOPPING = "stopping"  # 停止中
    STOPPED = "stopped"  # 停止
    CRASHED = "crashed"  # クラッシュ
    RESTARTING = "restarting"  # 再起動中


@dataclass
class WorkerProcess:
    """Worker Bee プロセス"""

    process_id: str = field(default_factory=lambda: str(ULID()))
    worker_id: str = ""
    colony_id: str = ""
    state: WorkerProcessState = WorkerProcessState.STOPPED
    pid: int | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    restart_count: int = 0
    last_error: str | None = None
    max_restarts: int = 3

    def is_running(self) -> bool:
        """稼働中か"""
        return self.state in (
            WorkerProcessState.STARTING,
            WorkerProcessState.RUNNING,
        )

    def can_restart(self) -> bool:
        """再起動可能か"""
        return self.restart_count < self.max_restarts


@dataclass
class WorkerPoolConfig:
    """Worker プール設定"""

    min_workers: int = 1
    max_workers: int = 10
    auto_restart: bool = True
    max_restarts_per_worker: int = 3
    health_check_interval: float = 30.0
    startup_timeout: float = 10.0
    shutdown_timeout: float = 30.0


class WorkerProcessManager:
    """Worker Bee プロセス管理

    複数のWorker Beeプロセスを管理。
    - 起動・停止
    - ヘルスチェック
    - 自動再起動
    """

    def __init__(self, config: WorkerPoolConfig | None = None):
        self._config = config or WorkerPoolConfig()
        self._workers: dict[str, WorkerProcess] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._on_worker_started: Callable[[WorkerProcess], None] | None = None
        self._on_worker_stopped: Callable[[WorkerProcess], None] | None = None
        self._on_worker_crashed: Callable[[WorkerProcess], None] | None = None
        self._health_check_task: asyncio.Task | None = None
        self._running = False

    def set_callbacks(
        self,
        on_started: Callable[[WorkerProcess], None] | None = None,
        on_stopped: Callable[[WorkerProcess], None] | None = None,
        on_crashed: Callable[[WorkerProcess], None] | None = None,
    ) -> None:
        """コールバック設定"""
        self._on_worker_started = on_started
        self._on_worker_stopped = on_stopped
        self._on_worker_crashed = on_crashed

    async def start_worker(
        self,
        worker_id: str,
        colony_id: str,
        command: list[str] | None = None,
    ) -> WorkerProcess:
        """Worker プロセスを起動"""
        worker = WorkerProcess(
            worker_id=worker_id,
            colony_id=colony_id,
            state=WorkerProcessState.STARTING,
            started_at=datetime.now(),
        )
        self._workers[worker.process_id] = worker

        if command:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                worker.pid = process.pid
                self._processes[worker.process_id] = process
            except Exception as e:
                worker.state = WorkerProcessState.CRASHED
                worker.last_error = str(e)
                if self._on_worker_crashed:
                    self._on_worker_crashed(worker)
                return worker

        worker.state = WorkerProcessState.RUNNING
        if self._on_worker_started:
            self._on_worker_started(worker)

        return worker

    async def stop_worker(self, process_id: str, force: bool = False) -> bool:
        """Worker プロセスを停止"""
        worker = self._workers.get(process_id)
        if not worker:
            return False

        worker.state = WorkerProcessState.STOPPING

        process = self._processes.get(process_id)
        if process:
            if force:
                process.kill()
            else:
                process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self._config.shutdown_timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()

            del self._processes[process_id]

        worker.state = WorkerProcessState.STOPPED
        worker.stopped_at = datetime.now()

        if self._on_worker_stopped:
            self._on_worker_stopped(worker)

        return True

    async def restart_worker(
        self,
        process_id: str,
        command: list[str] | None = None,
    ) -> WorkerProcess | None:
        """Worker プロセスを再起動"""
        worker = self._workers.get(process_id)
        if not worker:
            return None

        if not worker.can_restart():
            return None

        # 停止
        await self.stop_worker(process_id, force=True)

        # 再起動
        worker.state = WorkerProcessState.RESTARTING
        worker.restart_count += 1

        new_worker = await self.start_worker(
            worker_id=worker.worker_id,
            colony_id=worker.colony_id,
            command=command,
        )

        # 古いプロセス情報を削除
        del self._workers[process_id]

        return new_worker

    def get_worker(self, process_id: str) -> WorkerProcess | None:
        """Worker プロセス取得"""
        return self._workers.get(process_id)

    def get_workers_by_colony(self, colony_id: str) -> list[WorkerProcess]:
        """Colony別のWorker一覧"""
        return [w for w in self._workers.values() if w.colony_id == colony_id]

    def get_running_workers(self) -> list[WorkerProcess]:
        """稼働中のWorker一覧"""
        return [w for w in self._workers.values() if w.is_running()]

    def get_all_workers(self) -> list[WorkerProcess]:
        """全Worker一覧"""
        return list(self._workers.values())

    async def check_health(self, process_id: str) -> bool:
        """ヘルスチェック"""
        worker = self._workers.get(process_id)
        if not worker:
            return False

        process = self._processes.get(process_id)
        if process and process.returncode is not None:
            # プロセス終了
            worker.state = WorkerProcessState.CRASHED
            worker.last_error = f"Process exited with code {process.returncode}"
            if self._on_worker_crashed:
                self._on_worker_crashed(worker)
            return False

        return worker.state == WorkerProcessState.RUNNING

    async def start_health_check_loop(self) -> None:
        """ヘルスチェックループ開始"""
        self._running = True
        while self._running:
            for process_id in list(self._workers.keys()):
                worker = self._workers.get(process_id)
                if not worker or not worker.is_running():
                    continue

                healthy = await self.check_health(process_id)
                if not healthy and self._config.auto_restart and worker.can_restart():
                    await self.restart_worker(process_id)

            await asyncio.sleep(self._config.health_check_interval)

    def stop_health_check_loop(self) -> None:
        """ヘルスチェックループ停止"""
        self._running = False

    async def shutdown_all(self, force: bool = False) -> None:
        """全Worker停止"""
        self.stop_health_check_loop()

        for process_id in list(self._workers.keys()):
            await self.stop_worker(process_id, force=force)

    def get_stats(self) -> dict[str, Any]:
        """統計情報"""
        workers = list(self._workers.values())
        return {
            "total": len(workers),
            "running": len([w for w in workers if w.is_running()]),
            "stopped": len([w for w in workers if w.state == WorkerProcessState.STOPPED]),
            "crashed": len([w for w in workers if w.state == WorkerProcessState.CRASHED]),
            "total_restarts": sum(w.restart_count for w in workers),
        }
