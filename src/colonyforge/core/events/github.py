"""GitHub Projection イベントクラス

AR→GitHub片方向同期のイベント。
Issue作成/更新/クローズ、コメント追加、ラベル適用、Project同期を記録。
"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class GitHubIssueCreatedEvent(BaseEvent):
    """GitHub Issue作成イベント"""

    type: Literal[EventType.GITHUB_ISSUE_CREATED] = EventType.GITHUB_ISSUE_CREATED


class GitHubIssueUpdatedEvent(BaseEvent):
    """GitHub Issue更新イベント"""

    type: Literal[EventType.GITHUB_ISSUE_UPDATED] = EventType.GITHUB_ISSUE_UPDATED


class GitHubIssueClosedEvent(BaseEvent):
    """GitHub Issueクローズイベント"""

    type: Literal[EventType.GITHUB_ISSUE_CLOSED] = EventType.GITHUB_ISSUE_CLOSED


class GitHubCommentAddedEvent(BaseEvent):
    """GitHub Issueコメント追加イベント"""

    type: Literal[EventType.GITHUB_COMMENT_ADDED] = EventType.GITHUB_COMMENT_ADDED


class GitHubLabelAppliedEvent(BaseEvent):
    """GitHub ラベル適用イベント"""

    type: Literal[EventType.GITHUB_LABEL_APPLIED] = EventType.GITHUB_LABEL_APPLIED


class GitHubProjectSyncedEvent(BaseEvent):
    """GitHub Project同期イベント"""

    type: Literal[EventType.GITHUB_PROJECT_SYNCED] = EventType.GITHUB_PROJECT_SYNCED
