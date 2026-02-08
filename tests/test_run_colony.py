"""Run-Colony紐付け機能のテスト

GitHub Issue #14: P1-13: Run-Colony紐付け機能

RunをColonyに紐付ける機能のテスト。v4互換のためcolony_idはオプショナル。
"""

from hiveforge.core.events import (
    BaseEvent,
    EventType,
    RunStartedEvent,
)


class TestRunColonyBinding:
    """Run-Colony紐付け基本テスト"""

    def test_base_event_has_colony_id_field(self):
        """BaseEventにcolony_idフィールドが存在する

        v5ではRunをColonyに紐付けるため、BaseEventにcolony_idを追加。
        デフォルトはNoneで後方互換性を保つ。
        """
        # Arrange: BaseEventを作成
        event = BaseEvent(type=EventType.RUN_STARTED, run_id="run-123")

        # Assert: colony_idフィールドが存在し、デフォルトはNone
        assert hasattr(event, "colony_id")
        assert event.colony_id is None

    def test_run_started_event_with_colony_id(self):
        """RunStartedEventにcolony_idを指定できる

        Runを作成時にColonyに紐付けできる。
        """
        # Arrange & Act: colony_idを指定してRunStartedEventを作成
        event = RunStartedEvent(
            run_id="run-456",
            colony_id="colony-001",
        )

        # Assert: colony_idが設定される
        assert event.colony_id == "colony-001"
        assert event.run_id == "run-456"

    def test_run_started_event_without_colony_id(self):
        """colony_idなしでRunStartedEventを作成できる（v4互換）

        既存のRunはcolony_id=Noneで独立動作。
        """
        # Arrange & Act: colony_idを指定せずにRunStartedEventを作成
        event = RunStartedEvent(run_id="run-789")

        # Assert: colony_idはNone
        assert event.colony_id is None
        assert event.run_id == "run-789"


class TestColonyRunProjection:
    """ColonyからRun一覧を取得する投影のテスト"""

    def test_run_colony_projection_exists(self):
        """RunColonyProjectionクラスが存在する"""
        # Arrange & Act: インポートできることを確認
        from hiveforge.core.state.projections import RunColonyProjection

        # Assert: クラスが存在
        assert RunColonyProjection is not None

    def test_run_colony_projection_apply_run_started(self):
        """RunStartedEventを適用するとColony-Run紐付けが記録される"""
        # Arrange
        from hiveforge.core.state.projections import RunColonyProjection

        projection = RunColonyProjection()
        event = RunStartedEvent(
            run_id="run-001",
            colony_id="colony-001",
        )

        # Act: イベントを適用
        projection.apply(event)

        # Assert: Colony-Run紐付けが記録される
        assert "colony-001" in projection.colony_runs
        assert "run-001" in projection.colony_runs["colony-001"]

    def test_run_colony_projection_multiple_runs(self):
        """同じColonyに複数のRunを紐付けできる"""
        # Arrange
        from hiveforge.core.state.projections import RunColonyProjection

        projection = RunColonyProjection()
        event1 = RunStartedEvent(run_id="run-001", colony_id="colony-001")
        event2 = RunStartedEvent(run_id="run-002", colony_id="colony-001")
        event3 = RunStartedEvent(run_id="run-003", colony_id="colony-002")

        # Act: 複数のイベントを適用
        projection.apply(event1)
        projection.apply(event2)
        projection.apply(event3)

        # Assert: 各Colonyに正しくRunが紐付く
        assert set(projection.colony_runs["colony-001"]) == {"run-001", "run-002"}
        assert projection.colony_runs["colony-002"] == ["run-003"]

    def test_run_colony_projection_no_colony_id(self):
        """colony_idがNoneのRunは独立として扱う"""
        # Arrange
        from hiveforge.core.state.projections import RunColonyProjection

        projection = RunColonyProjection()
        event = RunStartedEvent(run_id="run-orphan", colony_id=None)

        # Act: colony_idなしのイベントを適用
        projection.apply(event)

        # Assert: 独立Runとして記録（Noneキーではなくorphansリスト）
        assert "run-orphan" in projection.orphan_runs

    def test_get_runs_by_colony(self):
        """ColonyIDからRun一覧を取得できる"""
        # Arrange
        from hiveforge.core.state.projections import RunColonyProjection

        projection = RunColonyProjection()
        projection.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        projection.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        # Act: ColonyからRun一覧を取得
        runs = projection.get_runs_by_colony("colony-001")

        # Assert
        assert set(runs) == {"run-001", "run-002"}

    def test_get_runs_by_colony_empty(self):
        """存在しないColonyは空リストを返す"""
        # Arrange
        from hiveforge.core.state.projections import RunColonyProjection

        projection = RunColonyProjection()

        # Act: 存在しないColonyのRunを取得
        runs = projection.get_runs_by_colony("nonexistent")

        # Assert
        assert runs == []


class TestRunColonyEventSerialization:
    """colony_id付きイベントのシリアライズテスト"""

    def test_colony_id_serialized_to_json(self):
        """colony_idがJSONにシリアライズされる"""
        # Arrange
        event = RunStartedEvent(run_id="run-001", colony_id="colony-001")

        # Act: JSONにシリアライズ
        json_str = event.to_json()

        # Assert: colony_idが含まれる
        assert '"colony_id": "colony-001"' in json_str

    def test_colony_id_deserialized_from_json(self):
        """colony_id付きJSONからデシリアライズできる"""
        # Arrange
        event = RunStartedEvent(run_id="run-001", colony_id="colony-001")
        json_str = event.to_json()

        # Act: JSONからデシリアライズ
        restored = RunStartedEvent.model_validate_json(json_str)

        # Assert
        assert restored.colony_id == "colony-001"
        assert restored.run_id == "run-001"
