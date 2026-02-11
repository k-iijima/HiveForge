"""Beekeeper 関連ツール定義"""

from mcp.types import Tool


def get_beekeeper_tools() -> list[Tool]:
    """Beekeeper (ユーザー窓口) ツール"""
    return [
        Tool(
            name="send_message",
            description=("Beekeeperにメッセージを送信して作業を依頼する（@colonyforge経由）"),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "ユーザーからのメッセージ（自然言語）",
                    },
                    "context": {
                        "type": "object",
                        "description": "追加コンテキスト情報",
                    },
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="get_beekeeper_status",
            description="Beekeeperを通じてHive/Colonyの状態を取得する",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "Hive ID（省略時は全Hive）",
                    },
                },
            },
        ),
        Tool(
            name="approve",
            description="承認待ちの操作を承認する",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "承認リクエストID",
                    },
                    "comment": {"type": "string", "description": "コメント"},
                },
                "required": ["request_id"],
            },
        ),
        Tool(
            name="reject",
            description="承認待ちの操作を拒否する",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "承認リクエストID",
                    },
                    "reason": {"type": "string", "description": "拒否理由"},
                },
                "required": ["request_id", "reason"],
            },
        ),
    ]
