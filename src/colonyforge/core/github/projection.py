"""GitHub Projection — AR イベント → GitHub 操作

AR（Akashic Record）のイベントを GitHub Issues / Comments / Labels に射影する。
ARが正本、GitHub は読み取り専用の射影（Read Model）として機能する。

マッピング:
    - RunStarted     → Issue 作成
    - TaskCompleted   → Issue コメント（進捗）
    - GuardVerified   → Issue コメント（検証結果）
    - SentinelAlert   → Issue ラベル + コメント（介入通知）
    - RunCompleted    → Issue コメント（サマリー）+ Issue クローズ
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from colonyforge.core.config import GitHubConfig
from colonyforge.core.events.base import BaseEvent
from colonyforge.core.events.types import EventType

if TYPE_CHECKING:
    from colonyforge.core.github.client import GitHubClient

logger = logging.getLogger(__name__)


@dataclass
class SyncState:
    """同期状態

    Attributes:
        last_synced_event_id: 最後に同期したイベントの ID
        run_issue_map: run_id → issue_number のマッピング
        synced_event_ids: 同期済みイベント ID のセット（冪等性用）
    """

    last_synced_event_id: str | None = None
    run_issue_map: dict[str, int] = field(default_factory=dict)
    synced_event_ids: set[str] = field(default_factory=set)


class GitHubProjection:
    """AR → GitHub 射影

    イベントを受け取り、対応する GitHub 操作を実行する。
    冪等性を保証し、同じイベントの再適用を安全にスキップする。

    Args:
        config: GitHubConfig インスタンス
        client: GitHubClient インスタンス
    """

    # イベントタイプ → ハンドラメソッド名のマッピング
    _HANDLERS: dict[str, str] = {
        EventType.RUN_STARTED: "_handle_run_started",
        EventType.RUN_COMPLETED: "_handle_run_completed",
        EventType.TASK_COMPLETED: "_handle_task_completed",
        EventType.GUARD_PASSED: "_handle_guard_result",
        EventType.GUARD_FAILED: "_handle_guard_result",
        EventType.SENTINEL_ALERT_RAISED: "_handle_sentinel_alert",
    }

    def __init__(self, config: GitHubConfig, client: GitHubClient) -> None:
        self._config = config
        self._client = client
        self._sync_state = SyncState()

    # ------------------------------------------------------------------
    # パブリック API
    # ------------------------------------------------------------------

    @property
    def sync_state(self) -> SyncState:
        """現在の同期状態を取得"""
        return self._sync_state

    def get_issue_number(self, run_id: str) -> int | None:
        """run_id に対応する Issue 番号を取得"""
        return self._sync_state.run_issue_map.get(run_id)

    async def apply(self, event: BaseEvent) -> None:
        """イベントを GitHub に射影する

        冪等性: 同じイベントの再適用は安全にスキップされる。
        未対応イベントタイプは無視される。

        Args:
            event: 適用するイベント
        """
        # 無効状態チェック
        if not self._config.enabled:
            return

        # 冪等性チェック
        if event.id in self._sync_state.synced_event_ids:
            logger.debug("Event %s already synced, skipping", event.id)
            return

        # ハンドラ検索
        event_type = event.type if isinstance(event.type, str) else event.type.value
        handler_name = self._HANDLERS.get(event_type)

        if handler_name is not None:
            handler = getattr(self, handler_name)
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Failed to project event %s (%s) to GitHub",
                    event.id,
                    event_type,
                )
                raise

        # 同期状態を更新
        self._sync_state.synced_event_ids.add(event.id)
        self._sync_state.last_synced_event_id = event.id

    async def batch_apply(self, events: list[BaseEvent]) -> None:
        """複数イベントを順番に射影する

        AR replay 結果を一括で処理する際に使用。

        Args:
            events: 適用するイベントのリスト（時間順）
        """
        for event in events:
            await self.apply(event)

    # ------------------------------------------------------------------
    # イベントハンドラ
    # ------------------------------------------------------------------

    async def _handle_run_started(self, event: BaseEvent) -> None:
        """RunStarted → Issue 作成"""
        run_id = event.run_id or "unknown"

        # 冪等性: 同じ run_id の Issue が既にある場合はスキップ
        if run_id in self._sync_state.run_issue_map:
            logger.debug("Issue for run %s already exists, skipping", run_id)
            return

        goal = event.payload.get("goal", "No goal specified")
        title = f"🐝 Run: {run_id}"
        body = (
            f"## Run Started\n\n"
            f"- **Run ID**: `{run_id}`\n"
            f"- **Goal**: {goal}\n"
            f"- **Started**: {event.timestamp.isoformat()}\n"
            f"- **Actor**: {event.actor}\n"
        )
        labels = [f"{self._config.label_prefix}run"]

        result = await self._client.create_issue(title=title, body=body, labels=labels)
        issue_number = result["number"]
        self._sync_state.run_issue_map[run_id] = issue_number
        logger.info("Created issue #%d for run %s", issue_number, run_id)

    async def _handle_run_completed(self, event: BaseEvent) -> None:
        """RunCompleted → Issue コメント + クローズ"""
        run_id = event.run_id or "unknown"
        issue_number = self._sync_state.run_issue_map.get(run_id)

        if issue_number is None:
            logger.warning("No issue found for run %s, skipping RunCompleted", run_id)
            return

        summary = event.payload.get("summary", "No summary")
        body = (
            f"## ✅ Run Completed\n\n"
            f"- **Summary**: {summary}\n"
            f"- **Completed**: {event.timestamp.isoformat()}\n"
        )

        await self._client.add_comment(issue_number=issue_number, body=body)
        await self._client.close_issue(issue_number=issue_number)
        logger.info("Closed issue #%d for run %s", issue_number, run_id)

    async def _handle_task_completed(self, event: BaseEvent) -> None:
        """TaskCompleted → Issue コメント（進捗）"""
        run_id = event.run_id or "unknown"
        issue_number = self._sync_state.run_issue_map.get(run_id)

        if issue_number is None:
            logger.debug("No issue found for run %s, skipping TaskCompleted", run_id)
            return

        task_id = event.task_id or "unknown"
        result = event.payload.get("result", "No result")
        body = (
            f"### 📋 Task Completed: `{task_id}`\n\n"
            f"- **Result**: {result}\n"
            f"- **Completed**: {event.timestamp.isoformat()}\n"
        )

        await self._client.add_comment(issue_number=issue_number, body=body)

    async def _handle_guard_result(self, event: BaseEvent) -> None:
        """GuardPassed/GuardFailed → Issue コメント（検証結果）"""
        run_id = event.run_id or "unknown"
        issue_number = self._sync_state.run_issue_map.get(run_id)

        if issue_number is None:
            logger.debug("No issue found for run %s, skipping GuardVerified", run_id)
            return

        verdict = event.payload.get("verdict", "unknown")
        reason = event.payload.get("reason", "No reason")
        colony_id = event.payload.get("colony_id", "")

        emoji = "✅" if verdict == "pass" else "❌"
        body = f"### {emoji} Guard Verification: **{verdict.upper()}**\n\n- **Reason**: {reason}\n"
        if colony_id:
            body += f"- **Colony**: `{colony_id}`\n"
        body += f"- **Verified**: {event.timestamp.isoformat()}\n"

        await self._client.add_comment(issue_number=issue_number, body=body)

    async def _handle_sentinel_alert(self, event: BaseEvent) -> None:
        """SentinelAlert → Issue ラベル + コメント"""
        run_id = event.run_id or "unknown"
        issue_number = self._sync_state.run_issue_map.get(run_id)

        if issue_number is None:
            logger.debug("No issue found for run %s, skipping SentinelAlert", run_id)
            return

        severity = event.payload.get("severity", "unknown")
        message = event.payload.get("message", "No details")

        # ラベル適用
        labels = [
            f"{self._config.label_prefix}sentinel",
            f"{self._config.label_prefix}severity:{severity}",
        ]
        await self._client.apply_labels(issue_number=issue_number, labels=labels)

        # コメント追加
        body = (
            f"### 🚨 Sentinel Alert: **{severity.upper()}**\n\n"
            f"- **Message**: {message}\n"
            f"- **Detected**: {event.timestamp.isoformat()}\n"
        )
        await self._client.add_comment(issue_number=issue_number, body=body)
