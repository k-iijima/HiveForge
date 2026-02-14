"""AmbiguityScorer テスト — §5.9 + §8 高速パス判定.

AmbiguityScorer は入力テキストから3軸スコア（ambiguity, context_sufficiency,
execution_risk）を算出し、分析パスを決定する純粋ロジックコンポーネント。
"""

from __future__ import annotations

import pytest

from colonyforge.requirement_analysis.models import (
    AmbiguityScores,
    AnalysisPath,
)
from colonyforge.requirement_analysis.scorer import AmbiguityScorer

# ---------------------------------------------------------------------------
# AmbiguityScores モデルテスト（§5.9）
# ---------------------------------------------------------------------------


class TestAmbiguityScoresModel:
    """AmbiguityScores Pydantic モデルの検証."""

    def test_create_valid_scores(self) -> None:
        """有効なスコアでインスタンスが作成できる."""
        # Arrange & Act
        scores = AmbiguityScores(
            ambiguity=0.5,
            context_sufficiency=0.6,
            execution_risk=0.3,
        )

        # Assert
        assert scores.ambiguity == 0.5
        assert scores.context_sufficiency == 0.6
        assert scores.execution_risk == 0.3

    def test_frozen(self) -> None:
        """frozen=True で値変更が禁止される."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.5, context_sufficiency=0.6, execution_risk=0.3)

        # Act & Assert: 変更を試みるとエラー
        with pytest.raises(Exception):
            scores.ambiguity = 0.9  # type: ignore[misc]

    def test_boundary_values(self) -> None:
        """0.0 と 1.0 の境界値が受け入れられる."""
        # Arrange & Act
        scores_min = AmbiguityScores(ambiguity=0.0, context_sufficiency=0.0, execution_risk=0.0)
        scores_max = AmbiguityScores(ambiguity=1.0, context_sufficiency=1.0, execution_risk=1.0)

        # Assert
        assert scores_min.ambiguity == 0.0
        assert scores_max.ambiguity == 1.0

    def test_out_of_range_raises(self) -> None:
        """範囲外の値は ValidationError."""
        with pytest.raises(Exception):
            AmbiguityScores(ambiguity=1.5, context_sufficiency=0.5, execution_risk=0.3)

        with pytest.raises(Exception):
            AmbiguityScores(ambiguity=0.5, context_sufficiency=-0.1, execution_risk=0.3)


class TestNeedsClarification:
    """needs_clarification プロパティの判定ロジック（§5.9）."""

    def test_high_ambiguity_low_context(self) -> None:
        """A≥0.7 かつ C≤0.3 → 質問必須."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.8, context_sufficiency=0.2, execution_risk=0.1)

        # Act & Assert
        assert scores.needs_clarification is True

    def test_low_context_alone(self) -> None:
        """C<0.3 単独で質問必須（曖昧度に関係なく）."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.3, context_sufficiency=0.1, execution_risk=0.1)

        # Act & Assert
        assert scores.needs_clarification is True

    def test_high_execution_risk(self) -> None:
        """R≥0.8 → 影響大で質問必須."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.2, context_sufficiency=0.9, execution_risk=0.9)

        # Act & Assert
        assert scores.needs_clarification is True

    def test_moderate_all(self) -> None:
        """中程度のスコア → 質問不要."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.5, context_sufficiency=0.5, execution_risk=0.5)

        # Act & Assert
        assert scores.needs_clarification is False

    def test_low_all(self) -> None:
        """全スコア低い → 質問不要（Instant Pass 相当）."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.1, context_sufficiency=0.9, execution_risk=0.1)

        # Act & Assert
        assert scores.needs_clarification is False


class TestCanProceedWithAssumptions:
    """can_proceed_with_assumptions プロパティの判定ロジック."""

    def test_sufficient_context_low_risk(self) -> None:
        """C≥0.3 かつ A<0.7 かつ R<0.5 → 仮説で進行可能."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.5, context_sufficiency=0.5, execution_risk=0.3)

        # Act & Assert
        assert scores.can_proceed_with_assumptions is True

    def test_high_ambiguity_blocks(self) -> None:
        """A≥0.7 → 仮説進行不可."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.8, context_sufficiency=0.5, execution_risk=0.3)

        # Act & Assert
        assert scores.can_proceed_with_assumptions is False

    def test_high_risk_blocks(self) -> None:
        """R≥0.5 → 仮説進行不可."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.3, context_sufficiency=0.5, execution_risk=0.6)

        # Act & Assert
        assert scores.can_proceed_with_assumptions is False

    def test_low_context_blocks(self) -> None:
        """C<0.3 → 仮説進行不可."""
        # Arrange
        scores = AmbiguityScores(ambiguity=0.3, context_sufficiency=0.2, execution_risk=0.3)

        # Act & Assert
        assert scores.can_proceed_with_assumptions is False


# ---------------------------------------------------------------------------
# AmbiguityScorer テスト
# ---------------------------------------------------------------------------


class TestAmbiguityScorerInit:
    """AmbiguityScorer の初期化."""

    def test_default_thresholds(self) -> None:
        """デフォルト閾値で初期化される（§8 + §13 設定値）."""
        # Arrange & Act
        scorer = AmbiguityScorer()

        # Assert: デフォルト閾値は §13 RequirementAnalysisConfig に準拠
        assert scorer.instant_pass_ambiguity == 0.3
        assert scorer.instant_pass_risk == 0.3
        assert scorer.assumption_pass_ambiguity == 0.7
        assert scorer.assumption_pass_risk == 0.5

    def test_custom_thresholds(self) -> None:
        """カスタム閾値で初期化できる."""
        # Arrange & Act
        scorer = AmbiguityScorer(
            instant_pass_ambiguity=0.2,
            instant_pass_risk=0.2,
            assumption_pass_ambiguity=0.6,
            assumption_pass_risk=0.4,
        )

        # Assert
        assert scorer.instant_pass_ambiguity == 0.2
        assert scorer.assumption_pass_ambiguity == 0.6


class TestScoreText:
    """score_text() — テキストの曖昧さスコア算出."""

    def test_clear_text_low_ambiguity(self) -> None:
        """明確なテキストは低い ambiguity スコアを返す.

        「テストを実行して」のような具体的な指示は ambiguity が低い。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("pytest tests/ を実行してください")

        # Assert: 具体的な指示なので ambiguity は低め
        assert scores.ambiguity < 0.5

    def test_vague_text_high_ambiguity(self) -> None:
        """曖昧なテキストは高い ambiguity スコアを返す.

        「いい感じにして」のような曖昧な指示は ambiguity が高い。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("いい感じに改善して")

        # Assert: 曖昧な指示なので ambiguity は高め
        assert scores.ambiguity >= 0.5

    def test_security_text_high_risk(self) -> None:
        """セキュリティ関連のテキストは高い execution_risk を返す.

        認証・暗号化等のキーワードを含む要求は誤実装時の影響が大きい。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("ユーザー認証機能を実装して、パスワードのハッシュ化が必要")

        # Assert: セキュリティ関連は execution_risk が高い
        assert scores.execution_risk >= 0.5

    def test_trivial_text_low_risk(self) -> None:
        """軽微な作業テキストは低い execution_risk を返す."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("READMEのタイポを直して")

        # Assert: タイポ修正は影響が小さい
        assert scores.execution_risk < 0.5

    def test_returns_ambiguity_scores_type(self) -> None:
        """返り値は AmbiguityScores 型."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        result = scorer.score_text("何かして")

        # Assert
        assert isinstance(result, AmbiguityScores)

    def test_context_sufficiency_default(self) -> None:
        """context_sufficiency はデフォルトで低い値（証拠収集前）.

        Context Forager（Phase 2）実装前は証拠がないため低い初期値。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("ログイン機能を作って")

        # Assert: 初期状態では context_sufficiency は低い
        assert 0.0 <= scores.context_sufficiency <= 1.0

    def test_empty_text_high_ambiguity(self) -> None:
        """空に近いテキストは高い ambiguity."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text("")

        # Assert
        assert scores.ambiguity >= 0.8

    def test_score_text_with_context_sufficiency(self) -> None:
        """context_sufficiency を外部から指定できる.

        Context Forager が証拠収集後に再スコアリングする際に使用。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text(
            "ログイン機能を作って",
            context_sufficiency=0.8,
        )

        # Assert: 指定値がそのまま使われる
        assert scores.context_sufficiency == 0.8


class TestScoreTextVagueWords:
    """曖昧語の検出テスト — ambiguity スコアに影響する語彙."""

    @pytest.mark.parametrize(
        "text,expected_high",
        [
            ("適切に処理して", True),
            ("いい感じにして", True),
            ("なんとなく改善して", True),
            ("うまくやって", True),
            ("pytest tests/test_api.py を実行", False),
            ("src/auth.py の 42行目を修正", False),
        ],
        ids=[
            "適切に",
            "いい感じに",
            "なんとなく",
            "うまく",
            "具体的コマンド",
            "具体的ファイル",
        ],
    )
    def test_vague_word_detection(self, text: str, expected_high: bool) -> None:
        """曖昧語を含むテキストは高スコア、具体的テキストは低スコア."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text(text)

        # Assert
        if expected_high:
            assert scores.ambiguity >= 0.5, f"'{text}' should have high ambiguity"
        else:
            assert scores.ambiguity < 0.5, f"'{text}' should have low ambiguity"


class TestScoreTextRiskKeywords:
    """execution_risk に影響するキーワード検出テスト."""

    @pytest.mark.parametrize(
        "text,expected_high",
        [
            ("認証機能を実装", True),
            ("データベースマイグレーション", True),
            ("暗号化処理を追加", True),
            ("決済処理を実装", True),
            ("READMEにバッジを追加", False),
            ("テストを実行して", False),
        ],
        ids=[
            "認証",
            "DBマイグレーション",
            "暗号化",
            "決済",
            "README編集",
            "テスト実行",
        ],
    )
    def test_risk_keyword_detection(self, text: str, expected_high: bool) -> None:
        """リスクキーワードを含むテキストは高スコア."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores = scorer.score_text(text)

        # Assert
        if expected_high:
            assert scores.execution_risk >= 0.5, f"'{text}' should have high risk"
        else:
            assert scores.execution_risk < 0.5, f"'{text}' should have low risk"


# ---------------------------------------------------------------------------
# determine_path() — 高速パス判定（§8）
# ---------------------------------------------------------------------------


class TestDeterminePath:
    """determine_path() — AmbiguityScores から AnalysisPath を決定."""

    def test_instant_pass(self) -> None:
        """ambiguity<0.3, context_sufficiency>0.8, execution_risk<0.3 → INSTANT_PASS.

        使用例: 「テストを実行して」「READMEのタイポを直して」
        """
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.1, context_sufficiency=0.9, execution_risk=0.1)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.INSTANT_PASS

    def test_assumption_pass(self) -> None:
        """ambiguity<0.7, execution_risk<0.5 → ASSUMPTION_PASS.

        使用例: 過去に類似実装があり、文脈が十分な要求
        """
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.5, context_sufficiency=0.6, execution_risk=0.3)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.ASSUMPTION_PASS

    def test_full_analysis_high_ambiguity(self) -> None:
        """ambiguity≥0.7 → FULL_ANALYSIS.

        使用例: 新規機能、アーキテクチャ変更
        """
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.8, context_sufficiency=0.5, execution_risk=0.3)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.FULL_ANALYSIS

    def test_full_analysis_high_risk(self) -> None:
        """execution_risk≥0.5 → FULL_ANALYSIS（ambiguityに関係なく）.

        使用例: セキュリティ関連の要求
        """
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.3, context_sufficiency=0.8, execution_risk=0.6)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.FULL_ANALYSIS

    def test_instant_pass_boundary(self) -> None:
        """Instant Pass 境界値: ambiguity=0.29, risk=0.29, context=0.81."""
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.29, context_sufficiency=0.81, execution_risk=0.29)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.INSTANT_PASS

    def test_instant_pass_fails_at_boundary(self) -> None:
        """Instant Pass 失敗境界: ambiguity=0.3（等号は不合格）."""
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.3, context_sufficiency=0.9, execution_risk=0.1)

        # Act
        path = scorer.determine_path(scores)

        # Assert: ambiguity==0.3 は Instant Pass 不可（< 0.3 ではない）
        assert path != AnalysisPath.INSTANT_PASS

    def test_assumption_pass_boundary(self) -> None:
        """Assumption Pass 境界: ambiguity=0.69, risk=0.49."""
        # Arrange
        scorer = AmbiguityScorer()
        scores = AmbiguityScores(ambiguity=0.69, context_sufficiency=0.5, execution_risk=0.49)

        # Act
        path = scorer.determine_path(scores)

        # Assert
        assert path == AnalysisPath.ASSUMPTION_PASS

    def test_custom_thresholds_affect_path(self) -> None:
        """カスタム閾値が判定に反映される."""
        # Arrange: 閾値を緩くする
        scorer = AmbiguityScorer(
            instant_pass_ambiguity=0.5,
            instant_pass_risk=0.5,
        )
        scores = AmbiguityScores(ambiguity=0.4, context_sufficiency=0.9, execution_risk=0.4)

        # Act
        path = scorer.determine_path(scores)

        # Assert: カスタム閾値では Instant Pass になる
        assert path == AnalysisPath.INSTANT_PASS


# ---------------------------------------------------------------------------
# score_and_determine() — 一括実行
# ---------------------------------------------------------------------------


class TestScoreAndDetermine:
    """score_and_determine() — テキストからスコア算出+パス判定を一括実行."""

    def test_trivial_task_instant_pass(self) -> None:
        """軽微なタスクは Instant Pass.

        context_sufficiency を高く設定すると InstantPass になりうる。
        """
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores, path = scorer.score_and_determine(
            "テストを実行して",
            context_sufficiency=0.9,
        )

        # Assert
        assert isinstance(scores, AmbiguityScores)
        assert isinstance(path, AnalysisPath)
        assert path == AnalysisPath.INSTANT_PASS

    def test_complex_task_full_analysis(self) -> None:
        """複雑なタスクは Full Analysis."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        scores, path = scorer.score_and_determine(
            "認証システムをいい感じに改善して、セキュリティも考慮して",
        )

        # Assert
        assert path == AnalysisPath.FULL_ANALYSIS

    def test_returns_tuple(self) -> None:
        """戻り値は (AmbiguityScores, AnalysisPath) のタプル."""
        # Arrange
        scorer = AmbiguityScorer()

        # Act
        result = scorer.score_and_determine("何かして")

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], AmbiguityScores)
        assert isinstance(result[1], AnalysisPath)
