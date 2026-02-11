"""Events エンドポイント

イベント取得と因果リンクに関するエンドポイント。
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query

from ..helpers import get_ar
from ..models import EventResponse, LineageResponse

router = APIRouter(prefix="/runs/{run_id}/events", tags=["Events"])


@router.get("", response_model=list[EventResponse])
async def get_events(
    run_id: str,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=10000, description="取得件数上限")] = 100,
):
    """イベント一覧を取得"""
    ar = get_ar()
    events = []

    for event in ar.replay(run_id, since=since):
        events.append(
            EventResponse(
                id=event.id,
                type=event.type.value if hasattr(event.type, "value") else event.type,
                timestamp=event.timestamp,
                actor=event.actor,
                payload=event.payload,
                hash=event.hash,
                prev_hash=event.prev_hash,
                parents=event.parents,
            )
        )
        if len(events) >= limit:
            break

    return events


@router.get("/{event_id}/lineage", response_model=LineageResponse)
async def get_event_lineage(
    run_id: str,
    event_id: str,
    direction: Annotated[
        Literal["ancestors", "descendants", "both"],
        Query(description="探索方向"),
    ] = "both",
    max_depth: Annotated[int, Query(ge=1, le=100, description="最大探索深度")] = 10,
):
    """イベントの因果リンクを取得

    Args:
        run_id: Run ID
        event_id: 対象のイベントID
        direction: 探索方向（ancestors, descendants, both）
        max_depth: 最大探索深度
    """
    ar = get_ar()

    # 全イベントを取得してインデックス化
    all_events: dict[str, Any] = {}
    # 逆引きマップ: parent_id -> [子イベントID...]
    children_map: dict[str, list[str]] = {}
    for event in ar.replay(run_id):
        all_events[event.id] = event
        # 逆引きマップを構築
        for parent_id in getattr(event, "parents", []):
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(event.id)

    if event_id not in all_events:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    ancestors: list[str] = []
    descendants: list[str] = []
    truncated = False

    # 祖先を探索（親方向）
    if direction in ("ancestors", "both"):
        visited: set[str] = set()
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                truncated = True
                continue

            if current_id not in all_events:  # pragma: no cover (defensive check)
                continue

            current_event = all_events[current_id]
            parents = getattr(current_event, "parents", [])

            for parent_id in parents:
                if parent_id not in visited and parent_id in all_events:
                    visited.add(parent_id)
                    ancestors.append(parent_id)
                    queue.append((parent_id, depth + 1))

    # 子孫を探索（子方向） - 逆引きマップを使用
    if direction in ("descendants", "both"):
        visited: set[str] = set()  # type: ignore[no-redef]
        queue = [(event_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                truncated = True
                continue

            # 逆引きマップから子イベントを取得
            for child_id in children_map.get(current_id, []):
                if child_id not in visited:
                    visited.add(child_id)
                    descendants.append(child_id)
                    queue.append((child_id, depth + 1))

    return LineageResponse(
        event_id=event_id,
        ancestors=ancestors,
        descendants=descendants,
        truncated=truncated,
    )
