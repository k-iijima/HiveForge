"""Hive関連ツール定義"""

from mcp.types import Tool


def get_hive_tools() -> list[Tool]:
    """Hive CRUD ツール"""
    return [
        Tool(
            name="create_hive",
            description="新しいHiveを作成します。Hiveは複数のColonyをまとめる最上位の単位です。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Hiveの名前"},
                    "description": {"type": "string", "description": "Hiveの説明"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_hives",
            description="Hive一覧を取得します。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_hive",
            description="Hiveの詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "HiveのID"},
                },
                "required": ["hive_id"],
            },
        ),
        Tool(
            name="close_hive",
            description="Hiveを終了します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "HiveのID"},
                },
                "required": ["hive_id"],
            },
        ),
    ]
