"""
Conference Projection

会議（Conference）の状態投影を管理する。
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..events import EventType

logger = logging.getLogger(__name__)


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


def build_conference_projection(
    events: list[Any], conference_id: str
) -> ConferenceProjection | None:
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
    """Conference状態のストア

    base_pathが指定された場合、JSONL形式で永続化する。
    未指定時は従来通りインメモリのみで動作する。
    """

    def __init__(self, base_path: Path | str | None = None):
        self._conferences: dict[str, ConferenceProjection] = {}
        self._base_path: Path | None = None
        if base_path is not None:
            self._base_path = Path(base_path) / "conferences"
            self._base_path.mkdir(parents=True, exist_ok=True)
            self._replay()

    def _conferences_path(self) -> Path | None:
        if self._base_path is None:
            return None
        return self._base_path / "conferences.jsonl"

    def add(self, projection: ConferenceProjection) -> None:
        """会議を追加"""
        self._conferences[projection.conference_id] = projection
        self._persist()

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
        self._persist()

    def remove(self, conference_id: str) -> None:
        """会議を削除"""
        self._conferences.pop(conference_id, None)
        self._persist()

    def clear(self) -> None:
        """全会議をクリア"""
        self._conferences.clear()
        self._persist()

    # =========================================================================
    # 永続化
    # =========================================================================

    def _persist(self) -> None:
        """現在の全状態をJSONLに書き出す"""
        path = self._conferences_path()
        if path is None:
            return
        with open(path, "w", encoding="utf-8") as f:
            for projection in self._conferences.values():
                data = self._projection_to_dict(projection)
                line = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
                f.write(line + "\n")

    def _replay(self) -> None:
        """JSONLファイルからメモリキャッシュを復元"""
        path = self._conferences_path()
        if path is None or not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    projection = self._dict_to_projection(data)
                    self._conferences[projection.conference_id] = projection
                except (ValueError, KeyError, Exception) as e:
                    logger.warning(f"Conference読み込みエラー: {e}")

    @staticmethod
    def _projection_to_dict(projection: ConferenceProjection) -> dict[str, Any]:
        """ConferenceProjectionをdictに変換"""
        data = dataclasses.asdict(projection)
        # Enumをstring値に変換
        data["state"] = projection.state.value
        # datetimeをISO文字列に変換
        if projection.started_at is not None:
            data["started_at"] = projection.started_at.isoformat()
        if projection.ended_at is not None:
            data["ended_at"] = projection.ended_at.isoformat()
        return data

    @staticmethod
    def _dict_to_projection(data: dict[str, Any]) -> ConferenceProjection:
        """dictからConferenceProjectionを復元"""
        # state: string → enum
        state_str = data.get("state", "active")
        data["state"] = ConferenceState(state_str)
        # datetime: ISO string → datetime
        for dt_field in ("started_at", "ended_at"):
            val = data.get(dt_field)
            if val is not None and isinstance(val, str):
                try:
                    data[dt_field] = datetime.fromisoformat(val)
                except ValueError:
                    data[dt_field] = None
        return ConferenceProjection(**data)
