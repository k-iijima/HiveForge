"""Worker Bee MCP ツール定義

Worker Beeが公開するMCPツールのスキーマ定義を集約する。
"""

from __future__ import annotations

from typing import Any


def get_worker_tool_definitions() -> list[dict[str, Any]]:
    """MCPツール定義を取得"""
    return [
        {
            "name": "receive_task",
            "description": "Queen Beeからタスクを受け取る",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "run_id": {"type": "string", "description": "Run ID"},
                    "goal": {"type": "string", "description": "タスクの目標"},
                    "context": {
                        "type": "object",
                        "description": "タスクのコンテキスト情報",
                    },
                },
                "required": ["task_id", "run_id", "goal"],
            },
        },
        {
            "name": "report_progress",
            "description": "作業の進捗を報告する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "progress": {
                        "type": "integer",
                        "description": "進捗率 (0-100)",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "message": {"type": "string", "description": "進捗メッセージ"},
                },
                "required": ["progress"],
            },
        },
        {
            "name": "complete_task",
            "description": "タスクを完了として報告する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "作業結果"},
                    "deliverables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "成果物のリスト",
                    },
                },
                "required": ["result"],
            },
        },
        {
            "name": "fail_task",
            "description": "タスクの失敗を報告する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "失敗理由"},
                    "recoverable": {
                        "type": "boolean",
                        "description": "リカバリ可能か",
                    },
                },
                "required": ["reason"],
            },
        },
        {
            "name": "get_status",
            "description": "Worker Beeの現在の状態を取得",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "execute_task_with_llm",
            "description": "タスクを受け取りLLMで自律的に実行する（ワンショット）",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "タスクID"},
                    "run_id": {"type": "string", "description": "Run ID"},
                    "goal": {"type": "string", "description": "タスクの目標（自然言語）"},
                    "context": {
                        "type": "object",
                        "description": "タスクのコンテキスト情報",
                        "properties": {
                            "working_directory": {"type": "string"},
                        },
                    },
                },
                "required": ["task_id", "run_id", "goal"],
            },
        },
    ]
