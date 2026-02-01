"""
Conference REST API エンドポイント

Conference（会議）の作成・終了・取得を提供する。
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...core import generate_event_id
from ...core.events import ConferenceEndedEvent, ConferenceStartedEvent
from ...core.state.conference import ConferenceProjection, ConferenceState, ConferenceStore
from ..helpers import get_ar

router = APIRouter(prefix="/conferences", tags=["Conferences"])

# グローバルなConferenceストア
_conference_store = ConferenceStore()


def get_conference_store() -> ConferenceStore:
    """ConferenceStoreを取得"""
    return _conference_store


# --- Request/Response Models ---


class StartConferenceRequest(BaseModel):
    """会議開始リクエスト"""

    hive_id: str = Field(..., description="所属Hive ID")
    topic: str = Field(..., min_length=1, max_length=500, description="議題")
    participants: list[str] = Field(default_factory=list, description="参加者（Colony ID）")
    initiated_by: str = Field(default="user", description="開始者")


class EndConferenceRequest(BaseModel):
    """会議終了リクエスト"""

    summary: str = Field(default="", description="会議サマリー")
    decisions_made: list[str] = Field(default_factory=list, description="決定IDリスト")


class ConferenceResponse(BaseModel):
    """会議レスポンス"""

    conference_id: str
    hive_id: str
    topic: str
    participants: list[str]
    initiated_by: str
    state: str
    started_at: datetime | None
    ended_at: datetime | None = None
    decisions_made: list[str] = []
    summary: str = ""
    duration_seconds: int = 0


# --- Endpoints ---


@router.post("", response_model=ConferenceResponse, status_code=status.HTTP_201_CREATED)
async def start_conference(request: StartConferenceRequest):
    """会議を開始"""
    ar = get_ar()
    store = get_conference_store()

    conference_id = generate_event_id()

    event = ConferenceStartedEvent(
        actor="api",
        payload={
            "conference_id": conference_id,
            "hive_id": request.hive_id,
            "topic": request.topic,
            "participants": request.participants,
            "initiated_by": request.initiated_by,
        },
    )

    # Hive IDをrun_idとして使用（会議はHiveレベル）
    ar.append(event, f"hive-{request.hive_id}")

    projection = ConferenceProjection(
        conference_id=conference_id,
        hive_id=request.hive_id,
        topic=request.topic,
        participants=request.participants,
        initiated_by=request.initiated_by,
        state=ConferenceState.ACTIVE,
        started_at=event.timestamp,
    )
    store.add(projection)

    return ConferenceResponse(
        conference_id=conference_id,
        hive_id=request.hive_id,
        topic=request.topic,
        participants=request.participants,
        initiated_by=request.initiated_by,
        state=projection.state.value,
        started_at=projection.started_at,
    )


@router.get("", response_model=list[ConferenceResponse])
async def list_conferences(hive_id: str | None = None, active_only: bool = False):
    """会議一覧を取得"""
    store = get_conference_store()

    if hive_id:
        conferences = store.list_by_hive(hive_id)
    elif active_only:
        conferences = store.list_active()
    else:
        conferences = store.list_all()

    return [
        ConferenceResponse(
            conference_id=c.conference_id,
            hive_id=c.hive_id,
            topic=c.topic,
            participants=c.participants,
            initiated_by=c.initiated_by,
            state=c.state.value,
            started_at=c.started_at,
            ended_at=c.ended_at,
            decisions_made=c.decisions_made,
            summary=c.summary,
            duration_seconds=c.duration_seconds,
        )
        for c in conferences
    ]


@router.get("/{conference_id}", response_model=ConferenceResponse)
async def get_conference(conference_id: str):
    """会議詳細を取得"""
    store = get_conference_store()
    conference = store.get(conference_id)

    if not conference:
        raise HTTPException(status_code=404, detail="Conference not found")

    return ConferenceResponse(
        conference_id=conference.conference_id,
        hive_id=conference.hive_id,
        topic=conference.topic,
        participants=conference.participants,
        initiated_by=conference.initiated_by,
        state=conference.state.value,
        started_at=conference.started_at,
        ended_at=conference.ended_at,
        decisions_made=conference.decisions_made,
        summary=conference.summary,
        duration_seconds=conference.duration_seconds,
    )


@router.post("/{conference_id}/end", response_model=ConferenceResponse)
async def end_conference(conference_id: str, request: EndConferenceRequest | None = None):
    """会議を終了"""
    ar = get_ar()
    store = get_conference_store()

    conference = store.get(conference_id)
    if not conference:
        raise HTTPException(status_code=404, detail="Conference not found")

    if conference.state == ConferenceState.ENDED:
        raise HTTPException(status_code=400, detail="Conference already ended")

    # 継続時間を計算
    now = datetime.now(timezone.utc)
    duration_seconds = 0
    if conference.started_at:
        duration_seconds = int((now - conference.started_at).total_seconds())

    summary = request.summary if request else ""
    decisions_made = request.decisions_made if request else []

    event = ConferenceEndedEvent(
        actor="api",
        payload={
            "conference_id": conference_id,
            "duration_seconds": duration_seconds,
            "decisions_made": decisions_made,
            "summary": summary,
            "ended_by": "user",
        },
    )

    ar.append(event, f"hive-{conference.hive_id}")

    # 投影を更新
    conference.state = ConferenceState.ENDED
    conference.ended_at = event.timestamp
    conference.duration_seconds = duration_seconds
    conference.summary = summary
    conference.decisions_made = decisions_made
    store.update(conference)

    return ConferenceResponse(
        conference_id=conference.conference_id,
        hive_id=conference.hive_id,
        topic=conference.topic,
        participants=conference.participants,
        initiated_by=conference.initiated_by,
        state=conference.state.value,
        started_at=conference.started_at,
        ended_at=conference.ended_at,
        decisions_made=conference.decisions_made,
        summary=conference.summary,
        duration_seconds=conference.duration_seconds,
    )
