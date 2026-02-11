"""Intervention (介入・エスカレーション) 関連ツール定義"""

from mcp.types import Tool


def get_intervention_tools() -> list[Tool]:
    """直接介入・エスカレーション・フィードバックツール"""
    return [
        Tool(
            name="user_intervene",
            description=(
                "ユーザー直接介入を作成します。Beekeeperをバイパスして直接指示を出します。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "対象Colony ID",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "直接指示内容",
                    },
                    "reason": {"type": "string", "description": "介入理由"},
                    "share_with_beekeeper": {
                        "type": "boolean",
                        "description": "Beekeeperにも共有するか",
                        "default": True,
                    },
                },
                "required": ["colony_id", "instruction"],
            },
        ),
        Tool(
            name="queen_escalate",
            description=(
                "Queen Beeからの直訴を作成します。"
                "Beekeeperとの調整で解決できない問題を"
                "ユーザーにエスカレーションします。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "Queen BeeのColony ID",
                    },
                    "escalation_type": {
                        "type": "string",
                        "description": (
                            "エスカレーション種別 "
                            "(beekeeper_conflict, resource_shortage, "
                            "technical_blocker, scope_clarification, "
                            "priority_dispute, external_dependency)"
                        ),
                    },
                    "summary": {"type": "string", "description": "問題の要約"},
                    "details": {"type": "string", "description": "詳細説明"},
                    "suggested_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "提案するアクション",
                    },
                    "beekeeper_context": {
                        "type": "string",
                        "description": "Beekeeperとのやり取り経緯",
                    },
                },
                "required": ["colony_id", "escalation_type", "summary"],
            },
        ),
        Tool(
            name="beekeeper_feedback",
            description=(
                "Beekeeperフィードバックを記録します。"
                "直接介入やエスカレーション解決後の改善点を記録します。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "escalation_id": {
                        "type": "string",
                        "description": "対応したエスカレーション/介入のID",
                    },
                    "resolution": {"type": "string", "description": "解決方法"},
                    "beekeeper_adjustment": {
                        "type": "object",
                        "description": "Beekeeperへの調整内容",
                    },
                    "lesson_learned": {
                        "type": "string",
                        "description": "学んだ教訓",
                    },
                },
                "required": ["escalation_id", "resolution"],
            },
        ),
        Tool(
            name="list_escalations",
            description="エスカレーション一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "Colony IDでフィルタ（オプション）",
                    },
                    "status": {
                        "type": "string",
                        "description": "ステータスでフィルタ (pending, resolved)",
                    },
                },
            },
        ),
        Tool(
            name="get_escalation",
            description="エスカレーションの詳細情報を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "escalation_id": {
                        "type": "string",
                        "description": "エスカレーションID",
                    },
                },
                "required": ["escalation_id"],
            },
        ),
    ]
