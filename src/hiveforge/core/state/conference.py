"""
Conference Projection

会議（Conference）の状態投影を管理する。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..events import EventType


class ConferenceState(Enum):
    """会議の状態"""

    ACTIVE = "active"  # 開催中
    ENDED = "ended"  # 終了


@dataclass
class ConferenceProjection:
    """会議の状態投影

    Attributes:
        conference_id: 会議ID
        hive_id: 所属Hive ID
        topic: 議題
        participants: 参加者（Colony ID）のリスト
        initiated_by: 開始者（"user" | "beekeeper"）
        state: 会議状態
        started_at: 開始時刻
        ended_at: 終了時刻
        decisions_made: 決定されたDecision IDのリスト
        summary: 会議サマリー
    """

    conference_id: str
    hive_id: str
    topic: str
    participants: list[str] = field(default_factory=list)
    initiated_by: str = "user"
    state: ConferenceState = ConferenceState.ACTIVE
    started_at: datetime | None = None
    ended_at: datetime | None = None
    decisions_made: list[str] = field(default_factory=list)
    summary: str = ""
    duration_seconds: int = 0


def build_conference_projection(events: list, conference_id: str) -> ConferenceProjection | None:
    """イベントリストからConference Projectionを構築

    Args:
        events: イベントリスト
        conference_id: 対象の会議ID

    Returns:
        ConferenceProjection or None
    """
    projection: ConferenceProjection | None = None

    for event in events:
        if event.type == EventType.CONFERENCE_STARTED:
            payload = event.payload
            if payload.get("conference_id") == conference_id:
                projection = ConferenceProjection(
                    conference_id=conference_id,
                    hive_id=payload.get("hive_id", ""),
                    topic=payload.get("topic", ""),
                    participants=payload.get("participants", []),
                    initiated_by=payload.get("initiated_by", "user"),
                    state=ConferenceState.ACTIVE,
                    started_at=event.timestamp,
                )
        elif event.type == EventType.CONFERENCE_ENDED and projection:
            payload = event.payload
            if payload.get("conference_id") == conference_id:
                projection.state = ConferenceState.ENDED
                projection.ended_at = event.timestamp
                projection.decisions_made = payload.get("decisions_made", [])
                projection.summary = payload.get("summary", "")
                projection.duration_seconds = payload.get("duration_seconds", 0)

    return projection


class ConferenceStore:
    """Conference状態のインメモリストア"""

    def __init__(self):
        self._conferences: dict[str, ConferenceProjection] = {}

    def add(self, projection: ConferenceProjection) -> None:
        """会議を追加"""
        self._conferences[projection.conference_id] = projection

    def get(self, conference_id: str) -> ConferenceProjection | None:
        """会議を取得"""
        return self._conferences.get(conference_id)

    def list_all(self) -> list[ConferenceProjection]:
        """全会議を取得"""
        return list(self._conferences.values())

    def list_active(self) -> list[ConferenceProjection]:
        """アクティブな会議を取得"""
        return [c for c in self._conferences.values() if c.state == ConferenceState.ACTIVE]

    def list_by_hive(self, hive_id: str) -> list[ConferenceProjection]:
        """Hive IDで会議を取得"""
        return [c for c in self._conferences.values() if c.hive_id == hive_id]

    def update(self, projection: ConferenceProjection) -> None:
        """会議を更新"""
        self._conferences[projection.conference_id] = projection

    def remove(self, conference_id: str) -> None:
        """会議を削除"""
        self._conferences.pop(conference_id, None)

    def clear(self) -> None:
        """全会議をクリア"""
        self._conferences.clear()
