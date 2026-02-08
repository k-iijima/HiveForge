"""Hive/Colony AR永続化テスト

M1-1-d: サーバー再起動後のデータ復元を検証する。
HiveStoreにイベントを書き込み、新しいHiveStoreインスタンスで
同じVaultを開いたときにデータが復元されることを確認する。
"""

from pathlib import Path

from hiveforge.core.ar.hive_projections import build_hive_aggregate
from hiveforge.core.ar.hive_storage import HiveStore
from hiveforge.core.events import (
    ColonyCompletedEvent,
    ColonyCreatedEvent,
    ColonyStartedEvent,
    HiveClosedEvent,
    HiveCreatedEvent,
    generate_event_id,
)


class TestHivePersistence:
    """Hiveデータの永続化テスト"""

    def test_hive_survives_store_recreation(self, tmp_path: Path) -> None:
        """HiveStoreを再作成してもHiveデータが復元される

        サーバー再起動をシミュレート: 同じVaultパスで
        新しいHiveStoreインスタンスを作成し、データが残ることを確認。
        """
        # Arrange: HiveStoreにHiveを作成
        hive_id = generate_event_id()
        store1 = HiveStore(tmp_path)
        event = HiveCreatedEvent(
            run_id=hive_id,
            actor="user",
            payload={
                "hive_id": hive_id,
                "name": "永続化テストHive",
                "description": "再起動テスト用",
            },
        )
        store1.append(event, hive_id)

        # Act: 新しいHiveStoreインスタンスを作成（サーバー再起動をシミュレート）
        store2 = HiveStore(tmp_path)
        events = list(store2.replay(hive_id))
        aggregate = build_hive_aggregate(hive_id, events)

        # Assert: データが復元される
        assert aggregate.name == "永続化テストHive"
        assert aggregate.projection.metadata.get("description") == "再起動テスト用"
        assert aggregate.state.value == "active"

    def test_hive_list_survives_store_recreation(self, tmp_path: Path) -> None:
        """HiveStoreを再作成してもHive一覧が復元される"""
        # Arrange: 複数のHiveを作成
        store1 = HiveStore(tmp_path)
        hive_ids = []
        for i in range(3):
            hive_id = generate_event_id()
            hive_ids.append(hive_id)
            event = HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": f"Hive{i}"},
            )
            store1.append(event, hive_id)

        # Act: 新しいHiveStoreインスタンスで一覧取得
        store2 = HiveStore(tmp_path)
        restored_ids = store2.list_hives()

        # Assert: 全Hiveが復元される
        assert set(hive_ids) == set(restored_ids)

    def test_closed_hive_state_survives_recreation(self, tmp_path: Path) -> None:
        """終了済みHiveの状態（closed）が再起動後も復元される"""
        # Arrange: Hiveを作成して終了
        hive_id = generate_event_id()
        store1 = HiveStore(tmp_path)
        store1.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "CloseTest"},
            ),
            hive_id,
        )
        store1.append(
            HiveClosedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id},
            ),
            hive_id,
        )

        # Act: 新しいHiveStoreでリプレイ
        store2 = HiveStore(tmp_path)
        aggregate = build_hive_aggregate(hive_id, store2.replay(hive_id))

        # Assert: closed状態が復元される
        assert aggregate.state.value == "closed"


class TestColonyPersistence:
    """Colonyデータの永続化テスト"""

    def test_colony_survives_store_recreation(self, tmp_path: Path) -> None:
        """HiveStoreを再作成してもColonyデータが復元される"""
        # Arrange: HiveとColonyを作成
        hive_id = generate_event_id()
        colony_id = generate_event_id()
        store1 = HiveStore(tmp_path)

        store1.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "ParentHive"},
            ),
            hive_id,
        )
        store1.append(
            ColonyCreatedEvent(
                run_id=colony_id,
                actor="user",
                payload={
                    "colony_id": colony_id,
                    "hive_id": hive_id,
                    "name": "永続化Colony",
                    "goal": "永続化テスト",
                },
            ),
            hive_id,
        )

        # Act: 新しいHiveStoreでリプレイ
        store2 = HiveStore(tmp_path)
        aggregate = build_hive_aggregate(hive_id, store2.replay(hive_id))

        # Assert: Colonyデータが復元される
        assert colony_id in aggregate.colonies
        colony = aggregate.colonies[colony_id]
        assert colony.goal == "永続化テスト"
        assert colony.metadata.get("name") == "永続化Colony"
        assert colony.state.value == "pending"

    def test_colony_lifecycle_survives_store_recreation(self, tmp_path: Path) -> None:
        """Colonyのライフサイクル（作成→開始→完了）が再起動後に復元される"""
        # Arrange: Hive + Colonyの全ライフサイクルイベントを記録
        hive_id = generate_event_id()
        colony_id = generate_event_id()
        store1 = HiveStore(tmp_path)

        store1.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "LifecycleHive"},
            ),
            hive_id,
        )
        store1.append(
            ColonyCreatedEvent(
                run_id=colony_id,
                actor="user",
                payload={
                    "colony_id": colony_id,
                    "hive_id": hive_id,
                    "name": "LifecycleColony",
                    "goal": "ライフサイクルテスト",
                },
            ),
            hive_id,
        )
        store1.append(
            ColonyStartedEvent(
                run_id=colony_id,
                actor="user",
                payload={"colony_id": colony_id},
            ),
            hive_id,
        )
        store1.append(
            ColonyCompletedEvent(
                run_id=colony_id,
                actor="user",
                payload={"colony_id": colony_id},
            ),
            hive_id,
        )

        # Act: 新しいHiveStoreでリプレイ
        store2 = HiveStore(tmp_path)
        aggregate = build_hive_aggregate(hive_id, store2.replay(hive_id))

        # Assert: 完了状態が復元される
        colony = aggregate.colonies[colony_id]
        assert colony.state.value == "completed"
        assert colony.completed_at is not None

    def test_multiple_colonies_survive_recreation(self, tmp_path: Path) -> None:
        """複数Colonyが再起動後に全て復元される"""
        # Arrange: Hiveに3つのColonyを作成
        hive_id = generate_event_id()
        store1 = HiveStore(tmp_path)
        store1.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "MultiColonyHive"},
            ),
            hive_id,
        )

        colony_ids = []
        for i in range(3):
            colony_id = generate_event_id()
            colony_ids.append(colony_id)
            store1.append(
                ColonyCreatedEvent(
                    run_id=colony_id,
                    actor="user",
                    payload={
                        "colony_id": colony_id,
                        "hive_id": hive_id,
                        "name": f"Colony{i}",
                        "goal": f"Goal{i}",
                    },
                ),
                hive_id,
            )

        # Act: 新しいHiveStoreでリプレイ
        store2 = HiveStore(tmp_path)
        aggregate = build_hive_aggregate(hive_id, store2.replay(hive_id))

        # Assert: 全Colonyが復元される
        assert len(aggregate.colonies) == 3
        for colony_id in colony_ids:
            assert colony_id in aggregate.colonies


class TestApiPersistence:
    """API経由の永続化テスト（統合テスト）"""

    def test_hive_created_via_api_persisted_in_hive_store(self, client, tmp_path: Path) -> None:
        """API経由で作成したHiveがHiveStoreに永続化される"""
        # Act: API経由でHiveを作成
        response = client.post("/hives", json={"name": "APIテスト", "description": "API経由"})
        assert response.status_code == 201
        hive_id = response.json()["hive_id"]

        # Assert: HiveStoreに直接アクセスして永続化を確認
        from hiveforge.api.helpers import get_hive_store

        store = get_hive_store()
        events = list(store.replay(hive_id))
        assert len(events) >= 1
        assert events[0].type.value == "hive.created"

    def test_colony_created_via_api_persisted_in_hive_store(self, client, tmp_path: Path) -> None:
        """API経由で作成したColonyがHiveStoreに永続化される"""
        # Arrange: Hiveを作成
        hive_response = client.post("/hives", json={"name": "ColonyAPITest"})
        hive_id = hive_response.json()["hive_id"]

        # Act: Colony作成
        colony_response = client.post(
            f"/hives/{hive_id}/colonies",
            json={"name": "APIColony", "goal": "APIテスト目標"},
        )
        assert colony_response.status_code == 201

        # Assert: HiveStoreにColonyイベントが記録される
        from hiveforge.api.helpers import get_hive_store

        store = get_hive_store()
        events = list(store.replay(hive_id))
        event_types = [e.type.value for e in events]
        assert "hive.created" in event_types
        assert "colony.created" in event_types

    def test_hive_data_consistent_after_multiple_operations(self, client, tmp_path: Path) -> None:
        """複数操作後のデータ整合性: 作成→Colony追加→終了が正しく反映される"""
        # Arrange: Hive作成
        hive_response = client.post("/hives", json={"name": "整合性テスト"})
        hive_id = hive_response.json()["hive_id"]

        # Colony作成
        client.post(f"/hives/{hive_id}/colonies", json={"name": "Col1"})
        client.post(f"/hives/{hive_id}/colonies", json={"name": "Col2"})

        # Hive終了
        client.post(f"/hives/{hive_id}/close")

        # Act: GET APIで最終状態を取得
        response = client.get(f"/hives/{hive_id}")

        # Assert: 全操作が反映されている
        data = response.json()
        assert data["status"] == "closed"
        assert len(data["colonies"]) == 2


class TestHiveStoreDirectOperations:
    """HiveStoreの直接操作テスト"""

    def test_list_hives_empty(self, tmp_path: Path) -> None:
        """Hiveがない場合は空リストを返す"""
        # Arrange
        store = HiveStore(tmp_path)

        # Act
        hives = store.list_hives()

        # Assert
        assert hives == []

    def test_list_hives_with_data(self, tmp_path: Path) -> None:
        """Hiveがある場合はIDリストを返す"""
        # Arrange
        store = HiveStore(tmp_path)
        hive_id1 = generate_event_id()
        hive_id2 = generate_event_id()
        store.append(
            HiveCreatedEvent(
                run_id=hive_id1,
                actor="user",
                payload={"hive_id": hive_id1, "name": "Hive1"},
            ),
            hive_id1,
        )
        store.append(
            HiveCreatedEvent(
                run_id=hive_id2,
                actor="user",
                payload={"hive_id": hive_id2, "name": "Hive2"},
            ),
            hive_id2,
        )

        # Act
        hives = store.list_hives()

        # Assert
        assert len(hives) == 2
        assert hive_id1 in hives
        assert hive_id2 in hives

    def test_count_events_empty(self, tmp_path: Path) -> None:
        """イベントがない場合はカウント0"""
        # Arrange
        store = HiveStore(tmp_path)

        # Act
        count = store.count_events("nonexistent-hive")

        # Assert
        assert count == 0

    def test_count_events_with_data(self, tmp_path: Path) -> None:
        """イベントがある場合はカウントを返す"""
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()
        store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "Test"},
            ),
            hive_id,
        )
        store.append(
            ColonyCreatedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="colony-1",
                payload={"colony_id": "colony-1", "name": "Colony1"},
            ),
            hive_id,
        )

        # Act
        count = store.count_events(hive_id)

        # Assert
        assert count == 2

    def test_replay_nonexistent_hive(self, tmp_path: Path) -> None:
        """存在しないHiveのreplayは空"""
        # Arrange
        store = HiveStore(tmp_path)

        # Act
        events = list(store.replay("nonexistent-hive"))

        # Assert
        assert events == []

    def test_replay_preserves_event_order(self, tmp_path: Path) -> None:
        """replayがイベントの挿入順序を保持する"""
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()
        store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "OrderTest"},
            ),
            hive_id,
        )
        store.append(
            ColonyCreatedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="colony-1",
                payload={"colony_id": "colony-1", "name": "Col1"},
            ),
            hive_id,
        )
        store.append(
            ColonyStartedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="colony-1",
                payload={"colony_id": "colony-1"},
            ),
            hive_id,
        )

        # Act
        events = list(store.replay(hive_id))

        # Assert
        assert len(events) == 3
        assert events[0].type.value == "hive.created"
        assert events[1].type.value == "colony.created"
        assert events[2].type.value == "colony.started"


class TestHiveStoreAppendAndHashChain:
    """HiveStore.appendとハッシュチェーンのテスト"""

    def test_append_sets_prev_hash(self, tmp_path: Path) -> None:
        """appendがprev_hashを設定してハッシュチェーンを構築する

        2つ目以降のイベントには前のイベントのhashがprev_hashとして
        設定され、改ざん検知可能なチェーンが作られる。
        """
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()

        # Act: 2つのイベントを追記
        event1 = store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "Chain Test"},
            ),
            hive_id,
        )
        event2 = store.append(
            ColonyCreatedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="colony-1",
                payload={"colony_id": "colony-1", "name": "Col1"},
            ),
            hive_id,
        )

        # Assert: event2のprev_hashはevent1のhash
        assert event1.prev_hash is None  # 最初のイベント
        assert event2.prev_hash == event1.hash

    def test_append_first_event_has_no_prev_hash(self, tmp_path: Path) -> None:
        """最初のイベントのprev_hashはNone

        空ファイルへの最初の追記ではprev_hashがNullになる。
        """
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()

        # Act
        event = store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "First"},
            ),
            hive_id,
        )

        # Assert
        assert event.prev_hash is None
        assert event.hash is not None

    def test_append_multiple_events_chain(self, tmp_path: Path) -> None:
        """複数イベントのハッシュチェーンが正しく構築される

        _find_last_hashが正しくファイル末尾から最新ハッシュを
        読み取れることを検証する。
        """
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()

        # Act: 5つのイベントを追記してチェーンを作る
        events = []
        events.append(
            store.append(
                HiveCreatedEvent(
                    run_id=hive_id,
                    actor="user",
                    payload={"hive_id": hive_id, "name": "Multi"},
                ),
                hive_id,
            )
        )
        for i in range(4):
            events.append(
                store.append(
                    ColonyCreatedEvent(
                        run_id=hive_id,
                        actor="user",
                        colony_id=f"col-{i}",
                        payload={"colony_id": f"col-{i}", "name": f"Colony-{i}"},
                    ),
                    hive_id,
                )
            )

        # Assert: 各イベントのprev_hashが前のイベントのhashと一致
        assert events[0].prev_hash is None
        for i in range(1, len(events)):
            assert events[i].prev_hash == events[i - 1].hash

    def test_append_and_replay_consistency(self, tmp_path: Path) -> None:
        """appendしたイベントがreplayで正しく読み出せる"""
        # Arrange
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()
        store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "Replay"},
            ),
            hive_id,
        )
        store.append(
            ColonyCreatedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="col-1",
                payload={"colony_id": "col-1", "name": "C1"},
            ),
            hive_id,
        )

        # Act
        replayed = list(store.replay(hive_id))

        # Assert
        assert len(replayed) == 2
        assert replayed[0].hash is not None
        assert replayed[1].prev_hash == replayed[0].hash

    def test_find_last_hash_large_file(self, tmp_path: Path) -> None:
        """大きなファイルで_find_last_hashのchunkループが動作する

        ファイルサイズが8192バイトを超える場合、_find_last_hashは
        末尾からchunk単位で読み込んでハッシュを探す。
        """
        # Arrange: 多数のイベントを追記して8KB超のファイルを作る
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()

        # 1イベント≈200バイト、50イベントで≈10KB
        events_appended = []
        events_appended.append(
            store.append(
                HiveCreatedEvent(
                    run_id=hive_id,
                    actor="user",
                    payload={"hive_id": hive_id, "name": "Large File Test"},
                ),
                hive_id,
            )
        )
        for i in range(50):
            events_appended.append(
                store.append(
                    ColonyCreatedEvent(
                        run_id=hive_id,
                        actor="user",
                        colony_id=f"col-{i:03d}",
                        payload={
                            "colony_id": f"col-{i:03d}",
                            "name": f"Colony {i}",
                            "description": f"Testing large file chunk read for colony {i}",
                        },
                    ),
                    hive_id,
                )
            )

        # ファイルが8KB超であることを確認
        events_file = store._get_events_file(hive_id)
        assert events_file.stat().st_size > 8192

        # Act: さらに1つ追記（_find_last_hashのchunkループが動作）
        last_event = store.append(
            ColonyStartedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="col-000",
                payload={"colony_id": "col-000"},
            ),
            hive_id,
        )

        # Assert: prev_hashが直前のイベントのhashと一致
        assert last_event.prev_hash == events_appended[-1].hash

    def test_replay_blank_lines_skipped(self, tmp_path: Path) -> None:
        """空行を含むイベントファイルでもreplayが正しく動作する

        replay中に空行（\\n only）があった場合、continueでスキップする。
        """
        # Arrange: イベントを追記してからファイルに空行を挿入
        store = HiveStore(tmp_path)
        hive_id = generate_event_id()
        store.append(
            HiveCreatedEvent(
                run_id=hive_id,
                actor="user",
                payload={"hive_id": hive_id, "name": "Blank Line Test"},
            ),
            hive_id,
        )

        # ファイルに空行を追加
        events_file = store._get_events_file(hive_id)
        with open(events_file, "a", encoding="utf-8") as f:
            f.write("\n\n")

        store.append(
            ColonyCreatedEvent(
                run_id=hive_id,
                actor="user",
                colony_id="col-1",
                payload={"colony_id": "col-1", "name": "After Blank"},
            ),
            hive_id,
        )

        # Act
        replayed = list(store.replay(hive_id))

        # Assert: 空行はスキップされ、2イベントのみ
        assert len(replayed) == 2

    def test_list_hives_missing_directory(self, tmp_path: Path) -> None:
        """_hives_pathが存在しない場合は空リストを返す

        HiveStore作成後にhivesディレクトリが削除された場合でも
        エラーにならず空リストが返される。
        """
        import shutil

        # Arrange
        store = HiveStore(tmp_path)

        # hivesディレクトリを強制削除
        shutil.rmtree(store._hives_path)

        # Act
        hives = store.list_hives()

        # Assert
        assert hives == []
