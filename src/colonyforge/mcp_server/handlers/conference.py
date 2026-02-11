"""
Conference MCP ハンドラー

Conference（会議）操作のMCPツールハンドラー。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ...core import generate_event_id
from ...core.events import ConferenceEndedEvent, ConferenceStartedEvent
from ...core.state.conference import ConferenceProjection, ConferenceState, ConferenceStore
from .base import BaseHandler

if TYPE_CHECKING:
    from ..server import ColonyForgeMCPServer


class ConferenceHandlers(BaseHandler):
    """Conference関連のMCPハンドラー"""

    def __init__(
        self, server: ColonyForgeMCPServer, conference_store: ConferenceStore | None = None
    ):
        """初期化

        Args:
            server: ColonyForgeMCPServer
            conference_store: ConferenceStore（Noneの場合は新規作成）
        """
        super().__init__(server)
        self._store = conference_store or ConferenceStore()

    @property
    def store(self) -> ConferenceStore:
        """ConferenceStoreを取得"""
        return self._store

    async def handle_start_conference(self, args: dict[str, Any]) -> dict[str, Any]:
        """会議を開始

        Args:
            args:
                hive_id: 所属Hive ID（必須）
                topic: 議題（必須）
                participants: 参加者リスト（オプション）

        Returns:
            会議情報
        """
        hive_id = args.get("hive_id")
        topic = args.get("topic")

        if not hive_id:
            return {"error": "hive_id is required"}
        if not topic:
            return {"error": "topic is required"}

        conference_id = generate_event_id()
        participants = args.get("participants", [])
        initiated_by = args.get("initiated_by", "user")

        event = ConferenceStartedEvent(
            actor="mcp",
            payload={
                "conference_id": conference_id,
                "hive_id": hive_id,
                "topic": topic,
                "participants": participants,
                "initiated_by": initiated_by,
            },
        )

        self._get_ar().append(event, f"hive-{hive_id}")

        projection = ConferenceProjection(
            conference_id=conference_id,
            hive_id=hive_id,
            topic=topic,
            participants=participants,
            initiated_by=initiated_by,
            state=ConferenceState.ACTIVE,
            started_at=event.timestamp,
        )
        self._store.add(projection)

        return {
            "conference_id": conference_id,
            "hive_id": hive_id,
            "topic": topic,
            "participants": participants,
            "state": "active",
            "started_at": event.timestamp.isoformat(),
        }

    async def handle_end_conference(self, args: dict[str, Any]) -> dict[str, Any]:
        """会議を終了

        Args:
            args:
                conference_id: 会議ID（必須）
                summary: サマリー（オプション）
                decisions_made: 決定IDリスト（オプション）

        Returns:
            終了した会議情報
        """
        conference_id = args.get("conference_id")
        if not conference_id:
            return {"error": "conference_id is required"}

        conference = self._store.get(conference_id)
        if not conference:
            return {"error": f"Conference not found: {conference_id}"}

        if conference.state == ConferenceState.ENDED:
            return {"error": "Conference already ended"}

        now = datetime.now(UTC)
        duration_seconds = 0
        if conference.started_at:
            duration_seconds = int((now - conference.started_at).total_seconds())

        summary = args.get("summary", "")
        decisions_made = args.get("decisions_made", [])

        event = ConferenceEndedEvent(
            actor="mcp",
            payload={
                "conference_id": conference_id,
                "duration_seconds": duration_seconds,
                "decisions_made": decisions_made,
                "summary": summary,
                "ended_by": "mcp",
            },
        )

        self._get_ar().append(event, f"hive-{conference.hive_id}")

        conference.state = ConferenceState.ENDED
        conference.ended_at = event.timestamp
        conference.duration_seconds = duration_seconds
        conference.summary = summary
        conference.decisions_made = decisions_made
        self._store.update(conference)

        return {
            "conference_id": conference_id,
            "state": "ended",
            "duration_seconds": duration_seconds,
            "summary": summary,
            "decisions_made": decisions_made,
        }

    async def handle_list_conferences(self, args: dict[str, Any]) -> dict[str, Any]:
        """会議一覧を取得

        Args:
            args:
                hive_id: Hive IDでフィルタ（オプション）
                active_only: アクティブのみ（オプション）

        Returns:
            会議一覧
        """
        hive_id = args.get("hive_id")
        active_only = args.get("active_only", False)

        if hive_id:
            conferences = self._store.list_by_hive(hive_id)
        elif active_only:
            conferences = self._store.list_active()
        else:
            conferences = self._store.list_all()

        return {
            "conferences": [
                {
                    "conference_id": c.conference_id,
                    "hive_id": c.hive_id,
                    "topic": c.topic,
                    "participants": c.participants,
                    "state": c.state.value,
                    "started_at": c.started_at.isoformat() if c.started_at else None,
                }
                for c in conferences
            ],
            "count": len(conferences),
        }

    async def handle_get_conference(self, args: dict[str, Any]) -> dict[str, Any]:
        """会議詳細を取得

        Args:
            args:
                conference_id: 会議ID（必須）

        Returns:
            会議詳細
        """
        conference_id = args.get("conference_id")
        if not conference_id:
            return {"error": "conference_id is required"}

        conference = self._store.get(conference_id)
        if not conference:
            return {"error": f"Conference not found: {conference_id}"}

        return {
            "conference_id": conference.conference_id,
            "hive_id": conference.hive_id,
            "topic": conference.topic,
            "participants": conference.participants,
            "initiated_by": conference.initiated_by,
            "state": conference.state.value,
            "started_at": conference.started_at.isoformat() if conference.started_at else None,
            "ended_at": conference.ended_at.isoformat() if conference.ended_at else None,
            "decisions_made": conference.decisions_made,
            "summary": conference.summary,
            "duration_seconds": conference.duration_seconds,
        }
