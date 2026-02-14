"""モニター表示用の定数定義

アイコン・色コードなど、表示に使用する共通定数を集約する。
"""

from __future__ import annotations

# アイコン定義
ROLE_ICONS: dict[str, str] = {
    "beekeeper": "🧑‍🌾",
    "queen_bee": "👑",
    "worker_bee": "🐝",
}

ACTIVITY_ICONS: dict[str, str] = {
    "llm.request": "🧠",
    "llm.response": "💬",
    "mcp.tool_call": "🔧",
    "mcp.tool_result": "📦",
    "agent.started": "▶️ ",
    "agent.completed": "✅",
    "agent.error": "❌",
    "message.sent": "📤",
    "message.received": "📥",
    "task.assigned": "📋",
    "task.progress": "📊",
}

# ANSI色定義 (ロール別)
ROLE_COLORS: dict[str, str] = {
    "beekeeper": "\033[33m",  # 黄
    "queen_bee": "\033[35m",  # 紫
    "worker_bee": "\033[32m",  # 緑
}
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

SESSION_NAME = "colonyforge-monitor"
