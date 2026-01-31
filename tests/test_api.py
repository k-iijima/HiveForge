"""API Server モジュールのテスト"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from hiveforge.api.server import (
    app,
    get_ar,
    _active_runs,
    _ar,
)


@pytest.fixture
def client(tmp_path):
    """テスト用クライアント"""
    # グローバル状態をクリア
    import hiveforge.api.server as server_module

    server_module._ar = None
    server_module._active_runs = {}

    with patch("hiveforge.api.server.get_settings") as mock_settings:
        mock_s = MagicMock()
        mock_s.get_vault_path.return_value = tmp_path / "Vault"
        mock_settings.return_value = mock_s

        with TestClient(app) as client:
            yield client

    # クリーンアップ
    server_module._ar = None
    server_module._active_runs = {}


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
        """Runを完了できる"""
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
        import hiveforge.api.server as server_module
        from hiveforge.core.events import HeartbeatEvent

        ar = server_module.get_ar()
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

        import hiveforge.api.server as server_module
        from hiveforge.core.events import HeartbeatEvent

        ar = server_module.get_ar()
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

        import hiveforge.api.server as server_module
        from hiveforge.core.events import HeartbeatEvent

        ar = server_module.get_ar()

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

        import hiveforge.api.server as server_module
        from hiveforge.core.events import HeartbeatEvent

        ar = server_module.get_ar()

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

        import hiveforge.api.server as server_module
        from hiveforge.core.events import HeartbeatEvent

        ar = server_module.get_ar()

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
        import hiveforge.api.server as server_module

        server_module._ar = None

        with patch("hiveforge.api.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = tmp_path / "Vault"
            mock_settings.return_value = mock_s

            # Act
            ar = get_ar()

            # Assert
            assert ar is not None

        # Cleanup
        server_module._ar = None

    def test_get_ar_returns_existing(self, tmp_path):
        """既存のARインスタンスを返す"""
        # Arrange
        import hiveforge.api.server as server_module

        mock_ar = MagicMock()
        server_module._ar = mock_ar

        # Act
        ar = get_ar()

        # Assert
        assert ar is mock_ar

        # Cleanup
        server_module._ar = None


class TestLifespanRunRecovery:
    """lifespan時のRun復元のテスト"""

    def test_lifespan_recovers_running_runs(self, tmp_path):
        """起動時にRUNNING状態のRunを復元する"""
        # Arrange
        import hiveforge.api.server as server_module
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
        server_module._ar = None
        server_module._active_runs = {}

        with patch("hiveforge.api.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = vault_path
            mock_settings.return_value = mock_s

            # Act
            with TestClient(app) as client:
                # Assert: 復元されたRunがアクティブに追加されている
                assert "recovery-run-001" in server_module._active_runs
                proj = server_module._active_runs["recovery-run-001"]
                assert proj.goal == "Recovery test"

        # Cleanup
        server_module._ar = None
        server_module._active_runs = {}


class TestGetRunFromInactiveRun:
    """非アクティブなRunの取得テスト"""

    def test_get_run_completed_run(self, client):
        """完了したRunの詳細を取得できる"""
        # Arrange: Runを作成して完了させる
        run_resp = client.post("/runs", json={"goal": "完了済みRun"})
        run_id = run_resp.json()["run_id"]
        client.post(f"/runs/{run_id}/complete")

        # runを_active_runsから削除されていることを確認
        import hiveforge.api.server as server_module

        assert run_id not in server_module._active_runs

        # Act: 完了したRunを取得
        response = client.get(f"/runs/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["state"] == "completed"


class TestListRunsEdgeCases:
    """list_runsのエッジケースのテスト"""

    def test_list_runs_with_empty_events_file(self, tmp_path):
        """空のevents.jsonlがあるRunがリストから除外される"""
        # Arrange
        import hiveforge.api.server as server_module

        vault_path = tmp_path / "Vault"
        vault_path.mkdir(parents=True, exist_ok=True)

        # 空のevents.jsonlを直接作成（list_runsでは表示されるが、eventsがない）
        runs_dir = vault_path / "empty-run"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "events.jsonl").touch()  # 空のファイル

        server_module._ar = None
        server_module._active_runs = {}

        with patch("hiveforge.api.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = vault_path
            mock_settings.return_value = mock_s

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
        server_module._ar = None
        server_module._active_runs = {}


class TestLifespanNoRuns:
    """Runがない状態でのlifespan"""

    def test_lifespan_with_no_existing_runs(self, tmp_path):
        """既存のRunがない場合も正常に起動する"""
        # Arrange
        import hiveforge.api.server as server_module

        vault_path = tmp_path / "EmptyVault"
        vault_path.mkdir(parents=True, exist_ok=True)

        server_module._ar = None
        server_module._active_runs = {}

        with patch("hiveforge.api.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = vault_path
            mock_settings.return_value = mock_s

            # Act & Assert: エラーなく起動
            with TestClient(app) as client:
                response = client.get("/health")
                assert response.status_code == 200
                assert len(server_module._active_runs) == 0

        # Cleanup
        server_module._ar = None
        server_module._active_runs = {}

    def test_lifespan_with_completed_run_only(self, tmp_path):
        """COMPLETEDのRunのみの場合、アクティブに追加されない"""
        # Arrange
        import hiveforge.api.server as server_module
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

        server_module._ar = None
        server_module._active_runs = {}

        with patch("hiveforge.api.server.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.get_vault_path.return_value = vault_path
            mock_settings.return_value = mock_s

            # Act
            with TestClient(app) as client:
                # Assert: 完了済みRunはアクティブに追加されない
                assert run_id not in server_module._active_runs

        # Cleanup
        server_module._ar = None
        server_module._active_runs = {}
