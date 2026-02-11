"""Guard Bee 関連ツール定義"""

from mcp.types import Tool


def get_guard_bee_tools() -> list[Tool]:
    """Guard Bee (品質検証) ツール"""
    return [
        Tool(
            name="verify_colony",
            description=(
                "Colony成果物をGuard Beeで品質検証します。"
                "差分・テスト・カバレッジ・Lint等の証拠を提出し、"
                "L1/L2の2層検証を実行します。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "colony_id": {
                        "type": "string",
                        "description": "検証対象のColony ID",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "検証対象のTask ID",
                    },
                    "evidence": {
                        "type": "array",
                        "description": "収集された証拠リスト",
                        "items": {
                            "type": "object",
                            "properties": {
                                "evidence_type": {
                                    "type": "string",
                                    "description": (
                                        "証拠タイプ (diff, test_result, "
                                        "test_coverage, lint_result, "
                                        "type_check, review_comment)"
                                    ),
                                },
                                "source": {
                                    "type": "string",
                                    "description": "証拠の出所",
                                },
                                "content": {
                                    "type": "object",
                                    "description": "証拠の内容",
                                },
                            },
                            "required": ["evidence_type", "source", "content"],
                        },
                    },
                    "context": {
                        "type": "object",
                        "description": "追加コンテキスト（オプション）",
                    },
                },
                "required": ["colony_id", "task_id", "evidence"],
            },
        ),
        Tool(
            name="get_guard_report",
            description="Run配下のGuard Bee検証レポート一覧を取得します。",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "Run ID（省略時は現在のRun）",
                    },
                },
            },
        ),
    ]
