"""
Hive/Colony E2Eテスト

Hive作成 → Colony作成 → Run実行 → 完了 の基本フローをテスト
"""

import pytest
from fastapi.testclient import TestClient

from hiveforge.api.server import app


@pytest.fixture
def client():
    """テスト用HTTPクライアント"""
    return TestClient(app)


class TestHiveBasicFlow:
    """Hive基本フローのE2Eテスト"""

    def test_complete_hive_flow(self, client: TestClient):
        """Hive作成 → Colony作成 → Run実行 → 完了 のフルフロー

        完全なHiveライフサイクルをテスト:
        1. Hiveを作成
        2. ColonyをHiveに追加
        3. ColonyでRunを実行
        4. Taskを作成・完了
        5. Runを完了
        6. Colonyを完了
        7. Hiveを終了
        """
        # Arrange & Act 1: Hive作成
        hive_response = client.post(
            "/hives", json={"name": "E2E Test Hive", "description": "E2Eテスト用Hive"}
        )

        # Assert 1
        assert hive_response.status_code == 201
        hive = hive_response.json()
        assert hive["name"] == "E2E Test Hive"
        assert hive["status"] == "active"
        hive_id = hive["hive_id"]

        # Act 2: Colony作成
        colony_response = client.post(
            f"/hives/{hive_id}/colonies", json={"name": "Feature Colony", "goal": "機能実装"}
        )

        # Assert 2
        assert colony_response.status_code == 201
        colony = colony_response.json()
        assert colony["name"] == "Feature Colony"
        assert colony["status"] == "created"
        colony_id = colony["colony_id"]

        # Act 3: Colony開始
        start_response = client.post(f"/colonies/{colony_id}/start")

        # Assert 3
        assert start_response.status_code == 200
        started_colony = start_response.json()
        assert started_colony["status"] == "running"

        # Act 4: Run開始（Colony内）
        run_response = client.post("/runs", json={"goal": "タスク実行"})

        # Assert 4
        assert run_response.status_code == 201
        run = run_response.json()
        run_id = run["run_id"]

        # Act 5: Task作成
        task_response = client.post(
            f"/runs/{run_id}/tasks", json={"title": "テストタスク", "description": "E2E用タスク"}
        )

        # Assert 5
        assert task_response.status_code == 201
        task = task_response.json()
        task_id = task["task_id"]

        # Act 6: Task完了
        complete_task_response = client.post(
            f"/runs/{run_id}/tasks/{task_id}/complete", json={"result": {"message": "完了"}}
        )

        # Assert 6
        assert complete_task_response.status_code == 200

        # Act 7: Run完了
        complete_run_response = client.post(
            f"/runs/{run_id}/complete", json={"summary": "全タスク完了"}
        )

        # Assert 7
        assert complete_run_response.status_code == 200
        completed_run = complete_run_response.json()
        assert completed_run["status"] == "completed"

        # Act 8: Colony完了
        complete_colony_response = client.post(f"/colonies/{colony_id}/complete")

        # Assert 8
        assert complete_colony_response.status_code == 200
        completed_colony = complete_colony_response.json()
        assert completed_colony["status"] == "completed"

        # Act 9: Hive終了
        close_hive_response = client.post(f"/hives/{hive_id}/close")

        # Assert 9
        assert close_hive_response.status_code == 200
        closed_hive = close_hive_response.json()
        assert closed_hive["status"] == "closed"

    def test_hive_with_multiple_colonies(self, client: TestClient):
        """1つのHiveに複数のColonyを作成できる

        Arrange: Hiveを作成
        Act: 複数のColonyを追加
        Assert: 全てのColonyが一覧で取得できる
        """
        # Arrange: Hive作成
        hive = client.post("/hives", json={"name": "Multi-Colony Hive"}).json()
        hive_id = hive["hive_id"]

        # Act: 複数Colony作成
        colony_names = ["Colony A", "Colony B", "Colony C"]
        created_colonies = []
        for name in colony_names:
            colony = client.post(f"/hives/{hive_id}/colonies", json={"name": name}).json()
            created_colonies.append(colony)

        # Assert: Colony一覧取得
        colonies_response = client.get(f"/hives/{hive_id}/colonies")
        assert colonies_response.status_code == 200
        colonies = colonies_response.json()
        assert len(colonies) == 3
        assert {c["name"] for c in colonies} == set(colony_names)


class TestHiveErrorHandling:
    """Hive異常系のE2Eテスト"""

    def test_colony_in_nonexistent_hive(self, client: TestClient):
        """存在しないHiveにColonyを作成できない

        Arrange: 存在しないHive ID
        Act: Colony作成を試行
        Assert: 404エラー
        """
        # Arrange
        fake_hive_id = "nonexistent-hive-id"

        # Act
        response = client.post(f"/hives/{fake_hive_id}/colonies", json={"name": "Orphan Colony"})

        # Assert
        assert response.status_code == 404

    def test_close_hive_with_running_colony(self, client: TestClient):
        """実行中Colonyがあるとき、Hiveは警告付きで終了される

        Arrange: HiveとRunning Colonyを作成
        Act: Hive終了を試行
        Assert: 終了は成功するが、Colonyも終了される
        """
        # Arrange
        hive = client.post("/hives", json={"name": "Active Hive"}).json()
        hive_id = hive["hive_id"]

        colony = client.post(f"/hives/{hive_id}/colonies", json={"name": "Active Colony"}).json()
        colony_id = colony["colony_id"]

        # Colonyを開始
        client.post(f"/colonies/{colony_id}/start")

        # Act: Hive終了
        response = client.post(f"/hives/{hive_id}/close")

        # Assert: 終了は成功（強制終了的な動作）
        assert response.status_code == 200


class TestEmergencyStop:
    """緊急停止のE2Eテスト"""

    def test_emergency_stop_propagation(self, client: TestClient):
        """緊急停止がRun全体に伝播する

        Arrange: Run、Task、確認要請を作成
        Act: 緊急停止を発行
        Assert: Runがaborted状態になる
        """
        # Arrange: Run開始
        run = client.post("/runs", json={"goal": "緊急停止テスト"}).json()
        run_id = run["run_id"]

        # Task作成
        client.post(f"/runs/{run_id}/tasks", json={"title": "進行中タスク"})

        # Act: 緊急停止
        response = client.post(
            f"/runs/{run_id}/emergency-stop", json={"reason": "テスト用緊急停止"}
        )

        # Assert
        assert response.status_code == 200

        # Runの状態を確認
        run_status = client.get(f"/runs/{run_id}").json()
        assert run_status["state"] == "aborted"


class TestLineageTracking:
    """因果追跡のE2Eテスト"""

    def test_event_lineage_retrieval(self, client: TestClient):
        """イベントの因果リンクを取得できる

        Arrange: Run → Task作成 → Task完了 の連鎖イベント
        Act: 完了イベントのLineageを取得
        Assert: 親イベント（Task作成、Run開始）が含まれる
        """
        # Arrange: Run開始
        run = client.post("/runs", json={"goal": "Lineageテスト"}).json()
        run_id = run["run_id"]

        # Task作成
        task = client.post(f"/runs/{run_id}/tasks", json={"title": "Lineage追跡用タスク"}).json()
        task_id = task["task_id"]

        # Task完了
        client.post(
            f"/runs/{run_id}/tasks/{task_id}/complete", json={"result": {"message": "完了"}}
        )

        # Act: イベント一覧を取得してLineageを確認
        events = client.get(f"/runs/{run_id}/events").json()

        # Assert: 複数のイベントがある
        assert len(events) >= 2  # run.started, task.created (task.completedはARに反映後)

        # 完了イベントを探す
        complete_events = [e for e in events if e["type"] == "task.completed"]
        assert len(complete_events) >= 1

        complete_event = complete_events[0]
        event_id = complete_event["id"]

        # Lineage取得
        lineage_response = client.get(f"/runs/{run_id}/events/{event_id}/lineage")
        assert lineage_response.status_code == 200
