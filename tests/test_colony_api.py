"""Colony REST API エンドポイントのテスト

GitHub Issue #8: P1-07: Colony REST API エンドポイント
"""

import pytest
from fastapi.testclient import TestClient


class TestColonyRoutes:
    """Colony REST APIルートのテスト"""

    @pytest.fixture
    def hive_id(self, client):
        """テスト用Hiveを作成"""
        response = client.post("/hives", json={"name": "TestHive"})
        return response.json()["hive_id"]

    def test_create_colony(self, client, hive_id):
        """POST /hives/{hive_id}/colonies でColonyを作成できる"""
        # Arrange
        request_data = {
            "name": "テストColony",
            "goal": "テスト用の目標",
        }

        # Act
        response = client.post(f"/hives/{hive_id}/colonies", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "colony_id" in data
        assert data["name"] == "テストColony"
        assert data["hive_id"] == hive_id

    def test_create_colony_hive_not_found(self, client):
        """存在しないHiveにColonyを作成すると404"""
        # Act
        response = client.post("/hives/nonexistent/colonies", json={"name": "Colony"})

        # Assert
        assert response.status_code == 404

    def test_list_colonies(self, client, hive_id):
        """GET /hives/{hive_id}/colonies でColony一覧を取得できる"""
        # Arrange: Colonyを作成
        client.post(f"/hives/{hive_id}/colonies", json={"name": "Colony1"})
        client.post(f"/hives/{hive_id}/colonies", json={"name": "Colony2"})

        # Act
        response = client.get(f"/hives/{hive_id}/colonies")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_colony_by_id(self, client, hive_id):
        """GET /hives/{hive_id}/colonies/{colony_id} でColony詳細を取得できる"""
        # Arrange: Colonyを作成
        create_response = client.post(f"/hives/{hive_id}/colonies", json={"name": "詳細テスト"})
        colony_id = create_response.json()["colony_id"]

        # Act
        response = client.get(f"/hives/{hive_id}/colonies/{colony_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["colony_id"] == colony_id
        assert data["name"] == "詳細テスト"

    def test_get_colony_not_found(self, client, hive_id):
        """存在しないColonyは404を返す"""
        # Act
        response = client.get(f"/hives/{hive_id}/colonies/nonexistent")

        # Assert
        assert response.status_code == 404


class TestColonyLifecycle:
    """Colonyライフサイクルのテスト"""

    @pytest.fixture
    def colony_id(self, client):
        """テスト用HiveとColonyを作成"""
        hive_response = client.post("/hives", json={"name": "TestHive"})
        hive_id = hive_response.json()["hive_id"]
        colony_response = client.post(f"/hives/{hive_id}/colonies", json={"name": "TestColony"})
        return colony_response.json()["colony_id"]

    def test_start_colony(self, client, colony_id):
        """POST /colonies/{colony_id}/start でColonyを開始できる"""
        # Act
        response = client.post(f"/colonies/{colony_id}/start")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["colony_id"] == colony_id

    def test_start_colony_not_found(self, client):
        """存在しないColonyの開始は404"""
        # Act
        response = client.post("/colonies/nonexistent/start")

        # Assert
        assert response.status_code == 404

    def test_complete_colony(self, client, colony_id):
        """POST /colonies/{colony_id}/complete でColonyを完了できる"""
        # Arrange: まずColonyを開始
        client.post(f"/colonies/{colony_id}/start")

        # Act
        response = client.post(f"/colonies/{colony_id}/complete")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["colony_id"] == colony_id

    def test_complete_colony_not_found(self, client):
        """存在しないColonyの完了は404"""
        # Act
        response = client.post("/colonies/nonexistent/complete")

        # Assert
        assert response.status_code == 404
