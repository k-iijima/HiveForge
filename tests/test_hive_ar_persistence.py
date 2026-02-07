"""Hive/Colony AR永続化テスト

M1-1-d: サーバー再起動後のデータ復元を検証する。
HiveStoreにイベントを書き込み、新しいHiveStoreインスタンスで
同じVaultを開いたときにデータが復元されることを確認する。
"""

from pathlib import Path

import pytest

from hiveforge.core.ar.hive_projections import HiveAggregate, build_hive_aggregate
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
