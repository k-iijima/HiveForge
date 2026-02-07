"""Beekeeper ツール定義

MCP公開ツールとLLM内部ツールのスキーマ定義。
"""

from __future__ import annotations

from typing import Any


def get_mcp_tool_definitions() -> list[dict[str, Any]]:
    """MCPツール定義を取得

    ユーザー/CopilotがBeekeeperに対して実行できるツール。
    """
    return [
        {
            "name": "send_message",
            "description": "Beekeeperにメッセージを送信して作業を依頼する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "ユーザーからのメッセージ（自然言語）",
                    },
                    "context": {
                        "type": "object",
                        "description": "追加コンテキスト情報",
                        "properties": {
                            "working_directory": {"type": "string"},
                            "selected_files": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["message"],
            },
        },
        {
            "name": "get_status",
            "description": "Hive/Colonyの現在の状態を取得",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hive_id": {
                        "type": "string",
                        "description": "Hive ID（省略時は現在のHive）",
                    },
                    "include_colonies": {
                        "type": "boolean",
                        "description": "Colony情報を含めるか",
                        "default": True,
                    },
                },
            },
        },
        {
            "name": "create_hive",
            "description": "新しいHiveを作成",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Hive名"},
                    "goal": {"type": "string", "description": "プロジェクトの目標"},
                },
                "required": ["name", "goal"],
            },
        },
        {
            "name": "create_colony",
            "description": "新しいColonyを作成",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "所属Hive ID"},
                    "name": {"type": "string", "description": "Colony名"},
                    "domain": {
                        "type": "string",
                        "description": "専門領域の説明",
                    },
                },
                "required": ["hive_id", "name", "domain"],
            },
        },
        {
            "name": "list_hives",
            "description": "Hive一覧を取得",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_colonies",
            "description": "Colony一覧を取得",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hive_id": {"type": "string", "description": "Hive ID"},
                },
                "required": ["hive_id"],
            },
        },
        {
            "name": "approve",
            "description": "承認待ちの操作を承認する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "承認リクエストID"},
                    "comment": {"type": "string", "description": "コメント"},
                },
                "required": ["request_id"],
            },
        },
        {
            "name": "reject",
            "description": "承認待ちの操作を拒否する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "承認リクエストID"},
                    "reason": {"type": "string", "description": "拒否理由"},
                },
                "required": ["request_id", "reason"],
            },
        },
        {
            "name": "emergency_stop",
            "description": "全ての作業を緊急停止する",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "停止理由"},
                    "scope": {
                        "type": "string",
                        "enum": ["all", "hive", "colony"],
                        "description": "停止範囲",
                        "default": "all",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "対象ID（scope=hive/colonyの場合）",
                    },
                },
                "required": ["reason"],
            },
        },
    ]
