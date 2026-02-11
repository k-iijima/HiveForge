"""Beekeeper REST API エンドポイントのテスト

M2-3-a: Copilot Chat @colonyforge → Beekeeper直結
FastAPI /beekeeper/* エンドポイントのテスト。
"""

from unittest.mock import AsyncMock, patch


class TestBeekeeperRoutes:
    """Beekeeper REST APIルートのテスト"""

    def test_send_message_endpoint_exists(self, client):
        """POST /beekeeper/send_message エンドポイントが存在する

        404ではなく、バリデーションエラー(422)か正常応答を返す。
        """
        # Act
        response = client.post("/beekeeper/send_message", json={})

        # Assert: エンドポイント自体は存在する（422 or 200、404でない）
        assert response.status_code != 404

    def test_send_message_requires_message(self, client):
        """send_messageはmessageフィールドが必須"""
        # Act: messageなしでリクエスト
        response = client.post("/beekeeper/send_message", json={})

        # Assert: バリデーションエラー
        assert response.status_code == 422

    def test_send_message_empty_message_rejected(self, client):
        """空文字のmessageは拒否される"""
        # Act
        response = client.post(
            "/beekeeper/send_message",
            json={"message": ""},
        )

        # Assert: バリデーションエラー（min_length=1）
        assert response.status_code == 422

    def test_send_message_success(self, client):
        """メッセージ送信が成功した場合のレスポンス

        BeekeeperMCPServerのhandle_send_messageをモックし、
        正常にレスポンスが返ることを確認。
        """
        # Arrange: Beekeeperの応答をモック
        mock_result = {
            "status": "success",
            "session_id": "session-001",
            "response": "テスト応答です",
            "actions_taken": 0,
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_send_message = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/send_message",
                json={"message": "こんにちは"},
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["session_id"] == "session-001"
        assert data["response"] == "テスト応答です"
        assert data["actions_taken"] == 0

    def test_send_message_with_context(self, client):
        """コンテキスト付きメッセージ送信

        contextフィールドがBeekeeperに渡されることを確認。
        """
        # Arrange
        mock_result = {
            "status": "success",
            "session_id": "session-002",
            "response": "コンテキスト付き応答",
            "actions_taken": 1,
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_send_message = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/send_message",
                json={
                    "message": "タスクを作って",
                    "context": {"hive_id": "hive-1"},
                },
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # contextがargumentsに含まれて呼ばれたことを確認
        call_args = mock_instance.handle_send_message.call_args[0][0]
        assert call_args["context"] == {"hive_id": "hive-1"}

    def test_send_message_error_response(self, client):
        """Beekeeperがエラーを返した場合"""
        # Arrange
        mock_result = {
            "status": "error",
            "session_id": "session-003",
            "error": "LLM接続タイムアウト",
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_send_message = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/send_message",
                json={"message": "テスト"},
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "LLM接続タイムアウト"


class TestBeekeeperStatusRoute:
    """Beekeeperステータスエンドポイントのテスト"""

    def test_status_endpoint_exists(self, client):
        """/beekeeper/status エンドポイントが存在する"""
        # Act
        response = client.post("/beekeeper/status", json={})

        # Assert
        assert response.status_code != 404

    def test_status_default(self, client):
        """デフォルトのステータス取得（全Hive概要）"""
        # Arrange
        mock_result = {
            "hives": [],
            "session": None,
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_get_status = AsyncMock(return_value=mock_result)

            # Act
            response = client.post("/beekeeper/status", json={})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"] is not None

    def test_status_with_hive_id(self, client):
        """特定HiveのステータスをHive IDで取得"""
        # Arrange
        mock_result = {
            "hives": [{"hive_id": "hive-1", "name": "テスト", "status": "active"}],
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_get_status = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/status",
                json={"hive_id": "hive-1"},
            )

        # Assert
        assert response.status_code == 200
        # hive_idがargumentsに渡されたことを確認
        call_args = mock_instance.handle_get_status.call_args[0][0]
        assert call_args["hive_id"] == "hive-1"


class TestBeekeeperApproveRejectRoutes:
    """承認/却下エンドポイントのテスト"""

    def test_approve_endpoint_exists(self, client):
        """/beekeeper/approve エンドポイントが存在する"""
        # Act
        response = client.post("/beekeeper/approve", json={})

        # Assert
        assert response.status_code != 404

    def test_approve_requires_requirement_id(self, client):
        """承認にはrequirement_idが必須"""
        # Act
        response = client.post("/beekeeper/approve", json={})

        # Assert
        assert response.status_code == 422

    def test_approve_success(self, client):
        """要件承認の成功"""
        # Arrange
        mock_result = {
            "status": "approved",
            "message": "要件を承認しました",
            "requirement_id": "req-001",
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_approve = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/approve",
                json={"requirement_id": "req-001", "reason": "問題なし"},
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"

    def test_reject_endpoint_exists(self, client):
        """/beekeeper/reject エンドポイントが存在する"""
        # Act
        response = client.post("/beekeeper/reject", json={})

        # Assert
        assert response.status_code != 404

    def test_reject_requires_requirement_id(self, client):
        """却下にはrequirement_idが必須"""
        # Act
        response = client.post("/beekeeper/reject", json={})

        # Assert
        assert response.status_code == 422

    def test_reject_success(self, client):
        """要件却下の成功"""
        # Arrange
        mock_result = {
            "status": "rejected",
            "message": "要件を却下しました",
            "requirement_id": "req-002",
        }

        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_reject = AsyncMock(return_value=mock_result)

            # Act
            response = client.post(
                "/beekeeper/reject",
                json={"requirement_id": "req-002", "reason": "仕様に合わない"},
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    def test_approve_with_exception(self, client):
        """承認処理で例外が発生した場合は400エラー（内部詳細は漏洩しない）"""
        # Arrange
        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_approve = AsyncMock(side_effect=Exception("要件が見つかりません"))

            # Act
            response = client.post(
                "/beekeeper/approve",
                json={"requirement_id": "req-nonexistent"},
            )

        # Assert
        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to approve requirement"

    def test_reject_with_exception(self, client):
        """却下処理で例外が発生した場合は400エラー（内部詳細は漏洩しない）"""
        # Arrange
        with patch("colonyforge.api.routes.beekeeper.BeekeeperMCPServer") as mock_beekeeper:
            mock_instance = mock_beekeeper.return_value
            mock_instance.handle_reject = AsyncMock(side_effect=Exception("要件が見つかりません"))

            # Act
            response = client.post(
                "/beekeeper/reject",
                json={"requirement_id": "req-nonexistent"},
            )

        # Assert
        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to reject requirement"


class TestBeekeeperResponseModel:
    """BeekeeperResponseモデルのテスト"""

    def test_response_model_fields(self):
        """レスポンスモデルの必須/オプションフィールド"""
        from colonyforge.api.routes.beekeeper import BeekeeperResponse

        # Arrange / Act: 最小限のフィールドで作成
        response = BeekeeperResponse(status="success")

        # Assert
        assert response.status == "success"
        assert response.session_id is None
        assert response.response is None
        assert response.error is None
        assert response.actions_taken is None
        assert response.data is None

    def test_response_model_full(self):
        """全フィールド指定のレスポンスモデル"""
        from colonyforge.api.routes.beekeeper import BeekeeperResponse

        # Arrange / Act
        response = BeekeeperResponse(
            status="success",
            session_id="sess-1",
            response="応答テキスト",
            error=None,
            actions_taken=3,
            data={"key": "value"},
        )

        # Assert
        assert response.status == "success"
        assert response.session_id == "sess-1"
        assert response.response == "応答テキスト"
        assert response.actions_taken == 3
        assert response.data == {"key": "value"}
