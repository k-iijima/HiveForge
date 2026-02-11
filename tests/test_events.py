"""イベントモデルのテスト

ColonyForgeの中核となるイベントモデルをテストする。
イベントはイミュータブルで、ULID形式のID、UTC タイムスタンプ、
JCS正規化によるSHA-256ハッシュを持つ。
"""

import json
from datetime import UTC, date, timedelta
from decimal import Decimal
from pathlib import PurePosixPath
from uuid import UUID

import pytest
from pydantic import ValidationError

from colonyforge.core.events import (
    DecisionRecordedEvent,
    EventType,
    RunStartedEvent,
    TaskCreatedEvent,
    WorkerAssignedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
    WorkerProgressEvent,
    WorkerStartedEvent,
    compute_hash,
    generate_event_id,
    parse_event,
)


class TestGenerateEventId:
    """イベントID生成（ULID形式）のテスト

    ULIDは時間順序付きのユニークIDで、26文字の文字列として表現される。
    タイムスタンプ成分を含むため、生成順にソート可能である。
    """

    def test_returns_26_character_string(self):
        """ULIDは26文字の文字列として生成される

        ULID仕様: 10文字のタイムスタンプ + 16文字のランダム成分 = 26文字
        """
        # Arrange: なし（純粋関数のため前提状態不要）

        # Act: IDを生成
        event_id = generate_event_id()

        # Assert: 26文字の文字列である
        assert isinstance(event_id, str), "IDは文字列型であるべき"
        assert len(event_id) == 26, "ULIDは26文字であるべき"

    def test_generates_unique_ids(self):
        """連続して生成されるIDはすべてユニークである

        ULIDのランダム成分により、同一ミリ秒内でも衝突しない。
        """
        # Arrange: 生成するID数を定義
        count = 100

        # Act: 複数のIDを生成
        generated_ids = [generate_event_id() for _ in range(count)]

        # Assert: すべてのIDがユニーク
        unique_ids = set(generated_ids)
        assert len(unique_ids) == count, (
            f"100個のIDがすべてユニークであるべき（重複: {count - len(unique_ids)}）"
        )


class TestComputeHash:
    """ハッシュ計算（JCS + SHA-256）のテスト

    JCS (RFC 8785) で正規化したJSONをSHA-256でハッシュ化する。
    これにより、キーの順序やスペースに依存しない決定論的なハッシュが得られる。
    """

    def test_deterministic_hash_for_same_data(self):
        """同一データに対しては常に同じハッシュが計算される

        決定論的ハッシュはイベントチェーンの整合性検証に必須。
        """
        # Arrange: テスト用データを用意
        data = {"type": "test", "value": 123, "nested": {"key": "value"}}

        # Act: 同じデータのハッシュを2回計算
        hash_first = compute_hash(data)
        hash_second = compute_hash(data)

        # Assert: 同じハッシュ値が得られる
        assert hash_first == hash_second, "同一データは同一ハッシュを生成すべき"

    def test_different_hash_for_different_data(self):
        """異なるデータに対しては異なるハッシュが計算される

        1ビットでも異なればハッシュは完全に異なる（雪崩効果）。
        """
        # Arrange: 値が1だけ異なる2つのデータ
        data_value_1 = {"type": "test", "value": 1}
        data_value_2 = {"type": "test", "value": 2}

        # Act: それぞれのハッシュを計算
        hash_1 = compute_hash(data_value_1)
        hash_2 = compute_hash(data_value_2)

        # Assert: ハッシュが異なる
        assert hash_1 != hash_2, "異なるデータは異なるハッシュを生成すべき"

    def test_hash_excludes_hash_field(self):
        """hashフィールド自体はハッシュ計算から除外される

        イベントのハッシュ値をイベント自体に含める際、
        循環参照を避けるためhashフィールドを除外して計算する。
        """
        # Arrange: hashフィールドの有無が異なる2つのデータ
        data_without_hash = {"type": "test", "value": 1}
        data_with_hash = {"type": "test", "value": 1, "hash": "this_is_ignored"}

        # Act: 両方のハッシュを計算
        hash_without = compute_hash(data_without_hash)
        hash_with = compute_hash(data_with_hash)

        # Assert: hashフィールドの有無に関わらず同じハッシュ
        assert hash_without == hash_with, "hashフィールドはハッシュ計算から除外されるべき"

    def test_hash_is_64_character_hex_string(self):
        """ハッシュはSHA-256の16進数文字列（64文字）である"""
        # Arrange: 任意のデータ
        data = {"key": "value"}

        # Act: ハッシュを計算
        hash_value = compute_hash(data)

        # Assert: 64文字の16進数文字列
        assert len(hash_value) == 64, "SHA-256は64文字の16進数"
        assert all(c in "0123456789abcdef" for c in hash_value), "16進数文字のみで構成"

    def test_key_order_does_not_affect_hash(self):
        """キーの順序が異なっても同じハッシュが計算される（JCS正規化）

        JCS (RFC 8785) はキーを辞書順にソートするため、
        元のキー順序に依存しない。
        """
        # Arrange: キー順序が異なる2つのデータ（論理的には同一）
        data_order_abc = {"a": 1, "b": 2, "c": 3}
        data_order_cba = {"c": 3, "b": 2, "a": 1}

        # Act: それぞれのハッシュを計算
        hash_abc = compute_hash(data_order_abc)
        hash_cba = compute_hash(data_order_cba)

        # Assert: 同じハッシュ値（キー順序に非依存）
        assert hash_abc == hash_cba, "JCS正規化によりキー順序は無視されるべき"

    def test_serialize_list_values(self):
        """リスト内の値も正しくシリアライズされる

        _serialize_value関数はリスト内のdatetime/enumも再帰的に処理する。
        """
        from datetime import datetime

        from colonyforge.core.events import _serialize_value

        # Arrange: datetimeを含むリスト
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        data_with_list = [dt, "string", {"nested": dt}]

        # Act: シリアライズ
        result = _serialize_value(data_with_list)

        # Assert: リスト内のdatetimeがISO文字列に変換されている
        assert result[0] == "2024-01-01T12:00:00+00:00"
        assert result[1] == "string"
        assert result[2]["nested"] == "2024-01-01T12:00:00+00:00"

    def test_serialize_pydantic_model(self):
        """Pydanticモデルがdictにシリアライズされる

        payloadにPydanticモデルが混入してもjcs.canonicalizeで
        例外が発生せず、正しくシリアライズされることを確認。
        """
        from pydantic import BaseModel

        from colonyforge.core.events import _serialize_value

        # Arrange: Pydanticモデルを含むデータ
        class InnerModel(BaseModel):
            name: str = "test"
            value: int = 42

        model = InnerModel()

        # Act: シリアライズ
        result = _serialize_value(model)

        # Assert: dictに変換されている
        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_serialize_set_and_frozenset(self):
        """setとfrozensetがソートされたリストにシリアライズされる

        JCS互換のために、順序を決定論的にする必要がある。
        """
        from colonyforge.core.events import _serialize_value

        # Arrange: setとfrozensetを含むデータ
        data_set = {3, 1, 2}
        data_frozenset = frozenset(["c", "a", "b"])

        # Act: シリアライズ
        result_set = _serialize_value(data_set)
        result_frozenset = _serialize_value(data_frozenset)

        # Assert: ソートされたリストに変換
        assert result_set == [1, 2, 3]
        assert result_frozenset == ["a", "b", "c"]

    def test_serialize_tuple(self):
        """tupleがリストにシリアライズされる"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        data = (1, "two", 3.0)

        # Act
        result = _serialize_value(data)

        # Assert
        assert result == [1, "two", 3.0]

    def test_serialize_bytes(self):
        """bytesが16進文字列にシリアライズされる"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        data = b"\xde\xad\xbe\xef"

        # Act
        result = _serialize_value(data)

        # Assert
        assert result == "deadbeef"

    def test_compute_hash_with_pydantic_payload(self):
        """Pydanticモデルを含むdictでもハッシュが計算できる"""
        from pydantic import BaseModel

        # Arrange
        class Payload(BaseModel):
            msg: str = "hello"

        data = {"type": "test", "payload": Payload()}

        # Act & Assert: 例外が発生しないことを確認
        hash_value = compute_hash(data)
        assert len(hash_value) == 64


class TestEventImmutability:
    """イベントのイミュータビリティ（不変性）テスト

    イベントソーシングにおいて、一度作成されたイベントは変更されてはならない。
    Pydanticのfrozen設定により、属性の変更を禁止する。
    """

    def test_event_attributes_cannot_be_modified(self):
        """作成後のイベント属性は変更できない

        frozen=Trueにより、属性への代入はValidationErrorを発生させる。
        """
        # Arrange: イベントを作成
        event = RunStartedEvent(run_id="test-run", payload={"goal": "test"})
        original_run_id = event.run_id

        # Act & Assert: 属性変更を試みるとエラー
        with pytest.raises(ValidationError):
            event.run_id = "modified-run-id"

        # Assert: 値が変更されていないことを確認
        assert event.run_id == original_run_id, "イベントは変更されていないべき"


class TestEventAutoFields:
    """イベントの自動生成フィールドテスト

    イベント作成時に、ID・タイムスタンプ・ハッシュが自動生成される。
    """

    def test_id_is_auto_generated(self):
        """イベントIDは指定しなくても自動生成される"""
        # Arrange & Act: IDを指定せずにイベント作成
        event = RunStartedEvent(run_id="test-run")

        # Assert: IDが自動生成されている
        assert event.id is not None, "IDは自動生成されるべき"
        assert len(event.id) == 26, "IDはULID形式（26文字）であるべき"

    def test_timestamp_is_auto_generated_in_utc(self):
        """タイムスタンプはUTCで自動生成される

        タイムゾーン情報を含むことで、異なる環境間での整合性を保証。
        """
        # Arrange & Act: タイムスタンプを指定せずにイベント作成
        event = RunStartedEvent(run_id="test-run")

        # Assert: UTCタイムスタンプが設定されている
        assert event.timestamp is not None, "タイムスタンプは自動生成されるべき"
        assert event.timestamp.tzinfo is not None, "タイムゾーン情報を含むべき"
        assert event.timestamp.tzinfo.utcoffset(None).total_seconds() == 0, "UTCであるべき"

    def test_hash_is_computed_automatically(self):
        """ハッシュはイベント内容から自動計算される"""
        # Arrange & Act: イベント作成
        event = RunStartedEvent(run_id="test-run", payload={"goal": "build"})

        # Assert: ハッシュが計算されている
        assert event.hash is not None, "ハッシュは自動計算されるべき"
        assert len(event.hash) == 64, "SHA-256ハッシュは64文字"

    def test_same_content_produces_same_hash(self):
        """同じ内容のイベントは同じハッシュを持つ（IDとタイムスタンプを除く）

        注意: 実際にはIDとタイムスタンプが異なるため、異なるハッシュになる。
        これはイベントの一意性を保証するための設計。
        """
        # Arrange: 同じパラメータで2つのイベントを作成
        event1 = RunStartedEvent(run_id="same-run", payload={"goal": "test"})
        event2 = RunStartedEvent(run_id="same-run", payload={"goal": "test"})

        # Assert: IDが異なるためハッシュも異なる
        assert event1.id != event2.id, "IDは毎回ユニークに生成される"
        assert event1.hash != event2.hash, "IDが異なるためハッシュも異なる"


class TestEventSerialization:
    """イベントのシリアライズ/デシリアライズテスト

    イベントはJSON形式で永続化・通信される。
    シリアライズ→デシリアライズで情報が失われないことを確認。
    """

    def test_roundtrip_preserves_all_fields(self):
        """JSON往復変換ですべてのフィールドが保持される"""
        # Arrange: すべてのフィールドを明示的に設定したイベント
        original = TaskCreatedEvent(
            run_id="test-run",
            task_id="task-001",
            actor="test-agent",
            payload={"title": "Implement feature X", "priority": "high"},
        )

        # Act: JSON化して復元
        json_str = original.to_json()
        restored = TaskCreatedEvent.from_json(json_str)

        # Assert: すべてのフィールドが一致
        assert restored.id == original.id, "IDが保持されるべき"
        assert restored.type == original.type, "typeが保持されるべき"
        assert restored.run_id == original.run_id, "run_idが保持されるべき"
        assert restored.task_id == original.task_id, "task_idが保持されるべき"
        assert restored.actor == original.actor, "actorが保持されるべき"
        assert restored.payload == original.payload, "payloadが保持されるべき"
        assert restored.timestamp == original.timestamp, "timestampが保持されるべき"
        assert restored.hash == original.hash, "hashが保持されるべき"

    def test_to_json_produces_valid_json(self):
        """to_json()は有効なJSON文字列を生成する"""
        # Arrange: イベント作成
        event = RunStartedEvent(run_id="test-run", payload={"key": "value"})

        # Act: JSON化
        json_str = event.to_json()

        # Assert: 有効なJSONとしてパース可能
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict), "パース結果は辞書であるべき"
        assert parsed["type"] == "run.started", "typeフィールドが正しい"


class TestParseEvent:
    """parse_event関数のテスト

    JSON文字列または辞書からイベントオブジェクトを復元する。
    typeフィールドに基づいて適切なイベントクラスにディスパッチ。
    """

    def test_parse_run_started_from_dict(self):
        """辞書からRunStartedEventをパースできる"""
        # Arrange: RunStartedEventを表す辞書
        data = {
            "type": "run.started",
            "run_id": "run-001",
            "payload": {"goal": "Build a web app"},
        }

        # Act: パース
        event = parse_event(data)

        # Assert: 正しいクラスとフィールド
        assert isinstance(event, RunStartedEvent), "RunStartedEventにパースされるべき"
        assert event.run_id == "run-001"
        assert event.payload["goal"] == "Build a web app"

    def test_parse_task_created_from_dict(self):
        """辞書からTaskCreatedEventをパースできる"""
        # Arrange: TaskCreatedEventを表す辞書
        data = {
            "type": "task.created",
            "run_id": "run-001",
            "task_id": "task-001",
            "payload": {"title": "Setup project"},
        }

        # Act: パース
        event = parse_event(data)

        # Assert: 正しいクラスとフィールド
        assert isinstance(event, TaskCreatedEvent), "TaskCreatedEventにパースされるべき"
        assert event.task_id == "task-001"

    def test_parse_from_json_string(self):
        """JSON文字列から直接パースできる"""
        # Arrange: JSON文字列
        json_str = '{"type": "run.started", "run_id": "run-from-json", "payload": {}}'

        # Act: パース
        event = parse_event(json_str)

        # Assert: 正しくパースされる
        assert isinstance(event, RunStartedEvent)
        assert event.run_id == "run-from-json"

    def test_parse_decision_recorded_from_dict(self):
        """辞書からDecisionRecordedEventをパースできる

        Decisionは仕様変更や判断事項をイベントとして残すための汎用イベント。
        """
        # Arrange: DecisionRecordedEventを表す辞書
        data = {
            "type": "decision.recorded",
            "run_id": "run-001",
            "actor": "copilot",
            "payload": {
                "decision_id": "dec-001",
                "key": "D3",
                "title": "Requirementを2階層に分割",
                "selected": "C",
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, DecisionRecordedEvent)
        assert event.type == EventType.DECISION_RECORDED
        assert event.payload["key"] == "D3"

    def test_parse_preserves_optional_fields(self):
        """オプショナルフィールドも正しくパースされる"""
        # Arrange: すべてのフィールドを含むデータ
        data = {
            "type": "task.created",
            "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "run_id": "run-001",
            "task_id": "task-001",
            "actor": "human",
            "payload": {"title": "Test"},
            "prev_hash": "abc123",
        }

        # Act: パース
        event = parse_event(data)

        # Assert: オプショナルフィールドが保持される
        assert event.id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert event.actor == "human"
        assert event.prev_hash == "abc123"


class TestEventType:
    """EventType列挙型のテスト"""

    def test_run_events_have_run_prefix(self):
        """Runイベントはrun.プレフィックスを持つ"""
        # Assert: Run関連イベントのプレフィックス確認
        assert EventType.RUN_STARTED.value == "run.started"
        assert EventType.RUN_COMPLETED.value == "run.completed"
        assert EventType.RUN_FAILED.value == "run.failed"

    def test_task_events_have_task_prefix(self):
        """Taskイベントはtask.プレフィックスを持つ"""
        # Assert: Task関連イベントのプレフィックス確認
        assert EventType.TASK_CREATED.value == "task.created"
        assert EventType.TASK_COMPLETED.value == "task.completed"

    def test_hive_events_have_hive_prefix(self):
        """Hiveイベントはhive.プレフィックスを持つ"""
        # Assert: Hive関連イベントのプレフィックス確認
        assert EventType.HIVE_CREATED.value == "hive.created"
        assert EventType.HIVE_CLOSED.value == "hive.closed"

    def test_colony_events_have_colony_prefix(self):
        """Colonyイベントはcolony.プレフィックスを持つ"""
        # Assert: Colony関連イベントのプレフィックス確認
        assert EventType.COLONY_CREATED.value == "colony.created"
        assert EventType.COLONY_STARTED.value == "colony.started"
        assert EventType.COLONY_COMPLETED.value == "colony.completed"
        assert EventType.COLONY_FAILED.value == "colony.failed"


class TestHiveEvents:
    """Hiveイベントのテスト

    Hiveは複数のColonyを管理する最上位のコンテナ。
    Hive層のイベントはrun_idを持たず、hive_idで識別される。
    """

    def test_hive_created_event_can_be_instantiated(self):
        """HiveCreatedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Hive作成イベントを生成
        from colonyforge.core.events import HiveCreatedEvent

        event = HiveCreatedEvent(
            actor="beekeeper",
            payload={"hive_id": "hive-001", "name": "Test Hive"},
        )

        # Assert: 正しい型と値
        assert event.type == EventType.HIVE_CREATED
        assert event.actor == "beekeeper"
        assert event.payload["hive_id"] == "hive-001"
        assert event.run_id is None  # Hiveイベントはrun_idを持たない

    def test_hive_closed_event_can_be_instantiated(self):
        """HiveClosedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Hive終了イベントを生成
        from colonyforge.core.events import HiveClosedEvent

        event = HiveClosedEvent(
            actor="beekeeper",
            payload={"hive_id": "hive-001", "reason": "completed"},
        )

        # Assert: 正しい型と値
        assert event.type == EventType.HIVE_CLOSED
        assert event.payload["reason"] == "completed"

    def test_hive_events_are_parseable(self):
        """Hiveイベントがparse_eventでパース可能"""
        # Arrange: Hive作成イベントのデータ
        data = {
            "type": "hive.created",
            "actor": "beekeeper",
            "payload": {"hive_id": "hive-001", "name": "Test Hive"},
        }

        # Act: パース
        from colonyforge.core.events import HiveCreatedEvent

        event = parse_event(data)

        # Assert: 正しいクラスにパースされる
        assert isinstance(event, HiveCreatedEvent)
        assert event.type == EventType.HIVE_CREATED


class TestColonyEvents:
    """Colonyイベントのテスト

    ColonyはHive内のサブプロジェクト単位。
    複数のRunを束ねて1つの目標に向かう。
    """

    def test_colony_created_event_can_be_instantiated(self):
        """ColonyCreatedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Colony作成イベントを生成
        from colonyforge.core.events import ColonyCreatedEvent

        event = ColonyCreatedEvent(
            actor="queen_bee",
            payload={
                "colony_id": "colony-001",
                "hive_id": "hive-001",
                "goal": "Implement feature X",
            },
        )

        # Assert: 正しい型と値
        assert event.type == EventType.COLONY_CREATED
        assert event.actor == "queen_bee"
        assert event.payload["colony_id"] == "colony-001"
        assert event.payload["hive_id"] == "hive-001"

    def test_colony_started_event_can_be_instantiated(self):
        """ColonyStartedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Colony開始イベントを生成
        from colonyforge.core.events import ColonyStartedEvent

        event = ColonyStartedEvent(
            actor="queen_bee",
            payload={"colony_id": "colony-001"},
        )

        # Assert: 正しい型
        assert event.type == EventType.COLONY_STARTED

    def test_colony_completed_event_can_be_instantiated(self):
        """ColonyCompletedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Colony完了イベントを生成
        from colonyforge.core.events import ColonyCompletedEvent

        event = ColonyCompletedEvent(
            actor="queen_bee",
            payload={"colony_id": "colony-001", "summary": "All runs completed"},
        )

        # Assert: 正しい型
        assert event.type == EventType.COLONY_COMPLETED

    def test_colony_failed_event_can_be_instantiated(self):
        """ColonyFailedEventが正しくインスタンス化できる"""
        # Arrange: なし

        # Act: Colony失敗イベントを生成
        from colonyforge.core.events import ColonyFailedEvent

        event = ColonyFailedEvent(
            actor="queen_bee",
            payload={"colony_id": "colony-001", "error": "Critical failure"},
        )

        # Assert: 正しい型
        assert event.type == EventType.COLONY_FAILED

    def test_colony_events_are_parseable(self):
        """Colonyイベントがparse_eventでパース可能"""
        # Arrange: 各Colonyイベントのデータ
        colony_events_data = [
            {"type": "colony.created", "payload": {"colony_id": "c1"}},
            {"type": "colony.started", "payload": {"colony_id": "c1"}},
            {"type": "colony.completed", "payload": {"colony_id": "c1"}},
            {"type": "colony.failed", "payload": {"colony_id": "c1", "error": "err"}},
        ]

        # Act & Assert: 全てパース可能
        from colonyforge.core.events import (
            ColonyCompletedEvent,
            ColonyCreatedEvent,
            ColonyFailedEvent,
            ColonyStartedEvent,
        )

        expected_classes = [
            ColonyCreatedEvent,
            ColonyStartedEvent,
            ColonyCompletedEvent,
            ColonyFailedEvent,
        ]

        for data, expected_class in zip(colony_events_data, expected_classes, strict=True):
            event = parse_event(data)
            assert isinstance(event, expected_class), (
                f"{data['type']} should parse to {expected_class.__name__}"
            )


class TestWorkerBeeEvents:
    """Worker Beeイベントのテスト"""

    def test_worker_assigned_event(self):
        """WorkerAssignedEventが正しく作成される"""
        # Arrange & Act
        event = WorkerAssignedEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="queen",
            payload={"goal": "Implement feature X"},
        )

        # Assert
        assert event.type == EventType.WORKER_ASSIGNED
        assert event.worker_id == "worker-1"
        assert event.task_id == "task-1"

    def test_worker_started_event(self):
        """WorkerStartedEventが正しく作成される"""
        # Arrange & Act
        event = WorkerStartedEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="worker-1",
            payload={},
        )

        # Assert
        assert event.type == EventType.WORKER_STARTED
        assert event.worker_id == "worker-1"

    def test_worker_progress_event(self):
        """WorkerProgressEventが正しく作成される"""
        # Arrange & Act
        event = WorkerProgressEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="worker-1",
            progress=50,
            payload={"message": "halfway done"},
        )

        # Assert
        assert event.type == EventType.WORKER_PROGRESS
        assert event.progress == 50

    def test_worker_progress_validates_range(self):
        """progressは0-100の範囲のみ許容"""
        # Assert: 範囲外はエラー
        with pytest.raises(ValueError):
            WorkerProgressEvent(
                run_id="run-1",
                task_id="task-1",
                worker_id="worker-1",
                actor="worker-1",
                progress=101,
                payload={},
            )

    def test_worker_completed_event(self):
        """WorkerCompletedEventが正しく作成される"""
        # Arrange & Act
        event = WorkerCompletedEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="worker-1",
            payload={"result": "Success"},
        )

        # Assert
        assert event.type == EventType.WORKER_COMPLETED
        assert event.worker_id == "worker-1"

    def test_worker_failed_event(self):
        """WorkerFailedEventが正しく作成される"""
        # Arrange & Act
        event = WorkerFailedEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="worker-1",
            reason="Connection timeout",
            payload={},
        )

        # Assert
        assert event.type == EventType.WORKER_FAILED
        assert event.reason == "Connection timeout"

    def test_worker_events_serialization(self):
        """Worker Beeイベントがシリアライズ可能"""
        # Arrange
        event = WorkerAssignedEvent(
            run_id="run-1",
            task_id="task-1",
            worker_id="worker-1",
            actor="queen",
            payload={},
        )

        # Act
        json_str = event.to_json()
        parsed = parse_event(json_str)

        # Assert
        assert isinstance(parsed, WorkerAssignedEvent)
        assert parsed.worker_id == "worker-1"


class TestEventTypeMapCompleteness:
    """EVENT_TYPE_MAP が全 EventType を網羅していることを検証

    EventType に新しい値が追加されたとき、
    EVENT_TYPE_MAP への登録漏れを検出するガードレールテスト。
    """

    def test_all_event_types_registered_in_map(self):
        """全 EventType が EVENT_TYPE_MAP に登録されている

        未登録の EventType があると BaseEvent にフォールバックし、
        ペイロードのスキーマ検証が効かなくなるため、
        全 EventType の専用クラス登録を強制する。
        """
        from colonyforge.core.events.registry import EVENT_TYPE_MAP
        from colonyforge.core.events.types import EventType

        # Arrange: 全EventType値を取得
        all_types = set(EventType)

        # Act: MAP に登録されたキーを取得
        registered_types = set(EVENT_TYPE_MAP.keys())

        # Assert: 差分がゼロ
        missing = all_types - registered_types
        assert missing == set(), (
            f"EVENT_TYPE_MAP に未登録の EventType があります: {sorted(m.value for m in missing)}"
        )


class TestSerializeValueJcsSafety:
    """_serialize_value のJCS互換性安全テスト

    compute_hash前にpayloadの全値がJCS互換のプリミティブ型に
    変換されることを保証し、チェーン整合性の破綻を未然に防ぐ。
    """

    def test_serialize_uuid(self):
        """UUIDが文字列に変換される"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        uuid_val = UUID("12345678-1234-5678-1234-567812345678")

        # Act
        result = _serialize_value(uuid_val)

        # Assert
        assert result == "12345678-1234-5678-1234-567812345678"
        assert isinstance(result, str)

    def test_serialize_date(self):
        """date（datetimeでない）がISO文字列に変換される"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        date_val = date(2026, 2, 8)

        # Act
        result = _serialize_value(date_val)

        # Assert
        assert result == "2026-02-08"
        assert isinstance(result, str)

    def test_serialize_timedelta(self):
        """timedeltaが秒数に変換される"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        td = timedelta(hours=1, minutes=30)

        # Act
        result = _serialize_value(td)

        # Assert
        assert result == 5400.0

    def test_serialize_decimal(self):
        """Decimalがfloatに変換される"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        dec = Decimal("3.14")

        # Act
        result = _serialize_value(dec)

        # Assert
        assert result == 3.14
        assert isinstance(result, float)

    def test_serialize_decimal_infinity_raises(self):
        """Decimal('Infinity')はValueErrorを送出する"""
        from colonyforge.core.events import _serialize_value

        # Act & Assert
        with pytest.raises(ValueError, match="JCS非互換"):
            _serialize_value(Decimal("Infinity"))

    def test_serialize_purepath(self):
        """PurePathが文字列に変換される"""
        from colonyforge.core.events import _serialize_value

        # Arrange
        path = PurePosixPath("/workspace/ColonyForge/src")

        # Act
        result = _serialize_value(path)

        # Assert
        assert result == "/workspace/ColonyForge/src"
        assert isinstance(result, str)

    def test_serialize_float_inf_raises(self):
        """float('inf')はValueErrorを送出する

        JSON仕様にinfは存在しないため、JCSでの正規化は不可能。
        """
        from colonyforge.core.events import _serialize_value

        # Act & Assert
        with pytest.raises(ValueError, match="inf"):
            _serialize_value(float("inf"))

    def test_serialize_float_nan_raises(self):
        """float('nan')はValueErrorを送出する"""
        from colonyforge.core.events import _serialize_value

        # Act & Assert
        with pytest.raises(ValueError, match="nan"):
            _serialize_value(float("nan"))

    def test_serialize_unsupported_type_raises_typeerror(self):
        """サポート外の型はTypeErrorを送出する

        暗黙的にスルーしてJCSで壊れるのではなく、
        明示的なエラーで問題箇所を特定しやすくする。
        """
        import re

        from colonyforge.core.events import _serialize_value

        # Act & Assert: 正規表現パターンはサポート外
        with pytest.raises(TypeError, match="JCS互換に変換できない型"):
            _serialize_value(re.compile(r"test"))

    def test_serialize_custom_object_raises_typeerror(self):
        """カスタムオブジェクトはTypeErrorを送出する"""
        from colonyforge.core.events import _serialize_value

        class CustomObj:
            pass

        # Act & Assert
        with pytest.raises(TypeError, match="JCS互換に変換できない型"):
            _serialize_value(CustomObj())

    def test_serialize_none_passthrough(self):
        """NoneはそのままJCS互換（null）として通る"""
        from colonyforge.core.events import _serialize_value

        # Act
        result = _serialize_value(None)

        # Assert
        assert result is None

    def test_serialize_finite_float_passthrough(self):
        """有限floatはそのまま通る"""
        from colonyforge.core.events import _serialize_value

        # Act
        result = _serialize_value(3.14)

        # Assert
        assert result == 3.14

    def test_serialize_int_passthrough(self):
        """intはそのまま通る"""
        from colonyforge.core.events import _serialize_value

        # Act
        result = _serialize_value(42)

        # Assert
        assert result == 42

    def test_serialize_bool_passthrough(self):
        """boolはそのまま通る（intのサブクラスだが別扱い）"""
        from colonyforge.core.events import _serialize_value

        # Act & Assert: boolがintにすり替わらないことを確認
        assert _serialize_value(True) is True
        assert _serialize_value(False) is False

    def test_compute_hash_with_uuid_payload(self):
        """UUIDを含むpayloadでcompute_hashが正常に計算できる"""
        # Arrange
        data = {
            "type": "test",
            "payload": {"request_id": UUID("abcdef01-2345-6789-abcd-ef0123456789")},
        }

        # Act & Assert: 例外が発生しない
        result = compute_hash(data)
        assert len(result) == 64

    def test_compute_hash_with_mixed_types_payload(self):
        """様々なJCS互換型を含むpayloadの決定論的ハッシュ"""
        # Arrange
        data1 = {
            "type": "test",
            "payload": {
                "uuid": UUID("12345678-0000-0000-0000-000000000000"),
                "date": date(2026, 1, 1),
                "decimal": Decimal("1.5"),
                "timedelta": timedelta(seconds=60),
            },
        }
        data2 = {
            "type": "test",
            "payload": {
                "uuid": UUID("12345678-0000-0000-0000-000000000000"),
                "date": date(2026, 1, 1),
                "decimal": Decimal("1.5"),
                "timedelta": timedelta(seconds=60),
            },
        }

        # Act
        hash1 = compute_hash(data1)
        hash2 = compute_hash(data2)

        # Assert: 同じデータから同じハッシュ
        assert hash1 == hash2
