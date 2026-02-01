"""Action Class - 操作のリスク分類とTrust Level連携

外部フィードバック対応: 操作をリスクレベルで分類し、
Trust Levelと組み合わせて確認要否を判定する。

Action Class:
    - READ_ONLY: 読み取り専用、副作用なし
    - REVERSIBLE: 元に戻せる操作（Git管理下のファイル編集等）
    - IRREVERSIBLE: 元に戻せない/高リスク操作（本番DB変更等）

Trust Level:
    - Level 0: 報告のみ
    - Level 1: 提案＋確認（デフォルト）
    - Level 2: 自動＋通知
    - Level 3: 完全委任
"""

from enum import Enum
from typing import Any


class ActionClass(str, Enum):
    """操作の分類（リスクレベル）"""

    READ_ONLY = "read_only"  # 読み取り専用、副作用なし
    REVERSIBLE = "reversible"  # 元に戻せる操作
    IRREVERSIBLE = "irreversible"  # 元に戻せない/高リスク操作


class TrustLevel(int, Enum):
    """委任レベル"""

    REPORT_ONLY = 0  # 全ての判断をユーザーに確認
    PROPOSE_CONFIRM = 1  # 提案するが実行前に確認（デフォルト）
    AUTO_NOTIFY = 2  # 自動実行するが結果を通知
    FULL_DELEGATION = 3  # 自動実行、問題時のみ通知


# ツール名からActionClassへのマッピング
_READ_ONLY_TOOLS = frozenset(
    [
        "read_file",
        "grep_search",
        "semantic_search",
        "file_search",
        "list_dir",
        "get_errors",
        "terminal_selection",
        "terminal_last_command",
    ]
)

_IRREVERSIBLE_TOOLS = frozenset(
    [
        "run_sql",
        "deploy",
        "publish",
        "delete_production",
        "send_email",
        "external_api_call",
    ]
)


def classify_action(tool_name: str, params: dict[str, Any]) -> ActionClass:
    """ツール名とパラメータからActionClassを判定

    Args:
        tool_name: MCPツール名
        params: ツールパラメータ（将来の拡張用）

    Returns:
        判定されたActionClass
    """
    if tool_name in _READ_ONLY_TOOLS:
        return ActionClass.READ_ONLY
    elif tool_name in _IRREVERSIBLE_TOOLS:
        return ActionClass.IRREVERSIBLE
    else:
        # 未知のツールは REVERSIBLE（安全側に倒す）
        return ActionClass.REVERSIBLE


def requires_confirmation(
    trust_level: TrustLevel,
    action_class: ActionClass,
    *,
    allow_irreversible_skip: bool = False,
) -> bool:
    """Trust LevelとAction Classから確認要否を判定

    Trust Level × Action Class マトリクス:
    | | Read-only | Reversible | Irreversible |
    |---|:---:|:---:|:---:|
    | Level 0 | 自動 | 確認必須 | 確認必須 |
    | Level 1 | 自動 | 確認必須 | 確認必須 |
    | Level 2 | 自動 | 自動+通知 | 確認必須 |
    | Level 3 | 自動 | 自動 | 確認推奨 |

    Args:
        trust_level: 委任レベル
        action_class: 操作分類
        allow_irreversible_skip: Trueの場合、Level 3でIRREVERSIBLEも確認スキップ

    Returns:
        True: 確認が必要
        False: 確認不要（自動実行可）
    """
    # READ_ONLY はどのレベルでも確認不要
    if action_class == ActionClass.READ_ONLY:
        return False

    # REVERSIBLE は Level 2以上で確認不要
    if action_class == ActionClass.REVERSIBLE:
        return trust_level.value < TrustLevel.AUTO_NOTIFY.value

    # IRREVERSIBLE は Level 3 でもデフォルトは確認必須
    if action_class == ActionClass.IRREVERSIBLE:
        if trust_level == TrustLevel.FULL_DELEGATION and allow_irreversible_skip:
            return False
        return True

    # フォールバック: 確認必須
    return True
