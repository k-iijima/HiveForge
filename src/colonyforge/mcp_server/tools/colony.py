"""Colony関連ツール定義"""

from mcp.types import Tool


def get_colony_tools() -> list[Tool]:
    """Colony管理ツール"""
    return [
        Tool(
            name="create_colony",
            description="新しいColonyを作成します。ColonyはHive配下のタスクグループです。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "親HiveのID"},
                    "name": {"type": "string", "description": "Colonyの名前"},
                    "goal": {"type": "string", "description": "Colonyの目標"},
                },
                "required": ["hive_id", "name"],
            },
        ),
        Tool(
            name="list_colonies",
            description="Hive配下のColony一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "HiveのID"},
                },
                "required": ["hive_id"],
            },
        ),
        Tool(
            name="start_colony",
            description="Colonyを開始します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {"type": "string", "description": "ColonyのID"},
                },
                "required": ["colony_id"],
            },
        ),
        Tool(
            name="complete_colony",
            description="Colonyを完了します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {"type": "string", "description": "ColonyのID"},
                },
                "required": ["colony_id"],
            },
        ),
    ]
