"""QueenDelegationMixin._format_queen_result テスト.

Queen Bee の実行結果を文字列にフォーマットするメソッドの
4つの分岐パスを検証する。
"""

from __future__ import annotations

from colonyforge.beekeeper.queen_delegation import QueenDelegationMixin


class TestFormatQueenResult:
    """_format_queen_result の全4分岐を検証."""

    def _make_mixin(self) -> QueenDelegationMixin:
        """素の Mixin を生成（_format_queen_result は self の他属性に依存しない）."""
        return QueenDelegationMixin()

    def test_completed_status_with_outputs(self) -> None:
        """status=completed: タスク完了メッセージと LLM 出力を結合する."""
        # Arrange
        mixin = self._make_mixin()
        result = {
            "status": "completed",
            "tasks_completed": 3,
            "tasks_total": 3,
            "results": [
                {"llm_output": "結果A"},
                {"llm_output": "結果B"},
            ],
        }

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert "タスク完了 (3/3)" in formatted
        assert "結果A" in formatted
        assert "結果B" in formatted

    def test_completed_status_without_outputs(self) -> None:
        """status=completed + results 空: 出力テキストなし."""
        # Arrange
        mixin = self._make_mixin()
        result = {
            "status": "completed",
            "tasks_completed": 1,
            "tasks_total": 1,
            "results": [],
        }

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert "タスク完了 (1/1)" in formatted

    def test_partial_status(self) -> None:
        """status=partial: 一部タスク完了メッセージ."""
        # Arrange
        mixin = self._make_mixin()
        result = {
            "status": "partial",
            "tasks_completed": 2,
            "tasks_total": 5,
            "results": [{"llm_output": "途中結果"}],
        }

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert "一部タスク完了 (2/5)" in formatted
        assert "途中結果" in formatted

    def test_rejected_status(self) -> None:
        """status=rejected: 拒否理由を返す."""
        # Arrange
        mixin = self._make_mixin()
        result = {"status": "rejected", "reason": "権限不足"}

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert formatted == "拒否されました: 権限不足"

    def test_error_status_default(self) -> None:
        """status が未知（else分岐）: タスク失敗メッセージ."""
        # Arrange
        mixin = self._make_mixin()
        result = {"status": "failed", "error": "接続エラー"}

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert formatted == "タスク失敗: 接続エラー"

    def test_error_status_unknown(self) -> None:
        """error キーがない場合: Unknown error."""
        # Arrange
        mixin = self._make_mixin()
        result = {"status": "unknown_status"}

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert formatted == "タスク失敗: Unknown error"

    def test_completed_results_with_non_dict_items(self) -> None:
        """results 内に dict でない要素がある場合: スキップされる."""
        # Arrange
        mixin = self._make_mixin()
        result = {
            "status": "completed",
            "tasks_completed": 2,
            "tasks_total": 2,
            "results": [
                "not_a_dict",
                {"llm_output": "有効"},
                {"no_llm_output_key": True},
            ],
        }

        # Act
        formatted = mixin._format_queen_result(result)

        # Assert
        assert "タスク完了 (2/2)" in formatted
        assert "有効" in formatted
        assert "not_a_dict" not in formatted
