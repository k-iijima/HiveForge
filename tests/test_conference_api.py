"""
Conference API テスト

Conference REST APIのテスト。
"""

import pytest
from fastapi.testclient import TestClient

from hiveforge.api.routes.conferences import get_conference_store
from hiveforge.api.server import app


@pytest.fixture
def client():
    """テスト用HTTPクライアント"""
    # ストアをクリア
    get_conference_store().clear()
    return TestClient(app)


class TestConferenceAPI:
    """Conference REST API のテスト"""

    def test_start_conference(self, client: TestClient):
        """会議を開始できる

        Arrange: 有効なリクエストデータ
        Act: POST /conferences
        Assert: 201で会議が作成される
        """
        # Arrange
        request_data = {
            "hive_id": "hive-001",
            "topic": "プロジェクト設計会議",
            "participants": ["ui-colony", "api-colony"],
        }

        # Act
        response = client.post("/conferences", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["hive_id"] == "hive-001"
        assert data["topic"] == "プロジェクト設計会議"
        assert data["state"] == "active"
        assert "conference_id" in data

    def test_list_conferences(self, client: TestClient):
        """会議一覧を取得できる

        Arrange: 複数の会議を作成
        Act: GET /conferences
        Assert: 全ての会議が取得される
        """
        # Arrange
        for topic in ["会議A", "会議B"]:
            client.post(
                "/conferences",
                json={"hive_id": "hive-001", "topic": topic},
            )

        # Act
        response = client.get("/conferences")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_conferences_by_hive(self, client: TestClient):
        """Hive IDで会議をフィルタできる

        Arrange: 異なるHiveに会議を作成
        Act: GET /conferences?hive_id=hive-001
        Assert: 指定Hiveの会議のみ取得
        """
        # Arrange
        client.post("/conferences", json={"hive_id": "hive-001", "topic": "A"})
        client.post("/conferences", json={"hive_id": "hive-002", "topic": "B"})

        # Act
        response = client.get("/conferences", params={"hive_id": "hive-001"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["hive_id"] == "hive-001"

    def test_get_conference(self, client: TestClient):
        """会議詳細を取得できる

        Arrange: 会議を作成
        Act: GET /conferences/{id}
        Assert: 会議の詳細が取得される
        """
        # Arrange
        create_response = client.post(
            "/conferences",
            json={"hive_id": "hive-001", "topic": "テスト会議"},
        )
        conference_id = create_response.json()["conference_id"]

        # Act
        response = client.get(f"/conferences/{conference_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["conference_id"] == conference_id
        assert data["topic"] == "テスト会議"

    def test_get_conference_not_found(self, client: TestClient):
        """存在しない会議は404

        Arrange: 存在しないID
        Act: GET /conferences/{id}
        Assert: 404エラー
        """
        # Act
        response = client.get("/conferences/nonexistent-id")

        # Assert
        assert response.status_code == 404

    def test_end_conference(self, client: TestClient):
        """会議を終了できる

        Arrange: アクティブな会議を作成
        Act: POST /conferences/{id}/end
        Assert: 会議が終了状態になる
        """
        # Arrange
        create_response = client.post(
            "/conferences",
            json={"hive_id": "hive-001", "topic": "終了テスト会議"},
        )
        conference_id = create_response.json()["conference_id"]

        # Act
        response = client.post(
            f"/conferences/{conference_id}/end",
            json={"summary": "決定事項まとめ", "decisions_made": ["decision-001"]},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "ended"
        assert data["summary"] == "決定事項まとめ"
        assert "decision-001" in data["decisions_made"]

    def test_end_conference_already_ended(self, client: TestClient):
        """終了済み会議の再終了は400

        Arrange: 終了済み会議
        Act: POST /conferences/{id}/end
        Assert: 400エラー
        """
        # Arrange
        create_response = client.post(
            "/conferences",
            json={"hive_id": "hive-001", "topic": "終了テスト"},
        )
        conference_id = create_response.json()["conference_id"]
        client.post(f"/conferences/{conference_id}/end")

        # Act
        response = client.post(f"/conferences/{conference_id}/end")

        # Assert
        assert response.status_code == 400

    def test_list_active_conferences(self, client: TestClient):
        """アクティブな会議のみ取得できる

        Arrange: アクティブと終了済みの会議を作成
        Act: GET /conferences?active_only=true
        Assert: アクティブな会議のみ取得
        """
        # Arrange
        active = client.post(
            "/conferences", json={"hive_id": "hive-001", "topic": "アクティブ"}
        ).json()
        ended = client.post("/conferences", json={"hive_id": "hive-001", "topic": "終了"}).json()
        client.post(f"/conferences/{ended['conference_id']}/end")

        # Act
        response = client.get("/conferences", params={"active_only": True})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["conference_id"] == active["conference_id"]
