"""API Server モジュールのテスト"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from hiveforge.api.server import app
from hiveforge.api.helpers import (
    get_ar,
    get_active_runs,
    set_ar,
    clear_active_runs,
)


@pytest.fixture
def client(tmp_path):
    """テスト用クライアント"""
    # グローバル状態をクリア
    set_ar(None)
    clear_active_runs()

    # server.py と helpers.py の両方で使用される get_settings をモック
    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
    ):
        with TestClient(app) as client:
            yield client

    # クリーンアップ
    set_ar(None)
    clear_active_runs()


class TestHealthEndpoint:
    """ヘルスチェックエンドポイントのテスト"""

    def test_health_check(self, client):
        """ヘルスチェックが正常に応答する"""
        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "active_runs" in data


class TestRunsEndpoints:
    """Runs関連エンドポイントのテスト"""

    def test_start_run(self, client):
        """Runを開始できる"""
        # Act
        response = client.post(
            "/runs",
            json={"goal": "テストRun", "metadata": {"key": "value"}},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "run_id" in data
        assert data["goal"] == "テストRun"
        assert data["state"] == "running"
        assert "started_at" in data

    def test_list_runs_active_only(self, client):
        """アクティブなRunのみをリストできる"""
        # Arrange
        client.post("/runs", json={"goal": "Test Run 1"})
        client.post("/runs", json={"goal": "Test Run 2"})

        # Act
        response = client.get("/runs?active_only=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_runs_all(self, client):
        """全てのRunをリストできる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "Test Run"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/complete")

        # Act
        response = client.get("/runs?active_only=false")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_get_run(self, client):
        """Runの詳細を取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "詳細テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.get(f"/runs/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["goal"] == "詳細テスト"
        assert data["state"] == "running"

    def test_get_run_not_found(self, client):
        """存在しないRunで404を返す"""
        # Act
        response = client.get("/runs/nonexistent-run")

        # Assert
        assert response.status_code == 404

    def test_complete_run(self, client):
        """タスクがない場合、Runを完了できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "完了テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(f"/runs/{run_id}/complete")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["run_id"] == run_id

    def test_complete_run_with_incomplete_tasks_fails(self, client):
        """未完了タスクがある場合、Runを完了できない"""
        # Arrange: タスクを作成して未完了のまま
        run_resp = client.post("/runs", json={"goal": "未完了タスクテスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "未完了タスク"})
        task_id = task_resp.json()["task_id"]

        # Act: 未完了タスクがある状態で完了を試みる
        response = client.post(f"/runs/{run_id}/complete")

        # Assert: 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert "incomplete_task_ids" in data["detail"]
        assert task_id in data["detail"]["incomplete_task_ids"]

    def test_complete_run_with_completed_tasks(self, client):
        """全タスクが完了している場合、Runを完了できる"""
        # Arrange: タスクを作成して完了させる
        run_resp = client.post("/runs", json={"goal": "タスク完了済みテスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "完了タスク"})
        task_id = task_resp.json()["task_id"]
        client.post(f"/runs/{run_id}/tasks/{task_id}/complete", json={})

        # Act
        response = client.post(f"/runs/{run_id}/complete")

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_complete_run_force_cancels_incomplete_tasks(self, client):
        """force=trueで未完了タスクを強制キャンセルして完了できる"""
        # Arrange: タスクを作成して未完了のまま
        run_resp = client.post("/runs", json={"goal": "強制完了テスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "キャンセル対象タスク"})
        task_id = task_resp.json()["task_id"]

        # Act: force=trueで強制完了
        response = client.post(f"/runs/{run_id}/complete", json={"force": True})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "cancelled_task_ids" in data
        assert task_id in data["cancelled_task_ids"]

    def test_complete_run_force_rejects_pending_requirements(self, client):
        """force=trueで未解決の確認要請も却下して完了できる"""
        # Arrange: Runを開始して確認要請を作成
        run_resp = client.post("/runs", json={"goal": "強制完了テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "未解決の確認要請", "options": ["承認", "却下"]},
        )
        req_id = req_resp.json()["id"]  # RequirementResponseのフィールド名

        # Act: force=trueで強制完了
        response = client.post(f"/runs/{run_id}/complete", json={"force": True})

        # Assert: 確認要請も却下される
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "cancelled_requirement_ids" in data
        assert req_id in data["cancelled_requirement_ids"]

    def test_complete_run_not_found(self, client):
        """存在しないRunの完了で404を返す"""
        # Act
        response = client.post("/runs/nonexistent/complete")

        # Assert
        assert response.status_code == 404

    def test_emergency_stop(self, client):
        """Runを緊急停止できる"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "緊急停止テスト"})
        run_id = run_resp.json()["run_id"]

        # Act: 緊急停止を実行
        response = client.post(
            f"/runs/{run_id}/emergency-stop",
            json={"reason": "テスト停止", "scope": "run"},
        )

        # Assert: 停止が成功
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        assert data["run_id"] == run_id
        assert data["reason"] == "テスト停止"
        assert "stopped_at" in data

    def test_emergency_stop_not_found(self, client):
        """存在しないRunの緊急停止で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/emergency-stop",
            json={"reason": "テスト"},
        )

        # Assert
        assert response.status_code == 404

    def test_emergency_stop_cancels_tasks(self, client):
        """緊急停止は未完了タスクをキャンセルする"""
        # Arrange: Runを開始してタスクを作成
        run_resp = client.post("/runs", json={"goal": "緊急停止タスクテスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "進行中タスク"})
        task_id = task_resp.json()["task_id"]

        # Act: 緊急停止を実行
        response = client.post(
            f"/runs/{run_id}/emergency-stop",
            json={"reason": "テスト停止"},
        )

        # Assert: タスクがキャンセルされている
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        assert "cancelled_task_ids" in data
        assert task_id in data["cancelled_task_ids"]

    def test_emergency_stop_rejects_pending_requirements(self, client):
        """緊急停止は未解決の確認要請を却下する"""
        # Arrange: Runを開始して確認要請を作成
        run_resp = client.post("/runs", json={"goal": "緊急停止確認要請テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "テスト確認要請"},
        )
        req_id = req_resp.json()["id"]

        # Act: 緊急停止を実行
        response = client.post(
            f"/runs/{run_id}/emergency-stop",
            json={"reason": "テスト停止"},
        )

        # Assert: 確認要請が却下されている
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        assert "cancelled_requirement_ids" in data
        assert req_id in data["cancelled_requirement_ids"]


class TestTasksEndpoints:
    """Tasks関連エンドポイントのテスト"""

    def test_create_task(self, client):
        """Taskを作成できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "タスクテスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks",
            json={"title": "テストタスク", "description": "詳細"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["title"] == "テストタスク"
        assert data["state"] == "pending"

    def test_create_task_run_not_found(self, client):
        """存在しないRunへのTask作成で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/tasks",
            json={"title": "タスク"},
        )

        # Assert
        assert response.status_code == 404

    def test_list_tasks(self, client):
        """Task一覧を取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "タスク一覧テスト"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/tasks", json={"title": "タスク1"})
        client.post(f"/runs/{run_id}/tasks", json={"title": "タスク2"})

        # Act
        response = client.get(f"/runs/{run_id}/tasks")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_tasks_run_not_found(self, client):
        """存在しないRunのTask一覧で404を返す"""
        # Act
        response = client.get("/runs/nonexistent/tasks")

        # Assert
        assert response.status_code == 404

    def test_list_tasks_completed_run(self, client):
        """完了したRunのTask一覧も取得できる"""
        # Arrange: Runを作成してタスクを追加し、Runを完了する
        run_resp = client.post("/runs", json={"goal": "完了Run確認テスト"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/tasks", json={"title": "完了前タスク"})
        client.post(f"/runs/{run_id}/complete")

        # Act: 完了したRunのタスク一覧を取得
        response = client.get(f"/runs/{run_id}/tasks")

        # Assert: 200 OKでタスク一覧が返される
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "完了前タスク"

    def test_complete_task(self, client):
        """Taskを完了できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "タスク完了テスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "完了タスク"})
        task_id = task_resp.json()["task_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/{task_id}/complete",
            json={"result": {"key": "value"}},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["task_id"] == task_id

    def test_complete_task_run_not_found(self, client):
        """存在しないRunのTask完了で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/tasks/task-123/complete",
            json={"result": {}},
        )

        # Assert
        assert response.status_code == 404

    def test_complete_task_not_found(self, client):
        """存在しないTaskの完了で404を返す"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/nonexistent-task/complete",
            json={"result": {}},
        )

        # Assert
        assert response.status_code == 404

    def test_fail_task(self, client):
        """Taskを失敗させることができる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "タスク失敗テスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "失敗タスク"})
        task_id = task_resp.json()["task_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/{task_id}/fail",
            json={"error": "エラーが発生", "retryable": False},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["task_id"] == task_id

    def test_fail_task_run_not_found(self, client):
        """存在しないRunのTask失敗で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/tasks/task-123/fail",
            json={"error": "エラー"},
        )

        # Assert
        assert response.status_code == 404

    def test_fail_task_not_found(self, client):
        """存在しないTaskの失敗で404を返す"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/nonexistent-task/fail",
            json={"error": "エラー"},
        )

        # Assert
        assert response.status_code == 404


class TestEventsEndpoint:
    """Events関連エンドポイントのテスト"""

    def test_get_events(self, client):
        """イベント一覧を取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "イベントテスト"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/tasks", json={"title": "タスク"})

        # Act
        response = client.get(f"/runs/{run_id}/events")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2  # RunStarted + TaskCreated

    def test_get_events_with_limit(self, client):
        """イベントを制限して取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "リミットテスト"})
        run_id = run_resp.json()["run_id"]
        for i in range(5):
            client.post(f"/runs/{run_id}/tasks", json={"title": f"タスク{i}"})

        # Act
        response = client.get(f"/runs/{run_id}/events?limit=3")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestLineageEndpoint:
    """Lineage関連エンドポイントのテスト"""

    def test_get_lineage_basic(self, client):
        """因果リンクを取得できる"""
        # Arrange: Runを開始してイベントを取得
        run_resp = client.post("/runs", json={"goal": "リネージュテスト"})
        run_id = run_resp.json()["run_id"]

        # イベント一覧を取得
        events_resp = client.get(f"/runs/{run_id}/events")
        events = events_resp.json()
        event_id = events[0]["id"]

        # Act
        response = client.get(f"/runs/{run_id}/events/{event_id}/lineage")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event_id
        assert "ancestors" in data
        assert "descendants" in data
        assert "truncated" in data

    def test_get_lineage_event_not_found(self, client):
        """存在しないイベントのlineageで404を返す"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "エラーテスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.get(f"/runs/{run_id}/events/nonexistent-event/lineage")

        # Assert
        assert response.status_code == 404

    def test_get_lineage_with_direction(self, client):
        """方向を指定してlineageを取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "方向テスト"})
        run_id = run_resp.json()["run_id"]
        events_resp = client.get(f"/runs/{run_id}/events")
        event_id = events_resp.json()[0]["id"]

        # Act
        response = client.get(f"/runs/{run_id}/events/{event_id}/lineage?direction=ancestors")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event_id

    def test_get_lineage_with_max_depth(self, client):
        """max_depthを指定してlineageを取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "深さテスト"})
        run_id = run_resp.json()["run_id"]
        events_resp = client.get(f"/runs/{run_id}/events")
        event_id = events_resp.json()[0]["id"]

        # Act
        response = client.get(f"/runs/{run_id}/events/{event_id}/lineage?max_depth=5")

        # Assert
        assert response.status_code == 200


class TestLineageWithParents:
    """parents付きイベントでのlineageテスト"""

    def test_lineage_finds_ancestors_with_parents(self, client, tmp_path):
        """parentsを持つイベントの祖先を取得できる"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "祖先テスト"})
        run_id = run_resp.json()["run_id"]

        # イベント一覧を取得して最初のイベントIDを取得
        events_resp = client.get(f"/runs/{run_id}/events")
        first_event_id = events_resp.json()[0]["id"]

        # parentsを持つイベントを直接追加
        import hiveforge.api.helpers as helpers_module
        from hiveforge.core.events import HeartbeatEvent

        ar = helpers_module.get_ar()
        # 2番目のイベント：最初のイベントを親に持つ
        event2 = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=[first_event_id],
        )
        ar.append(event2, run_id)

        # 3番目のイベント：2番目のイベントを親に持つ
        event3 = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=[event2.id],
        )
        ar.append(event3, run_id)

        # Act: 3番目のイベントの祖先を取得
        response = client.get(f"/runs/{run_id}/events/{event3.id}/lineage?direction=ancestors")

        # Assert: 祖先に2番目と1番目が含まれる
        assert response.status_code == 200
        data = response.json()
        assert event2.id in data["ancestors"]
        assert first_event_id in data["ancestors"]

    def test_lineage_finds_descendants_with_parents(self, client, tmp_path):
        """子孫を取得できる"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "子孫テスト"})
        run_id = run_resp.json()["run_id"]

        # イベント一覧を取得して最初のイベントIDを取得
        events_resp = client.get(f"/runs/{run_id}/events")
        first_event_id = events_resp.json()[0]["id"]

        import hiveforge.api.helpers as helpers_module
        from hiveforge.core.events import HeartbeatEvent

        ar = helpers_module.get_ar()
        # 子イベント：最初のイベントを親に持つ
        child_event = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=[first_event_id],
        )
        ar.append(child_event, run_id)

        # Act: 最初のイベントの子孫を取得
        response = client.get(
            f"/runs/{run_id}/events/{first_event_id}/lineage?direction=descendants"
        )

        # Assert: 子孫に子イベントが含まれる
        assert response.status_code == 200
        data = response.json()
        assert child_event.id in data["descendants"]

    def test_lineage_truncated_when_depth_exceeded(self, client, tmp_path):
        """深度制限を超えるとtruncatedになる"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "深度テスト"})
        run_id = run_resp.json()["run_id"]

        events_resp = client.get(f"/runs/{run_id}/events")
        first_event_id = events_resp.json()[0]["id"]

        import hiveforge.api.helpers as helpers_module
        from hiveforge.core.events import HeartbeatEvent

        ar = helpers_module.get_ar()

        # 深いチェーンを作成
        prev_id = first_event_id
        for _ in range(5):
            event = HeartbeatEvent(
                run_id=run_id,
                actor="test",
                parents=[prev_id],
            )
            ar.append(event, run_id)
            prev_id = event.id

        # Act: 最後のイベントの祖先をmax_depth=2で取得
        response = client.get(
            f"/runs/{run_id}/events/{prev_id}/lineage?direction=ancestors&max_depth=2"
        )

        # Assert: truncatedがTrue
        assert response.status_code == 200
        data = response.json()
        assert data["truncated"] is True

    def test_lineage_descendants_depth_truncated(self, client, tmp_path):
        """子孫探索で深度制限を超えるとtruncatedになる"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "子孫深度テスト"})
        run_id = run_resp.json()["run_id"]

        events_resp = client.get(f"/runs/{run_id}/events")
        first_event_id = events_resp.json()[0]["id"]

        import hiveforge.api.helpers as helpers_module
        from hiveforge.core.events import HeartbeatEvent

        ar = helpers_module.get_ar()

        # 深いチェーンを作成（最初のイベントの子孫を作る）
        prev_id = first_event_id
        for _ in range(5):
            event = HeartbeatEvent(
                run_id=run_id,
                actor="test",
                parents=[prev_id],
            )
            ar.append(event, run_id)
            prev_id = event.id

        # Act: 最初のイベントの子孫をmax_depth=2で取得
        response = client.get(
            f"/runs/{run_id}/events/{first_event_id}/lineage?direction=descendants&max_depth=2"
        )

        # Assert: truncatedがTrue
        assert response.status_code == 200
        data = response.json()
        assert data["truncated"] is True

    def test_lineage_with_parent_not_in_run(self, client, tmp_path):
        """存在しない親を持つイベントでもエラーにならない"""
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "存在しない親テスト"})
        run_id = run_resp.json()["run_id"]

        import hiveforge.api.helpers as helpers_module
        from hiveforge.core.events import HeartbeatEvent

        ar = helpers_module.get_ar()

        # 存在しない親を持つイベントを作成
        event = HeartbeatEvent(
            run_id=run_id,
            actor="test",
            parents=["nonexistent-parent-id"],
        )
        ar.append(event, run_id)

        # Act
        response = client.get(f"/runs/{run_id}/events/{event.id}/lineage?direction=ancestors")

        # Assert: エラーにならない（存在しない親はスキップされる）
        assert response.status_code == 200


class TestHeartbeatEndpoint:
    """ハートビートエンドポイントのテスト"""

    def test_send_heartbeat(self, client):
        """ハートビートを送信できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "ハートビートテスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(f"/runs/{run_id}/heartbeat")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_send_heartbeat_run_not_found(self, client):
        """存在しないRunへのハートビートで404を返す"""
        # Act
        response = client.post("/runs/nonexistent/heartbeat")

        # Assert
        assert response.status_code == 404


class TestGetArFunction:
    """get_ar関数のテスト"""

    def test_get_ar_creates_instance(self, tmp_path):
        """ARインスタンスを作成する"""
        # Arrange
        import hiveforge.api.helpers as helpers_module

        set_ar(None)

        with patch("hiveforge.api.helpers.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.return_value = mock_s

            # Act
            ar = get_ar()

            # Assert
            assert ar is not None

        # Cleanup
        set_ar(None)

    def test_get_ar_returns_existing(self, tmp_path):
        """既存のARインスタンスを返す"""
        # Arrange
        import hiveforge.api.helpers as helpers_module

        mock_ar = MagicMock()
        set_ar(mock_ar)

        # Act
        ar = get_ar()

        # Assert
        assert ar is mock_ar

        # Cleanup
        set_ar(None)


class TestLifespanRunRecovery:
    """lifespan時のRun復元のテスト"""

    def test_lifespan_recovers_running_runs(self, tmp_path):
        """起動時にRUNNING状態のRunを復元する"""
        from hiveforge.core.ar.storage import AkashicRecord
        from hiveforge.core.events import RunStartedEvent

        # 事前にRunを作成
        vault_path = tmp_path / "Vault"
        ar = AkashicRecord(vault_path)
        event = RunStartedEvent(
            run_id="recovery-run-001",
            actor="test",
            payload={"goal": "Recovery test"},
        )
        ar.append(event, "recovery-run-001")

        # グローバル状態をクリア
        set_ar(None)
        clear_active_runs()

        # server.py と helpers.py の両方で使用される get_settings をモック
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = vault_path
        mock_s.server.cors.enabled = False

        with (
            patch("hiveforge.api.server.get_settings", return_value=mock_s),
            patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        ):
            # Act
            with TestClient(app) as client:
                # Assert: 復元されたRunがアクティブに追加されている
                assert "recovery-run-001" in get_active_runs()
                proj = get_active_runs()["recovery-run-001"]
                assert proj.goal == "Recovery test"

        # Cleanup
        set_ar(None)
        clear_active_runs()


class TestGetRunFromInactiveRun:
    """非アクティブなRunの取得テスト"""

    def test_get_run_completed_run(self, client):
        """完了したRunの詳細を取得できる"""
        # Arrange: Runを作成して完了させる
        run_resp = client.post("/runs", json={"goal": "完了済みRun"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/complete")

        # runを_active_runsから削除されていることを確認
        import hiveforge.api.helpers as helpers_module

        assert run_id not in get_active_runs()

        # Act: 完了したRunを取得
        response = client.get(f"/runs/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["state"] == "completed"

    def test_get_events_completed_run(self, client):
        """完了したRunのイベント一覧も取得できる"""
        # Arrange: Runを作成してタスクを追加・完了し、Runを完了する
        run_resp = client.post("/runs", json={"goal": "完了Runイベント確認"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "イベント確認用タスク"})
        task_id = task_resp.json()["task_id"]
        client.post(f"/runs/{run_id}/tasks/{task_id}/complete", json={})
        client.post(f"/runs/{run_id}/complete")

        # Act: 完了したRunのイベント一覧を取得
        response = client.get(f"/runs/{run_id}/events")

        # Assert: 200 OKでイベント一覧が返される
        assert response.status_code == 200
        data = response.json()
        # run.started, task.created, task.completed, run.completed の4イベント
        assert len(data) >= 4
        types = [e["type"] for e in data]
        assert "run.started" in types
        assert "task.created" in types
        assert "run.completed" in types

    def test_get_requirements_completed_run(self, client):
        """完了したRunの確認要請一覧も取得できる"""
        # Arrange: Runを作成して確認要請を追加し、Runを完了する
        run_resp = client.post("/runs", json={"goal": "完了Run確認要請確認"})
        run_id = run_resp.json()["run_id"]
        client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "テスト確認要請", "options": ["A", "B"]},
        )
        client.post(f"/runs/{run_id}/complete")

        # Act: 完了したRunの確認要請一覧を取得
        response = client.get(f"/runs/{run_id}/requirements")

        # Assert: 200 OKで確認要請一覧が返される
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["description"] == "テスト確認要請"

    def test_create_task_on_completed_run_fails(self, client):
        """完了したRunへのタスク作成は404を返す"""
        # Arrange: Runを作成して完了する
        run_resp = client.post("/runs", json={"goal": "完了Run書き込み拒否テスト"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/complete")

        # Act: 完了したRunにタスクを作成しようとする
        response = client.post(f"/runs/{run_id}/tasks", json={"title": "新タスク"})

        # Assert: 404 Not Found（アクティブRunではないため）
        assert response.status_code == 404

    def test_create_requirement_on_completed_run_fails(self, client):
        """完了したRunへの確認要請作成は404を返す"""
        # Arrange: Runを作成して完了する
        run_resp = client.post("/runs", json={"goal": "完了Run書き込み拒否テスト"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/complete")

        # Act: 完了したRunに確認要請を作成しようとする
        response = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "テスト"},
        )

        # Assert: 404 Not Found（アクティブRunではないため）
        assert response.status_code == 404


class TestListRunsEdgeCases:
    """list_runsのエッジケースのテスト"""

    def test_list_runs_with_empty_events_file(self, tmp_path):
        """空のevents.jsonlがあるRunがリストから除外される"""
        vault_path = tmp_path / "Vault"
        vault_path.mkdir(parents=True, exist_ok=True)

        # 空のevents.jsonlを直接作成（list_runsでは表示されるが、eventsがない）
        runs_dir = vault_path / "empty-run"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "events.jsonl").touch()  # 空のファイル

        set_ar(None)
        clear_active_runs()

        # server.py と helpers.py の両方で使用される get_settings をモック
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = vault_path
        mock_s.server.cors.enabled = False

        with (
            patch("hiveforge.api.server.get_settings", return_value=mock_s),
            patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        ):
            with TestClient(app) as client:
                # Act: 全てのRunをリスト
                response = client.get("/runs?active_only=false")

                # Assert: 空のRunはリストに含まれない(projがNoneになるため)
                assert response.status_code == 200
                data = response.json()
                # 空のRunはprojがNoneなので結果に含まれない
                run_ids = [run["run_id"] for run in data]
                assert "empty-run" not in run_ids

        # Cleanup
        set_ar(None)
        clear_active_runs()


class TestLifespanNoRuns:
    """Runがない状態でのlifespan"""

    def test_lifespan_with_no_existing_runs(self, tmp_path):
        """既存のRunがない場合も正常に起動する"""
        vault_path = tmp_path / "EmptyVault"
        vault_path.mkdir(parents=True, exist_ok=True)

        set_ar(None)
        clear_active_runs()

        # server.py と helpers.py の両方で使用される get_settings をモック
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = vault_path
        mock_s.server.cors.enabled = False

        with (
            patch("hiveforge.api.server.get_settings", return_value=mock_s),
            patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        ):
            # Act & Assert: エラーなく起動
            with TestClient(app) as client:
                response = client.get("/health")
                assert response.status_code == 200
                assert len(get_active_runs()) == 0

        # Cleanup
        set_ar(None)
        clear_active_runs()

    def test_lifespan_with_completed_run_only(self, tmp_path):
        """COMPLETEDのRunのみの場合、アクティブに追加されない"""
        from hiveforge.core.ar.storage import AkashicRecord
        from hiveforge.core.events import RunStartedEvent, RunCompletedEvent

        vault_path = tmp_path / "CompletedVault"
        ar = AkashicRecord(vault_path)

        # 完了済みRunを作成
        run_id = "completed-run-001"
        start_event = RunStartedEvent(
            run_id=run_id,
            actor="test",
            payload={"goal": "Completed run test"},
        )
        ar.append(start_event, run_id)

        complete_event = RunCompletedEvent(
            run_id=run_id,
            actor="test",
        )
        ar.append(complete_event, run_id)

        set_ar(None)
        clear_active_runs()

        # server.py と helpers.py の両方で使用される get_settings をモック
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = vault_path
        mock_s.server.cors.enabled = False

        with (
            patch("hiveforge.api.server.get_settings", return_value=mock_s),
            patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        ):
            # Act
            with TestClient(app) as client:
                # Assert: 完了済みRunはアクティブに追加されない
                assert run_id not in get_active_runs()

        # Cleanup
        set_ar(None)
        clear_active_runs()


class TestAssignTaskEndpoint:
    """Task割り当てエンドポイントのテスト"""

    def test_assign_task(self, client):
        """Taskを担当者に割り当てできる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "割り当てテスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "タスク1"})
        task_id = task_resp.json()["task_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/{task_id}/assign",
            json={"assignee": "agent-001"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "assigned"
        assert data["task_id"] == task_id
        assert data["assignee"] == "agent-001"

    def test_assign_task_run_not_found(self, client):
        """存在しないRunのTask割り当てで404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/tasks/task-123/assign",
            json={"assignee": "agent-001"},
        )

        # Assert
        assert response.status_code == 404

    def test_assign_task_not_found(self, client):
        """存在しないTaskの割り当てで404を返す"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/nonexistent-task/assign",
            json={"assignee": "agent-001"},
        )

        # Assert
        assert response.status_code == 404


class TestReportProgressEndpoint:
    """進捗報告エンドポイントのテスト"""

    def test_report_progress(self, client):
        """Taskの進捗を報告できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "進捗テスト"})
        run_id = run_resp.json()["run_id"]
        task_resp = client.post(f"/runs/{run_id}/tasks", json={"title": "タスク1"})
        task_id = task_resp.json()["task_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/{task_id}/progress",
            json={"progress": 50, "message": "半分完了"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["task_id"] == task_id
        assert data["progress"] == 50

    def test_report_progress_run_not_found(self, client):
        """存在しないRunの進捗報告で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/tasks/task-123/progress",
            json={"progress": 50},
        )

        # Assert
        assert response.status_code == 404

    def test_report_progress_task_not_found(self, client):
        """存在しないTaskの進捗報告で404を返す"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/tasks/nonexistent-task/progress",
            json={"progress": 50},
        )

        # Assert
        assert response.status_code == 404


class TestRequirementsEndpoint:
    """Requirements関連エンドポイントのテスト"""

    def test_create_requirement(self, client):
        """確認要請を作成できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "確認テスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "この変更を承認しますか？", "options": ["はい", "いいえ"]},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "この変更を承認しますか？"
        assert data["state"] == "pending"
        assert data["options"] == ["はい", "いいえ"]

    def test_create_requirement_run_not_found(self, client):
        """存在しないRunの確認要請作成で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/requirements",
            json={"description": "テスト"},
        )

        # Assert
        assert response.status_code == 404

    def test_get_requirements(self, client):
        """確認要請一覧を取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "確認テスト"})
        run_id = run_resp.json()["run_id"]
        client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "要請1"},
        )

        # Act
        response = client.get(f"/runs/{run_id}/requirements")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["description"] == "要請1"
        assert data[0]["state"] == "pending"

    def test_get_requirements_run_not_found(self, client):
        """存在しないRunの確認要請一覧取得で404を返す"""
        # Act
        response = client.get("/runs/nonexistent-run/requirements")

        # Assert
        assert response.status_code == 404

    def test_get_requirements_pending_only(self, client):
        """pending_only=trueで保留中のみ取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "確認テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "要請1"},
        )
        req_id = req_resp.json()["id"]

        # 1つ承認
        client.post(
            f"/runs/{run_id}/requirements/{req_id}/resolve",
            json={"approved": True},
        )

        # もう1つ作成
        client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "要請2"},
        )

        # Act
        response = client.get(f"/runs/{run_id}/requirements?pending_only=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["description"] == "要請2"

    def test_get_requirements_includes_resolved(self, client):
        """pending_only=falseで解決済みも含めて取得できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "確認テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "要請1"},
        )
        req_id = req_resp.json()["id"]

        # 承認
        client.post(
            f"/runs/{run_id}/requirements/{req_id}/resolve",
            json={"approved": True, "comment": "承認コメント"},
        )

        # Act
        response = client.get(f"/runs/{run_id}/requirements")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["description"] == "要請1"
        assert data[0]["state"] == "approved"
        assert data[0]["comment"] == "承認コメント"

    def test_resolve_requirement_approve(self, client):
        """確認要請を承認できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "承認テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "承認しますか？", "options": ["オプション1", "オプション2"]},
        )
        req_id = req_resp.json()["id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/requirements/{req_id}/resolve",
            json={"approved": True, "selected_option": "オプション1", "comment": "承認します"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"

    def test_resolve_requirement_reject(self, client):
        """確認要請を却下できる"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "却下テスト"})
        run_id = run_resp.json()["run_id"]
        req_resp = client.post(
            f"/runs/{run_id}/requirements",
            json={"description": "承認しますか？"},
        )
        req_id = req_resp.json()["id"]

        # Act
        response = client.post(
            f"/runs/{run_id}/requirements/{req_id}/resolve",
            json={"approved": False, "comment": "却下します"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"

    def test_resolve_requirement_run_not_found(self, client):
        """存在しないRunの確認要請解決で404を返す"""
        # Act
        response = client.post(
            "/runs/nonexistent/requirements/req-123/resolve",
            json={"approved": True},
        )

        # Assert
        assert response.status_code == 404
