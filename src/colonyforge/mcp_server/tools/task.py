"""Task関連ツール定義"""

from mcp.types import Tool


def get_task_tools() -> list[Tool]:
    """Task管理ツール"""
    return [
        Tool(
            name="create_task",
            description="新しいTaskを作成します。分解した作業単位を登録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "タスクのタイトル"},
                    "description": {"type": "string", "description": "タスクの詳細説明"},
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="assign_task",
            description="Taskを自分に割り当てて作業を開始します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="report_progress",
            description="Taskの進捗を報告します。0-100の数値で進捗率を指定してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "progress": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "進捗率 (0-100)",
                    },
                    "message": {"type": "string", "description": "進捗メッセージ"},
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id", "progress"],
            },
        ),
        Tool(
            name="complete_task",
            description="Taskを完了します。成果物や結果を記録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "result": {"type": "string", "description": "タスクの成果・結果"},
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="fail_task",
            description="Taskを失敗としてマークします。エラー内容を記録してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "error": {"type": "string", "description": "エラー内容"},
                    "retryable": {
                        "type": "boolean",
                        "description": "リトライ可能かどうか",
                        "default": True,
                    },
                    "parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "親イベントID（因果リンク用）",
                    },
                },
                "required": ["task_id", "error"],
            },
        ),
    ]
