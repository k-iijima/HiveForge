"""GitHub Projection 関連ツール定義"""

from mcp.types import Tool


def get_github_tools() -> list[Tool]:
    """GitHub Projection (同期) ツール"""
    return [
        Tool(
            name="sync_run_to_github",
            description=(
                "指定RunのARイベントをGitHub Issues/Comments/Labelsに同期します。"
                "冪等なので何度実行しても安全です。"
                "run_idを省略すると現在のRunが対象になります。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "同期するRunのID（省略時は現在のRun）",
                    },
                },
            },
        ),
        Tool(
            name="get_github_sync_status",
            description=(
                "GitHub Projectionの同期状態を取得します。"
                "同期済みイベント数、Run→Issueマッピングなどを確認できます。"
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]
