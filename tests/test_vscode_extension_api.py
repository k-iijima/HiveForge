"""M2-1-f: VS Code拡張 動作保証テスト

VS Code拡張がAPI経由で行う操作を統合テストで検証する。

完了条件:
- VS Code拡張からHive/Colonyの作成・取得・終了ができる
- API接続失敗時にユーザーへ適切なエラー通知が出る

VS Code拡張の client.ts が呼び出すAPIエンドポイントを、
FastAPI TestClientで模擬し、全操作フローが正常に動作することを確認する。
"""


class TestVSCodeExtensionHiveFlow:
    """VS Code拡張のHive操作フロー

    client.ts の以下メソッドに対応:
    - getHives()     → GET /hives
    - getHive(id)    → GET /hives/{id}
    - createHive()   → POST /hives
    - closeHive(id)  → POST /hives/{id}/close
    """

    def test_full_hive_lifecycle(self, client):
        """Hiveの作成→取得→終了の完全フロー

        VS Code拡張のcreateHive→getHive→closeHiveの流れを再現。
        """
        # Arrange / Act: Hiveを作成（createHive相当）
        create_response = client.post(
            "/hives",
            json={"name": "VS Code Hive", "description": "拡張からの作成テスト"},
        )

        # Assert: 作成成功
        assert create_response.status_code == 201
        hive_data = create_response.json()
        hive_id = hive_data["hive_id"]
        assert hive_data["name"] == "VS Code Hive"

        # Act: Hive一覧取得（getHives相当）
        list_response = client.get("/hives")

        # Assert: 作成したHiveが一覧に含まれる
        assert list_response.status_code == 200
        hive_ids = [h["hive_id"] for h in list_response.json()]
        assert hive_id in hive_ids

        # Act: 個別Hive取得（getHive相当）
        get_response = client.get(f"/hives/{hive_id}")

        # Assert: 正しいHiveが返る
        assert get_response.status_code == 200
        assert get_response.json()["hive_id"] == hive_id
        assert get_response.json()["name"] == "VS Code Hive"

        # Act: Hive終了（closeHive相当）
        close_response = client.post(f"/hives/{hive_id}/close")

        # Assert: 終了成功
        assert close_response.status_code == 200
        assert close_response.json()["status"] == "closed"

    def test_get_nonexistent_hive_returns_404(self, client):
        """存在しないHiveの取得は404

        VS Code拡張側のエラーハンドリング（showErrorMessage）の検証基盤。
        """
        # Act
        response = client.get("/hives/nonexistent-hive-id")

        # Assert: 404でクライアントがエラー表示可能
        assert response.status_code == 404

    def test_close_nonexistent_hive_returns_404(self, client):
        """存在しないHiveの終了は404"""
        # Act
        response = client.post("/hives/nonexistent-hive-id/close")

        # Assert
        assert response.status_code == 404

    def test_create_hive_without_name_fails(self, client):
        """名前なしのHive作成はバリデーションエラー

        VS Code拡張側のvalidateInputに対応する
        サーバー側バリデーション。
        """
        # Act
        response = client.post("/hives", json={})

        # Assert: 422 Validation Error
        assert response.status_code == 422


class TestVSCodeExtensionColonyFlow:
    """VS Code拡張のColony操作フロー

    client.ts の以下メソッドに対応:
    - getColonies(hiveId)     → GET /hives/{hiveId}/colonies
    - createColony(hiveId)    → POST /hives/{hiveId}/colonies
    - startColony(colonyId)   → POST /colonies/{colonyId}/start
    - completeColony(colonyId)→ POST /colonies/{colonyId}/complete
    """

    def test_full_colony_lifecycle(self, client):
        """Colonyの作成→開始→完了の完全フロー

        VS Code拡張のcreateColony→startColony→completeColonyの流れを再現。
        """
        # Arrange: Hiveを作成（Colony作成の前提条件）
        hive_response = client.post("/hives", json={"name": "Colony Test Hive"})
        hive_id = hive_response.json()["hive_id"]

        # Act: Colony作成（createColony相当）
        create_response = client.post(
            f"/hives/{hive_id}/colonies",
            json={"name": "Feature-A Colony", "goal": "機能Aの実装"},
        )

        # Assert: 作成成功
        assert create_response.status_code == 201
        colony_data = create_response.json()
        colony_id = colony_data["colony_id"]
        assert colony_data["name"] == "Feature-A Colony"
        assert colony_data["hive_id"] == hive_id

        # Act: Colony一覧取得（getColonies相当）
        list_response = client.get(f"/hives/{hive_id}/colonies")

        # Assert: 作成したColonyが一覧に含まれる
        assert list_response.status_code == 200
        colony_ids = [c["colony_id"] for c in list_response.json()]
        assert colony_id in colony_ids

        # Act: Colony開始（startColony相当）
        start_response = client.post(f"/colonies/{colony_id}/start")

        # Assert: 開始成功
        assert start_response.status_code == 200
        assert start_response.json()["status"] == "running"

        # Act: Colony完了（completeColony相当）
        complete_response = client.post(f"/colonies/{colony_id}/complete")

        # Assert: 完了成功
        assert complete_response.status_code == 200
        assert complete_response.json()["status"] == "completed"

    def test_create_colony_for_nonexistent_hive_fails(self, client):
        """存在しないHiveへのColony作成は404"""
        # Act
        response = client.post(
            "/hives/nonexistent/colonies",
            json={"name": "Orphan Colony"},
        )

        # Assert
        assert response.status_code == 404

    def test_start_nonexistent_colony_fails(self, client):
        """存在しないColonyの開始は404"""
        # Act
        response = client.post("/colonies/nonexistent/start")

        # Assert
        assert response.status_code == 404

    def test_complete_nonexistent_colony_fails(self, client):
        """存在しないColonyの完了は404"""
        # Act
        response = client.post("/colonies/nonexistent/complete")

        # Assert
        assert response.status_code == 404


class TestVSCodeExtensionHealthCheck:
    """VS Code拡張のヘルスチェック

    client.ts の getHealth() → GET /health に対応。
    サーバー接続確認として拡張が最初に呼び出すエンドポイント。
    """

    def test_health_check_returns_expected_fields(self, client):
        """HealthResponseの全フィールドが返される

        client.ts のHealthResponseインターフェースに対応:
        - status: string
        - version: string
        - active_runs: number
        """
        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "active_runs" in data
        assert data["status"] == "healthy"


class TestVSCodeExtensionErrorHandling:
    """API接続エラー時の挙動テスト

    VS Code拡張のエラーハンドリングの前提条件:
    - 無効なリクエストに対して適切なHTTPステータスコードが返される
    - エラーレスポンスにdetailメッセージが含まれる
    """

    def test_invalid_json_returns_422(self, client):
        """不正なJSONでは422 Validation Error"""
        # Act
        response = client.post(
            "/hives",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        # Assert: 422でクライアントがエラーメッセージを表示できる
        assert response.status_code == 422

    def test_hive_error_response_has_detail(self, client):
        """エラーレスポンスにdetailフィールドが含まれる

        VS Code拡張のextractErrorMessage()で使用される。
        """
        # Act: 存在しないHive取得で404
        response = client.get("/hives/nonexistent")

        # Assert: detailが含まれる
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_colony_error_response_has_detail(self, client):
        """Colonyエラーレスポンスにもdetailフィールドが含まれる"""
        # Act: 存在しないColony開始で404
        response = client.post("/colonies/nonexistent/start")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_beekeeper_send_message_validation_error(self, client):
        """Beekeeper空メッセージはバリデーションエラー

        chatHandler.ts でユーザーの空入力を弾くサーバー側ガード。
        """
        # Act
        response = client.post(
            "/beekeeper/send_message",
            json={"message": ""},
        )

        # Assert
        assert response.status_code == 422
