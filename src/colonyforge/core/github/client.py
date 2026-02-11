"""GitHub REST API クライアント

httpx ベースの非同期クライアント。
GitHub.com / GitHub Enterprise Server の両方をサポート。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from colonyforge.core.config import GitHubConfig


class GitHubClientError(Exception):
    """GitHub API 呼び出しに関するエラー"""


class GitHubClient:
    """GitHub REST API クライアント

    Issue / Comment / Label 操作を提供する。
    全操作は非同期で、httpx.AsyncClient を使用する。

    Args:
        config: GitHubConfig インスタンス
    """

    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        self._owner = config.owner
        self._repo = config.repo
        self._base_url = config.base_url.rstrip("/")

        # トークン取得
        token = os.environ.get(config.token_env, "")
        if not token:
            raise GitHubClientError(
                f"GitHub token not found in environment variable '{config.token_env}'. "
                f"Set {config.token_env} to a valid GitHub personal access token."
            )
        self._token = token

    # ------------------------------------------------------------------
    # プロパティ
    # ------------------------------------------------------------------

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def repo(self) -> str:
        return self._repo

    @property
    def token(self) -> str:
        return self._token

    # ------------------------------------------------------------------
    # Issue 操作
    # ------------------------------------------------------------------

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Issue を作成する

        Args:
            title: Issue タイトル
            body: Issue 本文（Markdown）
            labels: 適用するラベル名のリスト

        Returns:
            作成された Issue のデータ（number, id 等）

        Raises:
            GitHubClientError: API 呼び出しに失敗した場合
        """
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/issues"
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        return await self._post(url, payload)

    async def update_issue(
        self,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Issue を更新する

        Args:
            issue_number: Issue 番号
            title: 新しいタイトル（None で変更なし）
            body: 新しい本文（None で変更なし）
            state: 新しい状態 ("open" or "closed")
            labels: 新しいラベルリスト

        Returns:
            更新された Issue のデータ

        Raises:
            GitHubClientError: API 呼び出しに失敗した場合
        """
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/issues/{issue_number}"
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels

        return await self._patch(url, payload)

    async def close_issue(self, issue_number: int) -> dict[str, Any]:
        """Issue をクローズする

        Args:
            issue_number: Issue 番号

        Returns:
            更新された Issue のデータ

        Raises:
            GitHubClientError: API 呼び出しに失敗した場合
        """
        return await self.update_issue(issue_number, state="closed")

    # ------------------------------------------------------------------
    # コメント操作
    # ------------------------------------------------------------------

    async def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """Issue にコメントを追加する

        Args:
            issue_number: Issue 番号
            body: コメント本文（Markdown）

        Returns:
            作成されたコメントのデータ

        Raises:
            GitHubClientError: API 呼び出しに失敗した場合
        """
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/issues/{issue_number}/comments"
        return await self._post(url, {"body": body})

    # ------------------------------------------------------------------
    # ラベル操作
    # ------------------------------------------------------------------

    async def apply_labels(self, issue_number: int, labels: list[str]) -> list[dict[str, Any]]:
        """Issue にラベルを適用する

        Args:
            issue_number: Issue 番号
            labels: 適用するラベル名のリスト

        Returns:
            適用されたラベルのリスト

        Raises:
            GitHubClientError: API 呼び出しに失敗した場合
        """
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/issues/{issue_number}/labels"
        return await self._post(url, {"labels": labels})

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """共通リクエストヘッダー"""
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _post(self, url: str, payload: dict[str, Any]) -> Any:
        """POST リクエストを送信"""
        try:
            async with httpx.AsyncClient(headers=self._headers()) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise GitHubClientError(str(exc)) from exc

    async def _patch(self, url: str, payload: dict[str, Any]) -> Any:
        """PATCH リクエストを送信"""
        try:
            async with httpx.AsyncClient(headers=self._headers()) as client:
                response = await client.patch(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise GitHubClientError(str(exc)) from exc
