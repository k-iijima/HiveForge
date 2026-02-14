"""イベントフォーマッタ

SSEイベントを人間可読な文字列に変換する。
"""

from __future__ import annotations

from .constants import (
    ACTIVITY_ICONS,
    BOLD,
    DIM,
    RESET,
    ROLE_COLORS,
    ROLE_ICONS,
)


def format_event(event: dict[str, object], *, color: bool = True) -> str:
    """イベントを人間可読な1行文字列にフォーマットする。"""
    agent = event.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    agent_id: str = str(agent.get("agent_id", "?"))
    role: str = str(agent.get("role", ""))
    activity_type: str = str(event.get("activity_type", ""))
    summary: str = str(event.get("summary", ""))
    timestamp: str = str(event.get("timestamp", ""))

    # 時刻を短縮 (HH:MM:SS)
    time_short = timestamp[11:19] if len(timestamp) >= 19 else timestamp

    icon = ACTIVITY_ICONS.get(activity_type, "📌")
    role_icon = ROLE_ICONS.get(role, "")

    if color:
        c = ROLE_COLORS.get(role, "")
        return f"{DIM}{time_short}{RESET} {icon} {c}{BOLD}{role_icon}{agent_id}{RESET} {summary}"
    return f"{time_short} {icon} {role_icon}{agent_id} {summary}"
