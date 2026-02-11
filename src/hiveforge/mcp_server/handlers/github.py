"""GitHub Projection MCP ハンドラー

AR→GitHub同期操作をMCPツールとして公開する。
"""

from __future__ import annotations

import logging
from typing import Any

from ...core.config import GitHubConfig, get_settings
from ...core.github.client import GitHubClient, GitHubClientError
from ...core.github.projection import GitHubProjection
from .base import BaseHandler

logger = logging.getLogger(__name__)


class GitHubHandlers(BaseHandler):
    """GitHub Projection ハンドラー

    AR のイベントを GitHub Issues/Comments/Labels に射影する
    MCP ツールを提供する。
    """

    _projection: GitHubProjection | None = None

    def _get_github_config(self) -> GitHubConfig:
        """GitHubConfig を取得"""
        return get_settings().github

    def _get_projection(self) -> GitHubProjection:
        """GitHubProjection インスタンスを取得（遅延初期化）"""
        if self._projection is None:
            config = self._get_github_config()
            if not config.enabled:
                raise GitHubClientError(
                    "GitHub Projection is not enabled. "
                    "Set github.enabled=true in hiveforge.config.yaml"
                )
            client = GitHubClient(config)
            self._projection = GitHubProjection(config=config, client=client)
        return self._projection

    async def handle_sync_run_to_github(self, args: dict[str, Any]) -> dict[str, Any]:
        """指定 Run の AR イベントを GitHub に同期する

        AR からイベントを replay し、GitHubProjection で射影する。
        冪等なので何度実行しても安全。
        """
        run_id = args.get("run_id") or self._current_run_id
        if not run_id:
            return {"error": "run_id is required (no active run)"}

        try:
            projection = self._get_projection()
            ar = self._get_ar()

            # AR からイベントを replay
            events = list(ar.replay(run_id))
            if not events:
                return {
                    "status": "no_events",
                    "run_id": run_id,
                    "message": "No events found for this run",
                }

            # 射影を適用
            await projection.batch_apply(events)

            issue_number = projection.get_issue_number(run_id)
            return {
                "status": "synced",
                "run_id": run_id,
                "events_processed": len(events),
                "issue_number": issue_number,
                "sync_state": {
                    "last_synced_event_id": projection.sync_state.last_synced_event_id,
                    "total_synced": len(projection.sync_state.synced_event_ids),
                },
            }
        except GitHubClientError:
            raise
        except Exception as exc:
            logger.exception("Failed to sync run %s to GitHub", run_id)
            raise RuntimeError(f"GitHub sync failed for run {run_id}") from exc

    async def handle_get_github_sync_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """GitHub同期状態を取得する"""
        try:
            projection = self._get_projection()
            state = projection.sync_state

            return {
                "status": "ok",
                "enabled": True,
                "last_synced_event_id": state.last_synced_event_id,
                "total_synced": len(state.synced_event_ids),
                "run_issue_map": state.run_issue_map,
            }
        except GitHubClientError as exc:
            return {"error": str(exc), "enabled": False}
