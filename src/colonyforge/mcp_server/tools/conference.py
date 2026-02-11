"""Conference関連ツール定義"""

from mcp.types import Tool


def get_conference_tools() -> list[Tool]:
    """Conference (会議) ツール"""
    return [
        Tool(
            name="start_conference",
            description="会議を開始します。複数のColonyが参加し、意見収集・決定を行います。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "会議を開催するHiveのID",
                    },
                    "topic": {"type": "string", "description": "会議の議題"},
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "参加者（Colony ID）のリスト",
                    },
                },
                "required": ["hive_id", "topic"],
            },
        ),
        Tool(
            name="end_conference",
            description="会議を終了します。サマリーと決定事項を記録できます。",
            inputSchema={
                "type": "object",
                "properties": {
                    "conference_id": {"type": "string", "description": "会議ID"},
                    "summary": {"type": "string", "description": "会議のサマリー"},
                    "decisions_made": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "決定されたDecision IDのリスト",
                    },
                },
                "required": ["conference_id"],
            },
        ),
        Tool(
            name="list_conferences",
            description="会議一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "Hive IDでフィルタ（オプション）",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "アクティブな会議のみ取得",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="get_conference",
            description="会議の詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "conference_id": {"type": "string", "description": "会議ID"},
                },
                "required": ["conference_id"],
            },
        ),
    ]
