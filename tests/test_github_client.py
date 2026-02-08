"""GitHubClient テスト

GitHub REST API クライアントのテスト。
httpx をモックして外部通信なしで検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiveforge.core.config import GitHubConfig
from hiveforge.core.github.client import GitHubClient, GitHubClientError


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def github_config() -> GitHubConfig:
    """テスト用 GitHubConfig"""
    return GitHubConfig(
        enabled=True,
        owner="test-owner",
        repo="test-repo",
        project_number=1,
        base_url="https://api.github.com",
        label_prefix="hiveforge:",
    )


@pytest.fixture
def mock_token(monkeypatch: pytest.MonkeyPatch) -> str:
    """GITHUB_TOKEN 環境変数をセット"""
    token = "ghp_test_token_1234567890"
    monkeypatch.setenv("GITHUB_TOKEN", token)
    return token


@pytest.fixture
def client(github_config: GitHubConfig, mock_token: str) -> GitHubClient:
    """テスト用 GitHubClient"""
    return GitHubClient(github_config)


# ---------------------------------------------------------------------------
# 初期化
# ---------------------------------------------------------------------------


class TestGitHubClientInit:
    """GitHubClient 初期化テスト"""

    def test_init_with_valid_config(self, github_config: GitHubConfig, mock_token: str) -> None:
        """有効な設定で初期化できることを確認

        GitHubConfigとトークン環境変数が揃っている場合、
        GitHubClientが正常にインスタンス化される。
        """
        # Arrange: fixture で設定済み

        # Act
        client = GitHubClient(github_config)

        # Assert
        assert client.owner == "test-owner"
        assert client.repo == "test-repo"
        assert client.token == mock_token

    def test_init_without_token_raises(self, github_config: GitHubConfig) -> None:
        """トークン環境変数が未設定の場合 GitHubClientError を送出

        セキュリティ上、トークンなしでのAPI呼び出しは許可しない。
        """
        # Arrange: GITHUB_TOKEN 未設定

        # Act & Assert
        with pytest.raises(GitHubClientError, match="token"):
            GitHubClient(github_config)

    def test_init_custom_token_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """カスタムトークン環境変数名をサポートすること

        GHESなど、GITHUB_TOKEN以外の環境変数名を使用するケースに対応。
        """
        # Arrange
        monkeypatch.setenv("MY_GH_TOKEN", "ghp_custom")
        config = GitHubConfig(
            enabled=True,
            owner="owner",
            repo="repo",
            token_env="MY_GH_TOKEN",
        )

        # Act
        client = GitHubClient(config)

        # Assert
        assert client.token == "ghp_custom"


# ---------------------------------------------------------------------------
# Issue 作成
# ---------------------------------------------------------------------------


class TestCreateIssue:
    """Issue 作成テスト"""

    @pytest.mark.asyncio
    async def test_create_issue_success(self, client: GitHubClient) -> None:
        """Issue作成が成功した場合、issue番号を返すこと

        REST API POST /repos/{owner}/{repo}/issues を呼び出し、
        レスポンスからissue番号を抽出する。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 42, "id": 12345}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            result = await client.create_issue(
                title="Run started: 01HTEST",
                body="Goal: テスト実行",
                labels=["hiveforge:run"],
            )

        # Assert
        assert result == {"number": 42, "id": 12345}
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert "/repos/test-owner/test-repo/issues" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_create_issue_api_error(self, client: GitHubClient) -> None:
        """API エラー時に GitHubClientError を送出すること

        ネットワークエラーや認証エラーなどの場合、
        例外を適切にラップして送出する。
        """
        # Arrange
        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act & Assert
            with pytest.raises(GitHubClientError, match="Connection refused"):
                await client.create_issue(title="test", body="test")


# ---------------------------------------------------------------------------
# Issue 更新
# ---------------------------------------------------------------------------


class TestUpdateIssue:
    """Issue 更新テスト"""

    @pytest.mark.asyncio
    async def test_update_issue_success(self, client: GitHubClient) -> None:
        """Issue更新が成功した場合、更新後データを返すこと

        PATCH /repos/{owner}/{repo}/issues/{issue_number} を呼び出す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"number": 42, "state": "open"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.patch = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            result = await client.update_issue(
                issue_number=42,
                title="Updated title",
                body="Updated body",
            )

        # Assert
        assert result["number"] == 42
        mock_http.patch.assert_called_once()


# ---------------------------------------------------------------------------
# Issue クローズ
# ---------------------------------------------------------------------------


class TestCloseIssue:
    """Issue クローズテスト"""

    @pytest.mark.asyncio
    async def test_close_issue_success(self, client: GitHubClient) -> None:
        """Issueクローズが成功した場合、state=closedを含むデータを返すこと

        PATCH /repos/{owner}/{repo}/issues/{issue_number} で state=closed を送信。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"number": 42, "state": "closed"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.patch = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            result = await client.close_issue(issue_number=42)

        # Assert
        assert result["state"] == "closed"
        call_kwargs = mock_http.patch.call_args
        # state=closed がリクエストボディに含まれる
        assert call_kwargs.kwargs.get("json", {}).get("state") == "closed"


# ---------------------------------------------------------------------------
# コメント追加
# ---------------------------------------------------------------------------


class TestAddComment:
    """Issue コメント追加テスト"""

    @pytest.mark.asyncio
    async def test_add_comment_success(self, client: GitHubClient) -> None:
        """コメント追加が成功した場合、コメントデータを返すこと

        POST /repos/{owner}/{repo}/issues/{issue_number}/comments を呼び出す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 999, "body": "Guard failed"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            result = await client.add_comment(
                issue_number=42, body="Guard failed: test coverage below 80%"
            )

        # Assert
        assert result["id"] == 999
        assert result["body"] == "Guard failed"


# ---------------------------------------------------------------------------
# ラベル適用
# ---------------------------------------------------------------------------


class TestApplyLabels:
    """ラベル適用テスト"""

    @pytest.mark.asyncio
    async def test_apply_labels_success(self, client: GitHubClient) -> None:
        """ラベル適用が成功した場合、ラベルリストを返すこと

        POST /repos/{owner}/{repo}/issues/{issue_number}/labels を呼び出す。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "hiveforge:sentinel"},
            {"name": "hiveforge:run"},
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            result = await client.apply_labels(
                issue_number=42,
                labels=["hiveforge:sentinel"],
            )

        # Assert
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ヘッダー検証
# ---------------------------------------------------------------------------


class TestHeaders:
    """リクエストヘッダーテスト"""

    @pytest.mark.asyncio
    async def test_auth_header_included(self, client: GitHubClient) -> None:
        """Authorization ヘッダーにBearerトークンが含まれること

        全APIリクエストに認証ヘッダーが付与されることを検証。
        """
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 1}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            await client.create_issue(title="test", body="test")

        # Assert: AsyncClient 初期化時にヘッダーが渡される
        init_kwargs = mock_cls.call_args.kwargs
        headers = init_kwargs.get("headers", {})
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer ghp_test_token_1234567890"

    @pytest.mark.asyncio
    async def test_accept_header_json(self, client: GitHubClient) -> None:
        """Accept ヘッダーに application/vnd.github+json が含まれること"""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 1}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            await client.create_issue(title="test", body="test")

        # Assert
        init_kwargs = mock_cls.call_args.kwargs
        headers = init_kwargs.get("headers", {})
        assert headers.get("Accept") == "application/vnd.github+json"


# ---------------------------------------------------------------------------
# GHES 対応
# ---------------------------------------------------------------------------


class TestGHES:
    """GitHub Enterprise Server 対応テスト"""

    @pytest.mark.asyncio
    async def test_custom_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """カスタムbase_urlでGHESをサポートすること

        base_urlがAPI URLのプレフィックスとして使用される。
        """
        # Arrange
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        config = GitHubConfig(
            enabled=True,
            owner="corp",
            repo="project",
            base_url="https://github.corp.com/api/v3",
        )
        client = GitHubClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"number": 1}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Act
            await client.create_issue(title="test", body="test")

        # Assert
        call_args = mock_http.post.call_args
        url = call_args.args[0]
        assert url.startswith("https://github.corp.com/api/v3")
