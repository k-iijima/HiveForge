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
