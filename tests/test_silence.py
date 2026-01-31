"""沈黙検出器 (Silence Detector) のテスト"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from hiveforge.silence import SilenceDetector, HeartbeatManager
from hiveforge.core.events import SilenceDetectedEvent


class TestSilenceDetector:
    """SilenceDetectorのテスト"""

    def test_record_activity_updates_last_activity(self, temp_vault):
        """record_activityで最終アクティビティ時刻が更新される"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=10)

        # Act
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        detector.record_activity(timestamp)

        # Assert
        assert detector._last_activity == timestamp

    def test_record_activity_without_timestamp_uses_now(self, temp_vault):
        """タイムスタンプなしでrecord_activityすると現在時刻が使われる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=10)

        # Act
        before = datetime.now(timezone.utc)
        detector.record_activity()
        after = datetime.now(timezone.utc)

        # Assert
        assert detector._last_activity is not None
        assert before <= detector._last_activity <= after

    @pytest.mark.asyncio
    async def test_start_and_stop(self, temp_vault):
        """start/stopで検出器が正しく開始・停止する"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=1)

        # Act: 開始
        await detector.start()
        assert detector._running is True
        assert detector._task is not None
        assert detector._last_activity is not None

        # Act: 停止
        await detector.stop()
        assert detector._running is False

    @pytest.mark.asyncio
    async def test_silence_detection_triggers_callback(self, temp_vault):
        """沈黙が検出されるとコールバックが呼ばれる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)

        callback_called = asyncio.Event()
        callback_args = {}

        async def on_silence(run_id: str, detected_at: datetime) -> None:
            callback_args["run_id"] = run_id
            callback_args["detected_at"] = detected_at
            callback_called.set()

        # 非常に短いインターバルで検出器を作成
        detector = SilenceDetector(
            ar=ar,
            run_id="run-001",
            interval_seconds=1,  # 1秒インターバル
            on_silence=on_silence,
        )

        # 過去のアクティビティを設定（沈黙状態を作る）
        detector._last_activity = datetime.now(timezone.utc) - timedelta(seconds=10)

        # Act: 開始
        await detector.start()

        try:
            # コールバックが呼ばれるのを待つ（最大3秒）
            await asyncio.wait_for(callback_called.wait(), timeout=3.0)

            # Assert
            assert callback_args["run_id"] == "run-001"
            assert callback_args["detected_at"] is not None
        finally:
            await detector.stop()

    @pytest.mark.asyncio
    async def test_silence_detection_creates_event(self, temp_vault):
        """沈黙検出時にイベントが記録される"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)

        detector = SilenceDetector(
            ar=ar,
            run_id="run-001",
            interval_seconds=1,
        )

        # 過去のアクティビティを設定
        detector._last_activity = datetime.now(timezone.utc) - timedelta(seconds=10)

        # Act: 沈黙を処理
        detected_at = datetime.now(timezone.utc)
        await detector._handle_silence(detected_at)

        # Assert: イベントが記録されている
        events = list(ar.replay("run-001"))
        assert len(events) == 1
        assert events[0].type.value == "system.silence_detected"

    @pytest.mark.asyncio
    async def test_monitor_loop_respects_running_flag(self, temp_vault):
        """監視ループは_runningフラグを尊重する"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=1)

        # Act: 開始してすぐ停止
        await detector.start()
        await asyncio.sleep(0.1)  # 少し待つ
        await detector.stop()

        # Assert: 正常に終了している
        assert detector._running is False

    @pytest.mark.asyncio
    async def test_stop_without_task(self, temp_vault):
        """タスクがない状態でstopしてもエラーにならない"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=10)

        # taskがNoneの状態
        assert detector._task is None

        # Act & Assert: エラーなし
        await detector.stop()

    @pytest.mark.asyncio
    async def test_monitor_loop_breaks_when_stopped_during_sleep(self, temp_vault):
        """sleep中に停止フラグが変わった場合にループを抜ける"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=1)

        # Act: 開始
        await detector.start()

        # 少し待ってから停止（ループの途中で止まるようにする）
        await asyncio.sleep(0.5)
        detector._running = False  # 直接フラグを変更

        # ループが終了するのを待つ
        await asyncio.sleep(1.5)

        # Assert: タスクは完了しているはず
        assert detector._running is False

    @pytest.mark.asyncio
    async def test_no_silence_with_recent_activity(self, temp_vault):
        """最近のアクティビティがあれば沈黙は検出されない"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)

        callback_called = False

        async def on_silence(run_id: str, detected_at: datetime) -> None:
            nonlocal callback_called
            callback_called = True

        detector = SilenceDetector(
            ar=ar,
            run_id="run-001",
            interval_seconds=1,
            on_silence=on_silence,
        )

        # Act: 開始して、アクティビティを継続的に記録
        await detector.start()

        for _ in range(3):
            await asyncio.sleep(0.5)
            detector.record_activity()  # アクティビティを記録し続ける

        await detector.stop()

        # Assert: 沈黙は検出されない
        assert callback_called is False


class TestHeartbeatManager:
    """HeartbeatManagerのテスト"""

    def test_add_silence_callback(self, temp_vault):
        """コールバックを追加できる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        async def callback(run_id: str, detected_at: datetime) -> None:
            pass

        # Act
        manager.add_silence_callback(callback)

        # Assert
        assert len(manager._on_silence_callbacks) == 1

    @pytest.mark.asyncio
    async def test_start_and_stop_monitoring(self, temp_vault):
        """Runの監視を開始・停止できる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        # Act: 監視開始
        await manager.start_monitoring("run-001")
        assert "run-001" in manager._detectors

        # Act: 同じRunの監視を再度開始しても無視される
        await manager.start_monitoring("run-001")
        assert len(manager._detectors) == 1

        # Act: 監視停止
        await manager.stop_monitoring("run-001")
        assert "run-001" not in manager._detectors

    @pytest.mark.asyncio
    async def test_stop_monitoring_nonexistent_run(self, temp_vault):
        """存在しないRunの監視停止はエラーにならない"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        # Act & Assert: エラーなし
        await manager.stop_monitoring("nonexistent-run")

    def test_record_heartbeat(self, temp_vault):
        """ハートビートを記録できる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        # 検出器を直接追加（start_monitoringは非同期なので）
        detector = SilenceDetector(ar=ar, run_id="run-001", interval_seconds=10)
        manager._detectors["run-001"] = detector

        # Act
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        manager.record_heartbeat("run-001", timestamp)

        # Assert
        assert detector._last_activity == timestamp

    def test_record_heartbeat_nonexistent_run(self, temp_vault):
        """存在しないRunへのハートビートは無視される"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        # Act & Assert: エラーなし
        manager.record_heartbeat("nonexistent-run")

    @pytest.mark.asyncio
    async def test_stop_all(self, temp_vault):
        """全ての監視を停止できる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        await manager.start_monitoring("run-001")
        await manager.start_monitoring("run-002")
        assert len(manager._detectors) == 2

        # Act
        await manager.stop_all()

        # Assert
        assert len(manager._detectors) == 0

    @pytest.mark.asyncio
    async def test_silence_callback_is_called_for_all_registered(self, temp_vault):
        """沈黙検出時に登録されたすべてのコールバックが呼ばれる"""
        # Arrange
        from hiveforge.core import AkashicRecord

        ar = AkashicRecord(temp_vault)
        manager = HeartbeatManager(ar)

        callback1_called = False
        callback2_called = False

        async def callback1(run_id: str, detected_at: datetime) -> None:
            nonlocal callback1_called
            callback1_called = True

        async def callback2(run_id: str, detected_at: datetime) -> None:
            nonlocal callback2_called
            callback2_called = True

        manager.add_silence_callback(callback1)
        manager.add_silence_callback(callback2)

        await manager.start_monitoring("run-001")

        # 検出器の沈黙ハンドラを直接テスト
        detector = manager._detectors["run-001"]
        detector._last_activity = datetime.now(timezone.utc) - timedelta(seconds=100)
        await detector._handle_silence(datetime.now(timezone.utc))

        await manager.stop_all()

        # Assert
        assert callback1_called
        assert callback2_called
