"""ChangeTracker — §11.3 要件変更追跡.

doorstop 要件の変更を検知し、構造化された RA_REQ_CHANGED イベントを発行する。
"""

from __future__ import annotations

import difflib
from typing import Any

from colonyforge.core.events.ra import RAReqChangedEvent
from colonyforge.requirement_analysis.models import ChangeReason, RequirementChangedPayload


class ChangeTracker:
    """要件変更追跡 — RA_REQ_CHANGED イベント発行.

    doorstop 要件の変更を検知し、構造化された RA_REQ_CHANGED イベントを発行する。
    """

    def __init__(self, *, ar_store: Any | None = None) -> None:
        """ar_store: Akashic Record ストア（イベント永続化先）."""
        self._ar_store = ar_store

    def track_change(
        self,
        *,
        doorstop_id: str,
        prev_version: int,
        new_version: int,
        reason: ChangeReason,
        diff_summary: str,
        diff_lines: list[str] | None = None,
        affected_links: list[str] | None = None,
        cause_event_id: str | None = None,
        prev_hash: str | None = None,
    ) -> RAReqChangedEvent:
        """要件変更を記録し、RA_REQ_CHANGED イベントを返す.

        Raises:
            ValueError: new_version <= prev_version の場合
        """
        if new_version <= prev_version:
            raise ValueError(f"new_version ({new_version}) must be > prev_version ({prev_version})")

        payload_model = RequirementChangedPayload(
            doorstop_id=doorstop_id,
            prev_version=prev_version,
            new_version=new_version,
            reason=reason,
            cause_event_id=cause_event_id,
            diff_summary=diff_summary,
            diff_lines=diff_lines or [],
            affected_links=affected_links or [],
        )

        event = RAReqChangedEvent(
            payload=payload_model.model_dump(),
            prev_hash=prev_hash,
        )

        return event

    def compute_diff(
        self,
        old_content: str,
        new_content: str,
    ) -> list[str]:
        """unified diff を計算する."""
        return list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                lineterm="",
            )
        )
