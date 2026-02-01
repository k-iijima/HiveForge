"""Action Class（操作分類）のテスト

外部フィードバック対応: 操作をリスクレベルで分類し、Trust Levelと連携。
"""

import pytest

from hiveforge.core.models.action_class import (
    ActionClass,
    TrustLevel,
    classify_action,
    requires_confirmation,
)


class TestActionClass:
    """ActionClass Enum のテスト"""

    def test_read_only_action_class(self):
        """READ_ONLY は読み取り専用操作を表す"""
        # Assert
        assert ActionClass.READ_ONLY.value == "read_only"

    def test_reversible_action_class(self):
        """REVERSIBLE は元に戻せる操作を表す"""
        # Assert
        assert ActionClass.REVERSIBLE.value == "reversible"

    def test_irreversible_action_class(self):
        """IRREVERSIBLE は元に戻せない/高リスク操作を表す"""
        # Assert
        assert ActionClass.IRREVERSIBLE.value == "irreversible"


class TestTrustLevel:
    """TrustLevel Enum のテスト"""

    def test_trust_level_report_only(self):
        """Level 0: 報告のみ"""
        assert TrustLevel.REPORT_ONLY.value == 0

    def test_trust_level_propose_confirm(self):
        """Level 1: 提案＋確認"""
        assert TrustLevel.PROPOSE_CONFIRM.value == 1

    def test_trust_level_auto_notify(self):
        """Level 2: 自動＋通知"""
        assert TrustLevel.AUTO_NOTIFY.value == 2

    def test_trust_level_full_delegation(self):
        """Level 3: 完全委任"""
        assert TrustLevel.FULL_DELEGATION.value == 3


class TestClassifyAction:
    """classify_action 関数のテスト"""

    def test_read_file_is_read_only(self):
        """read_file ツールは READ_ONLY"""
        # Act
        result = classify_action("read_file", {})

        # Assert
        assert result == ActionClass.READ_ONLY

    def test_grep_search_is_read_only(self):
        """grep_search ツールは READ_ONLY"""
        # Act
        result = classify_action("grep_search", {})

        # Assert
        assert result == ActionClass.READ_ONLY

    def test_semantic_search_is_read_only(self):
        """semantic_search ツールは READ_ONLY"""
        # Act
        result = classify_action("semantic_search", {})

        # Assert
        assert result == ActionClass.READ_ONLY

    def test_create_file_is_reversible(self):
        """create_file ツールは REVERSIBLE（Git管理下）"""
        # Act
        result = classify_action("create_file", {})

        # Assert
        assert result == ActionClass.REVERSIBLE

    def test_edit_file_is_reversible(self):
        """edit_file ツールは REVERSIBLE"""
        # Act
        result = classify_action("edit_file", {})

        # Assert
        assert result == ActionClass.REVERSIBLE

    def test_run_in_terminal_is_reversible(self):
        """run_in_terminal ツールは REVERSIBLE（デフォルト）"""
        # Act
        result = classify_action("run_in_terminal", {})

        # Assert
        assert result == ActionClass.REVERSIBLE

    def test_run_sql_is_irreversible(self):
        """run_sql ツールは IRREVERSIBLE"""
        # Act
        result = classify_action("run_sql", {})

        # Assert
        assert result == ActionClass.IRREVERSIBLE

    def test_deploy_is_irreversible(self):
        """deploy ツールは IRREVERSIBLE"""
        # Act
        result = classify_action("deploy", {})

        # Assert
        assert result == ActionClass.IRREVERSIBLE

    def test_publish_is_irreversible(self):
        """publish ツールは IRREVERSIBLE"""
        # Act
        result = classify_action("publish", {})

        # Assert
        assert result == ActionClass.IRREVERSIBLE

    def test_unknown_tool_defaults_to_reversible(self):
        """未知のツールは REVERSIBLE（安全側に倒す）"""
        # Act
        result = classify_action("unknown_new_tool", {})

        # Assert
        assert result == ActionClass.REVERSIBLE


class TestRequiresConfirmation:
    """requires_confirmation 関数のテスト

    Trust Level × Action Class マトリクス:
    | | Read-only | Reversible | Irreversible |
    |---|:---:|:---:|:---:|
    | Level 0 | 自動 | 確認必須 | 確認必須 |
    | Level 1 | 自動 | 確認必須 | 確認必須 |
    | Level 2 | 自動 | 自動+通知 | 確認必須 |
    | Level 3 | 自動 | 自動 | 確認推奨 |
    """

    # READ_ONLY はどのレベルでも確認不要
    def test_read_only_level_0_no_confirmation(self):
        """READ_ONLY + Level 0 = 確認不要"""
        assert requires_confirmation(TrustLevel.REPORT_ONLY, ActionClass.READ_ONLY) is False

    def test_read_only_level_3_no_confirmation(self):
        """READ_ONLY + Level 3 = 確認不要"""
        assert requires_confirmation(TrustLevel.FULL_DELEGATION, ActionClass.READ_ONLY) is False

    # REVERSIBLE は Level 0-1 で確認必須、Level 2-3 で不要
    def test_reversible_level_0_requires_confirmation(self):
        """REVERSIBLE + Level 0 = 確認必須"""
        assert requires_confirmation(TrustLevel.REPORT_ONLY, ActionClass.REVERSIBLE) is True

    def test_reversible_level_1_requires_confirmation(self):
        """REVERSIBLE + Level 1 = 確認必須"""
        assert requires_confirmation(TrustLevel.PROPOSE_CONFIRM, ActionClass.REVERSIBLE) is True

    def test_reversible_level_2_no_confirmation(self):
        """REVERSIBLE + Level 2 = 確認不要（通知あり）"""
        assert requires_confirmation(TrustLevel.AUTO_NOTIFY, ActionClass.REVERSIBLE) is False

    def test_reversible_level_3_no_confirmation(self):
        """REVERSIBLE + Level 3 = 確認不要"""
        assert requires_confirmation(TrustLevel.FULL_DELEGATION, ActionClass.REVERSIBLE) is False

    # IRREVERSIBLE は Level 0-2 で確認必須、Level 3 でも推奨（デフォルト確認必須）
    def test_irreversible_level_0_requires_confirmation(self):
        """IRREVERSIBLE + Level 0 = 確認必須"""
        assert requires_confirmation(TrustLevel.REPORT_ONLY, ActionClass.IRREVERSIBLE) is True

    def test_irreversible_level_1_requires_confirmation(self):
        """IRREVERSIBLE + Level 1 = 確認必須"""
        assert requires_confirmation(TrustLevel.PROPOSE_CONFIRM, ActionClass.IRREVERSIBLE) is True

    def test_irreversible_level_2_requires_confirmation(self):
        """IRREVERSIBLE + Level 2 = 確認必須"""
        assert requires_confirmation(TrustLevel.AUTO_NOTIFY, ActionClass.IRREVERSIBLE) is True

    def test_irreversible_level_3_requires_confirmation_by_default(self):
        """IRREVERSIBLE + Level 3 = 確認推奨（デフォルトは確認必須）"""
        assert requires_confirmation(TrustLevel.FULL_DELEGATION, ActionClass.IRREVERSIBLE) is True

    def test_irreversible_level_3_can_skip_with_override(self):
        """IRREVERSIBLE + Level 3 = オーバーライドで確認スキップ可"""
        assert (
            requires_confirmation(
                TrustLevel.FULL_DELEGATION,
                ActionClass.IRREVERSIBLE,
                allow_irreversible_skip=True,
            )
            is False
        )
