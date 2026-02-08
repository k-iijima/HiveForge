"""M5-2: パフォーマンスベンチマークテスト

AR (Akashic Record) のappend/replay、イベントのシリアライズ/デシリアライズ、
ハッシュ計算、投影構築のパフォーマンスを計測する。

実行方法:
    pytest tests/test_benchmark.py -m benchmark --benchmark-enable -v

通常のテスト実行 (pytest) ではスキップされる。
"""

from __future__ import annotations

import pytest

from hiveforge.core import AkashicRecord, generate_event_id
from hiveforge.core.ar.projections import RunProjection, build_run_projection
from hiveforge.core.events import (
    RunCompletedEvent,
    RunStartedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)
from hiveforge.core.events.base import BaseEvent, compute_hash
from hiveforge.core.events.registry import parse_event
from hiveforge.core.honeycomb.models import Episode, KPIScores, Outcome
from hiveforge.core.honeycomb.store import HoneycombStore


# =========================================================================
# ベンチマークデータの準備
# =========================================================================


def _make_task_created_event(run_id: str = "run-bench") -> TaskCreatedEvent:
    """ベンチマーク用のTaskCreatedEventを作成"""
    return TaskCreatedEvent(
        run_id=run_id,
        payload={
            "title": "ベンチマーク用タスク",
            "description": "パフォーマンス計測のためのテストタスク",
            "colony_id": "colony-bench",
        },
    )


def _make_run_events(run_id: str, task_count: int = 10) -> list[BaseEvent]:
    """一連のRunイベントを生成（RunStarted → N * TaskCreated+Completed → RunCompleted）"""
    events: list[BaseEvent] = []

    events.append(
        RunStartedEvent(run_id=run_id, payload={"goal": f"Benchmark with {task_count} tasks"})
    )

    for i in range(task_count):
        task_id = f"task-{i:04d}"
        events.append(
            TaskCreatedEvent(
                run_id=run_id,
                payload={
                    "title": f"Task {i}",
                    "description": f"Benchmark task #{i}",
                    "colony_id": "colony-bench",
                    "task_id": task_id,
                },
            )
        )
        events.append(
            TaskCompletedEvent(
                run_id=run_id,
                payload={
                    "task_id": task_id,
                    "result": f"Completed task {i}",
                    "token_count": 100,
                },
            )
        )

    events.append(RunCompletedEvent(run_id=run_id, payload={"status": "success"}))
    return events


def _make_episode(episode_id: str, colony_id: str = "colony-1") -> Episode:
    """ベンチマーク用Episodeを作成"""
    return Episode(
        episode_id=episode_id,
        run_id=f"run-{episode_id}",
        colony_id=colony_id,
        outcome=Outcome.SUCCESS,
        duration_seconds=120.5,
        token_count=1500,
        kpi_scores=KPIScores(correctness=1.0, lead_time_seconds=120.5, incident_rate=0.0),
    )


# =========================================================================
# 1. compute_hash ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestComputeHashBenchmark:
    """compute_hash (JCS正規化 + SHA-256) のパフォーマンス"""

    def test_hash_small_payload(self, benchmark):
        """小さなpayloadのハッシュ計算"""
        # Arrange
        data = {"type": "task.created", "actor": "test", "payload": {"title": "x"}}

        # Act & Assert
        result = benchmark(compute_hash, data)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_hash_medium_payload(self, benchmark):
        """中規模payloadのハッシュ計算"""
        # Arrange: 20フィールドのpayload
        data = {
            "type": "task.created",
            "actor": "worker-01",
            "payload": {f"field_{i}": f"value_{i}" * 10 for i in range(20)},
        }

        # Act & Assert
        result = benchmark(compute_hash, data)
        assert isinstance(result, str)

    def test_hash_large_payload(self, benchmark):
        """大規模payloadのハッシュ計算"""
        # Arrange: 大きなネストされた構造
        data = {
            "type": "task.completed",
            "actor": "worker-01",
            "payload": {
                "result": "x" * 1000,
                "metrics": {f"metric_{i}": float(i) for i in range(50)},
                "logs": [f"log entry {i}: " + "detail " * 20 for i in range(10)],
            },
        }

        # Act & Assert
        result = benchmark(compute_hash, data)
        assert isinstance(result, str)


# =========================================================================
# 2. イベントシリアライズ/デシリアライズ ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestEventSerializationBenchmark:
    """イベントのシリアライズ/デシリアライズ性能"""

    def test_to_jsonl(self, benchmark):
        """BaseEvent.to_jsonl() — Pydanticシリアライズ"""
        # Arrange
        event = _make_task_created_event()

        # Act & Assert
        result = benchmark(event.to_jsonl)
        assert isinstance(result, str)
        assert "task.created" in result

    def test_parse_event_from_json(self, benchmark):
        """parse_event() — JSON文字列からBaseEventへデシリアライズ"""
        # Arrange
        event = _make_task_created_event()
        json_line = event.to_jsonl()

        # Act & Assert
        parsed = benchmark(parse_event, json_line)
        assert parsed.type.value == "task.created"

    def test_model_dump(self, benchmark):
        """BaseEvent.model_dump() — dict変換"""
        # Arrange
        event = _make_task_created_event()

        # Act & Assert
        result = benchmark(event.model_dump)
        assert isinstance(result, dict)


# =========================================================================
# 3. AR append ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestARAappendBenchmark:
    """AkashicRecord.append() のパフォーマンス"""

    def test_append_single_event(self, benchmark, tmp_path):
        """1イベントの追記（ファイルI/O含む）"""
        # Arrange
        ar = AkashicRecord(vault_path=tmp_path / "vault")
        run_id = "run-bench-append"
        counter = [0]

        def do_append():
            counter[0] += 1
            event = TaskCreatedEvent(
                run_id=run_id,
                payload={
                    "title": f"Task {counter[0]}",
                    "task_id": f"task-{counter[0]:04d}",
                },
            )
            return ar.append(event, run_id)

        # Act & Assert
        result = benchmark(do_append)
        assert result is not None


# =========================================================================
# 4. AR replay ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestARReplayBenchmark:
    """AkashicRecord.replay() のパフォーマンス"""

    @pytest.fixture
    def ar_with_events(self, tmp_path):
        """100件のイベントを含むARを準備"""
        ar = AkashicRecord(vault_path=tmp_path / "vault")
        run_id = "run-bench-replay"
        for event in _make_run_events(run_id, task_count=50):
            ar.append(event, run_id)
        return ar, run_id

    @pytest.fixture
    def ar_with_many_events(self, tmp_path):
        """1000件のイベントを含むARを準備"""
        ar = AkashicRecord(vault_path=tmp_path / "vault")
        run_id = "run-bench-replay-large"
        for event in _make_run_events(run_id, task_count=500):
            ar.append(event, run_id)
        return ar, run_id

    def test_replay_100_events(self, benchmark, ar_with_events):
        """100件のイベントを全件リプレイ"""
        ar, run_id = ar_with_events

        # Act & Assert
        events = benchmark(lambda: list(ar.replay(run_id)))
        assert len(events) == 102  # 1 RunStarted + 50*2 + 1 RunCompleted

    def test_replay_1000_events(self, benchmark, ar_with_many_events):
        """1000件のイベントを全件リプレイ"""
        ar, run_id = ar_with_many_events

        # Act & Assert
        events = benchmark(lambda: list(ar.replay(run_id)))
        assert len(events) == 1002  # 1 RunStarted + 500*2 + 1 RunCompleted


# =========================================================================
# 5. 投影 (Projection) 構築ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestProjectionBenchmark:
    """RunProjection構築のパフォーマンス"""

    def test_build_projection_small(self, benchmark):
        """10タスクの投影構築"""
        # Arrange
        run_id = "run-proj-small"
        events = _make_run_events(run_id, task_count=10)

        # Act & Assert
        proj = benchmark(build_run_projection, events, run_id)
        assert isinstance(proj, RunProjection)

    def test_build_projection_medium(self, benchmark):
        """50タスクの投影構築"""
        # Arrange
        run_id = "run-proj-medium"
        events = _make_run_events(run_id, task_count=50)

        # Act & Assert
        proj = benchmark(build_run_projection, events, run_id)
        assert isinstance(proj, RunProjection)

    def test_build_projection_large(self, benchmark):
        """200タスクの投影構築"""
        # Arrange
        run_id = "run-proj-large"
        events = _make_run_events(run_id, task_count=200)

        # Act & Assert
        proj = benchmark(build_run_projection, events, run_id)
        assert isinstance(proj, RunProjection)


# =========================================================================
# 6. HoneycombStore ベンチマーク
# =========================================================================


@pytest.mark.benchmark
class TestHoneycombStoreBenchmark:
    """HoneycombStoreのパフォーマンス"""

    def test_append_episode(self, benchmark, tmp_path):
        """Episode 1件の永続化"""
        # Arrange
        store = HoneycombStore(tmp_path / "honeycomb")
        counter = [0]

        def do_append():
            counter[0] += 1
            ep = _make_episode(f"ep-{counter[0]:04d}")
            store.append(ep)
            return ep

        # Act & Assert
        result = benchmark(do_append)
        assert result is not None

    def test_replay_100_episodes(self, benchmark, tmp_path):
        """100件のEpisodeを全件リプレイ"""
        # Arrange
        store = HoneycombStore(tmp_path / "honeycomb")
        for i in range(100):
            store.append(_make_episode(f"ep-{i:04d}"))

        # Act & Assert
        episodes = benchmark(store.replay_all)
        assert len(episodes) == 100

    def test_replay_colony_filtered(self, benchmark, tmp_path):
        """Colony別の250件フィルターリプレイ"""
        # Arrange: 2つのcolonyに125件ずつ
        store = HoneycombStore(tmp_path / "honeycomb")
        for i in range(250):
            colony = "colony-a" if i % 2 == 0 else "colony-b"
            store.append(_make_episode(f"ep-{i:04d}", colony_id=colony))

        # Act & Assert
        episodes = benchmark(lambda: store.replay_colony("colony-a"))
        assert len(episodes) == 125
