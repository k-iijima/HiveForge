"""API認証ミドルウェアのテスト

M5-1a: API Key認証ミドルウェアの動作を検証する。

- auth.enabled=false の場合: 全リクエストが通過する
- auth.enabled=true の場合:
  - APIキーなしで 401 Unauthorized
  - 無効なAPIキーで 401 Unauthorized
  - 正しいAPIキーで通過
  - ヘルスチェック等の除外パスは認証不要
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hiveforge.api.helpers import clear_active_runs, set_ar
from hiveforge.api.server import app

# --- Fixtures ---


@pytest.fixture
def _clean_state():
    """テスト前後でグローバル状態をクリア"""
    set_ar(None)
    clear_active_runs()
    yield
    set_ar(None)
    clear_active_runs()


def _make_mock_settings(tmp_path, *, auth_enabled: bool):
    """テスト用の設定モックを生成"""
    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False
    mock_s.auth.enabled = auth_enabled
    mock_s.auth.api_key_env = "HIVEFORGE_API_KEY"
    return mock_s


@pytest.fixture
def client_auth_disabled(tmp_path, _clean_state):
    """auth.enabled=false のテストクライアント"""
    mock_s = _make_mock_settings(tmp_path, auth_enabled=False)

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        patch("hiveforge.api.auth.get_settings", return_value=mock_s),
        TestClient(app) as client,
    ):
        yield client


@pytest.fixture
def client_auth_enabled(tmp_path, _clean_state):
    """auth.enabled=true のテストクライアント（APIキー設定済み）"""
    mock_s = _make_mock_settings(tmp_path, auth_enabled=True)
    test_api_key = "test-secret-key-12345"

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        patch("hiveforge.api.auth.get_settings", return_value=mock_s),
        patch.dict(os.environ, {"HIVEFORGE_API_KEY": test_api_key}),
        TestClient(app) as client,
    ):
        yield client, test_api_key


@pytest.fixture
def client_auth_enabled_no_key(tmp_path, _clean_state):
    """auth.enabled=true だが環境変数にAPIキーが未設定"""
    mock_s = _make_mock_settings(tmp_path, auth_enabled=True)
    env = os.environ.copy()
    env.pop("HIVEFORGE_API_KEY", None)

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        patch("hiveforge.api.auth.get_settings", return_value=mock_s),
        patch.dict(os.environ, env, clear=True),
        TestClient(app) as client,
    ):
        yield client


# --- Tests ---


class TestAuthDisabled:
    """auth.enabled=false の場合のテスト"""

    def test_health_no_auth_required(self, client_auth_disabled):
        """認証無効時: ヘルスチェックは認証不要"""
        # Act
        response = client_auth_disabled.get("/health")

        # Assert
        assert response.status_code == 200

    def test_api_endpoint_accessible_without_key(self, client_auth_disabled):
        """認証無効時: APIエンドポイントもキーなしでアクセス可能"""
        # Act
        response = client_auth_disabled.get("/runs")

        # Assert
        assert response.status_code == 200


class TestAuthEnabled:
    """auth.enabled=true の場合のテスト"""

    def test_health_excluded_from_auth(self, client_auth_enabled):
        """認証有効時: ヘルスチェックは認証不要"""
        # Arrange
        client, _api_key = client_auth_enabled

        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200

    def test_openapi_excluded_from_auth(self, client_auth_enabled):
        """認証有効時: OpenAPIドキュメントは認証不要"""
        # Arrange
        client, _api_key = client_auth_enabled

        # Act
        response = client.get("/docs")

        # Assert
        assert response.status_code == 200

    def test_no_api_key_returns_401(self, client_auth_enabled):
        """認証有効時: APIキーなしのリクエストは 401"""
        # Arrange
        client, _api_key = client_auth_enabled

        # Act
        response = client.get("/runs")

        # Assert
        assert response.status_code == 401
        body = response.json()
        assert body["detail"] == "API key required"

    def test_invalid_api_key_returns_401(self, client_auth_enabled):
        """認証有効時: 無効なAPIキーは 401"""
        # Arrange
        client, _api_key = client_auth_enabled

        # Act
        response = client.get(
            "/runs",
            headers={"X-API-Key": "wrong-key"},
        )

        # Assert
        assert response.status_code == 401
        body = response.json()
        assert body["detail"] == "Invalid API key"

    def test_valid_api_key_in_header(self, client_auth_enabled):
        """認証有効時: 正しいAPIキー（ヘッダー）でアクセス可能"""
        # Arrange
        client, api_key = client_auth_enabled

        # Act
        response = client.get(
            "/runs",
            headers={"X-API-Key": api_key},
        )

        # Assert
        assert response.status_code == 200

    def test_valid_api_key_in_bearer(self, client_auth_enabled):
        """認証有効時: 正しいAPIキー（Bearerトークン）でアクセス可能"""
        # Arrange
        client, api_key = client_auth_enabled

        # Act
        response = client.get(
            "/runs",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        # Assert
        assert response.status_code == 200

    def test_invalid_bearer_returns_401(self, client_auth_enabled):
        """認証有効時: 無効なBearerトークンは 401"""
        # Arrange
        client, _api_key = client_auth_enabled

        # Act
        response = client.get(
            "/runs",
            headers={"Authorization": "Bearer wrong-token"},
        )

        # Assert
        assert response.status_code == 401

    def test_post_endpoint_requires_auth(self, client_auth_enabled):
        """認証有効時: POSTエンドポイントも認証必須"""
        # Arrange
        client, api_key = client_auth_enabled

        # Act: 認証なし
        response_no_auth = client.post("/runs", json={"run_id": "test"})

        # Assert
        assert response_no_auth.status_code == 401

        # Act: 認証あり（422はバリデーションエラーだが認証は通過）
        response_with_auth = client.post(
            "/runs",
            json={"run_id": "test"},
            headers={"X-API-Key": api_key},
        )

        # Assert: 401ではない（認証は通過している）
        assert response_with_auth.status_code != 401


class TestAuthNoApiKeyConfigured:
    """環境変数にAPIキーが設定されていない場合のテスト"""

    def test_missing_env_var_returns_500(self, client_auth_enabled_no_key):
        """APIキー環境変数が未設定の場合: サーバーエラーではなく401"""
        # Arrange
        client = client_auth_enabled_no_key

        # Act
        response = client.get("/runs")

        # Assert: APIキーが設定されていなければ全リクエスト拒否
        assert response.status_code == 401


class TestAuthMiddlewareUnit:
    """認証ミドルウェアのユニットテスト"""

    def test_extract_api_key_from_header(self):
        """X-API-Key ヘッダーからAPIキーを抽出"""
        from hiveforge.api.auth import extract_api_key

        # Arrange
        key = "my-secret"

        # Act
        result = extract_api_key(x_api_key=key, authorization=None)

        # Assert
        assert result == key

    def test_extract_api_key_from_bearer(self):
        """Authorization: Bearer ヘッダーからAPIキーを抽出"""
        from hiveforge.api.auth import extract_api_key

        # Arrange
        key = "my-secret"

        # Act
        result = extract_api_key(x_api_key=None, authorization=f"Bearer {key}")

        # Assert
        assert result == key

    def test_extract_api_key_header_priority(self):
        """X-API-Key と Authorization の両方がある場合、X-API-Key を優先"""
        from hiveforge.api.auth import extract_api_key

        # Arrange
        header_key = "header-key"
        bearer_key = "bearer-key"

        # Act
        result = extract_api_key(
            x_api_key=header_key,
            authorization=f"Bearer {bearer_key}",
        )

        # Assert: X-API-Key が優先
        assert result == header_key

    def test_extract_api_key_none(self):
        """どちらもない場合は None"""
        from hiveforge.api.auth import extract_api_key

        # Act
        result = extract_api_key(x_api_key=None, authorization=None)

        # Assert
        assert result is None

    def test_extract_api_key_invalid_bearer_format(self):
        """Bearer 形式でない Authorization ヘッダーは無視"""
        from hiveforge.api.auth import extract_api_key

        # Act
        result = extract_api_key(x_api_key=None, authorization="Basic abc123")

        # Assert
        assert result is None
