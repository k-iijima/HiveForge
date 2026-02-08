"""Hive REST API エンドポイントのテスト

GitHub Issue #7: P1-06: Hive REST API エンドポイント
"""


class TestHiveRoutes:
    """Hive REST APIルートのテスト"""

    def test_hives_router_exists(self, client):
        """/hives エンドポイントが存在する"""
        # Act: /hivesにGET
        response = client.get("/hives")

        # Assert: 404ではなく200を返す
        assert response.status_code == 200

    def test_create_hive(self, client):
        """POST /hives でHiveを作成できる"""
        # Arrange
        request_data = {
            "name": "テストHive",
            "description": "テスト用のHive",
        }

        # Act
        response = client.post("/hives", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "hive_id" in data
        assert data["name"] == "テストHive"

    def test_create_hive_minimal(self, client):
        """最小限の情報でHiveを作成できる"""
        # Arrange: nameのみ
        request_data = {"name": "最小Hive"}

        # Act
        response = client.post("/hives", json=request_data)

        # Assert
        assert response.status_code == 201
        assert response.json()["name"] == "最小Hive"

    def test_get_hives_list(self, client):
        """GET /hives でHive一覧を取得できる"""
        # Arrange: いくつかのHiveを作成
        client.post("/hives", json={"name": "Hive1"})
        client.post("/hives", json={"name": "Hive2"})

        # Act
        response = client.get("/hives")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_hive_by_id(self, client):
        """GET /hives/{hive_id} でHive詳細を取得できる"""
        # Arrange: Hiveを作成
        create_response = client.post("/hives", json={"name": "詳細テスト"})
        hive_id = create_response.json()["hive_id"]

        # Act
        response = client.get(f"/hives/{hive_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["hive_id"] == hive_id
        assert data["name"] == "詳細テスト"

    def test_get_hive_not_found(self, client):
        """存在しないHiveは404を返す"""
        # Act
        response = client.get("/hives/nonexistent-hive")

        # Assert
        assert response.status_code == 404

    def test_close_hive(self, client):
        """POST /hives/{hive_id}/close でHiveを終了できる"""
        # Arrange: Hiveを作成
        create_response = client.post("/hives", json={"name": "終了テスト"})
        hive_id = create_response.json()["hive_id"]

        # Act
        response = client.post(f"/hives/{hive_id}/close")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "closed"
        assert data["hive_id"] == hive_id

    def test_close_hive_not_found(self, client):
        """存在しないHiveの終了は404を返す"""
        # Act
        response = client.post("/hives/nonexistent-hive/close")

        # Assert
        assert response.status_code == 404


class TestHiveWithColonies:
    """HiveとColonyの関連テスト"""

    def test_hive_includes_colonies(self, client):
        """Hive詳細にはColony一覧が含まれる"""
        # Arrange: HiveとColonyを作成
        create_response = client.post("/hives", json={"name": "ColonyテストHive"})
        hive_id = create_response.json()["hive_id"]

        # Colonyを作成（/colonies エンドポイントがあると仮定）
        # 今はhive_idとの紐付けのテストのみ

        # Act
        response = client.get(f"/hives/{hive_id}")

        # Assert
        data = response.json()
        assert "colonies" in data
        assert isinstance(data["colonies"], list)
