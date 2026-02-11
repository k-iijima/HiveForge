"""MCP ツール定義パッケージ

MCPで公開するツールのスキーマ定義。
ドメインごとにファイルを分割し、ここで集約する。
"""

from mcp.types import Tool

from .beekeeper import get_beekeeper_tools
from .colony import get_colony_tools
from .conference import get_conference_tools
from .github import get_github_tools
from .guard_bee import get_guard_bee_tools
from .hive import get_hive_tools
from .intervention import get_intervention_tools
from .run import get_run_tools
from .task import get_task_tools


def get_tool_definitions() -> list[Tool]:
    """利用可能なツール一覧を取得"""
    return [
        *get_hive_tools(),
        *get_colony_tools(),
        *get_run_tools(),
        *get_task_tools(),
        *get_conference_tools(),
        *get_intervention_tools(),
        *get_guard_bee_tools(),
        *get_beekeeper_tools(),
        *get_github_tools(),
    ]
