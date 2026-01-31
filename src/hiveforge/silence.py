"""沈黙検出器 (Silence Detector)

長時間の無応答を検出してアラートを発行。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

from .core import get_settings, AkashicRecord
from .core.events import SilenceDetectedEvent


class SilenceDetector:
    """沈黙検出器

    ハートビートが一定時間途絶えた場合に沈黙を検出。
    VS Code拡張やダッシュボードにアラートを送信。
    """

    def __init__(
        self,
        ar: AkashicRecord,
        run_id: str,
        interval_seconds: int | None = None,
        on_silence: Callable[[str, datetime], Awaitable[None]] | None = None,
    ):
        """
        Args:
            ar: Akashic Record インスタンス
            run_id: 監視対象のRun ID
            interval_seconds: 沈黙判定の閾値（秒）
            on_silence: 沈黙検出時のコールバック
        """
        self.ar = ar
        self.run_id = run_id
        self.interval = interval_seconds or get_settings().governance.heartbeat_interval_seconds
        self.on_silence = on_silence
        self._last_activity: datetime | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def record_activity(self, timestamp: datetime | None = None) -> None:
        """アクティビティを記録"""
        self._last_activity = timestamp or datetime.now(timezone.utc)

    async def start(self) -> None:
        """検出器を開始"""
        self._running = True
        self._last_activity = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """検出器を停止"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self) -> None:
        """監視ループ"""
        threshold = timedelta(seconds=self.interval * 2)  # 2回分のハートビートを待つ

        while self._running:
            await asyncio.sleep(self.interval)

            if not self._running:
                break

            now = datetime.now(timezone.utc)

            if self._last_activity and (now - self._last_activity) > threshold:
                # 沈黙を検出
                await self._handle_silence(now)

    async def _handle_silence(self, detected_at: datetime) -> None:
        """沈黙を処理"""
        # イベントを記録
        event = SilenceDetectedEvent(
            run_id=self.run_id,
            actor="silence_detector",
            payload={
                "last_activity": self._last_activity.isoformat() if self._last_activity else None,
                "detected_at": detected_at.isoformat(),
                "threshold_seconds": self.interval * 2,
            },
        )
        self.ar.append(event, self.run_id)

        # コールバックを呼び出し
        if self.on_silence:
            await self.on_silence(self.run_id, detected_at)

        # 連続検出を防ぐためにリセット
        self._last_activity = detected_at


class HeartbeatManager:
    """ハートビートマネージャー

    複数のRunの沈黙検出を管理。
    """

    def __init__(self, ar: AkashicRecord):
        self.ar = ar
        self._detectors: dict[str, SilenceDetector] = {}
        self._on_silence_callbacks: list[Callable[[str, datetime], Awaitable[None]]] = []

    def add_silence_callback(self, callback: Callable[[str, datetime], Awaitable[None]]) -> None:
        """沈黙検出コールバックを追加"""
        self._on_silence_callbacks.append(callback)

    async def start_monitoring(self, run_id: str) -> None:
        """Runの監視を開始"""
        if run_id in self._detectors:
            return

        async def on_silence(rid: str, detected_at: datetime) -> None:
            for callback in self._on_silence_callbacks:
                await callback(rid, detected_at)

        detector = SilenceDetector(
            ar=self.ar,
            run_id=run_id,
            on_silence=on_silence,
        )
        self._detectors[run_id] = detector
        await detector.start()

    async def stop_monitoring(self, run_id: str) -> None:
        """Runの監視を停止"""
        if run_id in self._detectors:
            await self._detectors[run_id].stop()
            del self._detectors[run_id]

    def record_heartbeat(self, run_id: str, timestamp: datetime | None = None) -> None:
        """ハートビートを記録"""
        if run_id in self._detectors:
            self._detectors[run_id].record_activity(timestamp)

    async def stop_all(self) -> None:
        """全ての監視を停止"""
        for detector in self._detectors.values():
            await detector.stop()
        self._detectors.clear()
