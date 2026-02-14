"""RefereeComparer テスト — Best-of-N Spec 比較（§5.7）.

複数の SpecDraft を比較し、testability / risk_coverage / clarity /
completeness の4軸で採点して最良の草案を選択する。
"""

from __future__ import annotations

import pytest

from colonyforge.requirement_analysis.models import (
    AcceptanceCriterion,
    RefereeResult,
    SpecDraft,
)
from colonyforge.requirement_analysis.referee_comparer import RefereeComparer

# ---------------------------------------------------------------------------
# ヘルパー: テスト用 SpecDraft 生成
# ---------------------------------------------------------------------------


def _make_draft(
    *,
    draft_id: str = "draft-1",
    version: int = 1,
    goal: str = "テスト機能を実装する",
    acceptance_criteria: list[str | AcceptanceCriterion] | None = None,
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
    open_items: list[str] | None = None,
    risk_mitigations: list[str] | None = None,
) -> SpecDraft:
    """テスト用の SpecDraft を簡易生成する."""
    return SpecDraft(
        draft_id=draft_id,
        version=version,
        goal=goal,
        acceptance_criteria=acceptance_criteria or ["デフォルト基準"],
        constraints=constraints or [],
        non_goals=non_goals or [],
        open_items=open_items or [],
        risk_mitigations=risk_mitigations or [],
    )


def _make_criterion(text: str, *, measurable: bool = False) -> AcceptanceCriterion:
    """テスト用の AcceptanceCriterion を簡易生成する."""
    return AcceptanceCriterion(text=text, measurable=measurable)


# ---------------------------------------------------------------------------
# 単一草案 → そのまま選択
# ---------------------------------------------------------------------------


class TestSingleDraft:
    """草案が1つしかない場合はそのまま選択される."""

    def test_single_draft_selected(self) -> None:
        """草案1つの場合、その草案が選択される."""
        # Arrange
        draft = _make_draft(draft_id="only-one")
        comparer = RefereeComparer()

        # Act
        result = comparer.compare([draft], draft_ids=["only-one"])

        # Assert
        assert isinstance(result, RefereeResult)
        assert result.selected_draft_id == "only-one"
        assert len(result.scores) == 1

    def test_single_draft_has_scores(self) -> None:
        """単一草案でも全4軸のスコアが算出される."""
        # Arrange
        draft = _make_draft(
            acceptance_criteria=[
                _make_criterion("レスポンス200を返す", measurable=True),
            ],
            risk_mitigations=["タイムアウト時はリトライする"],
        )
        comparer = RefereeComparer()

        # Act
        result = comparer.compare([draft], draft_ids=["d1"])

        # Assert: 全軸にスコアがある
        score = result.scores[0]
        assert 0.0 <= score.testability <= 1.0
        assert 0.0 <= score.risk_coverage <= 1.0
        assert 0.0 <= score.clarity <= 1.0
        assert 0.0 <= score.completeness <= 1.0
        assert 0.0 <= score.total <= 1.0


# ---------------------------------------------------------------------------
# 複数草案の比較
# ---------------------------------------------------------------------------


class TestMultipleDrafts:
    """複数草案を比較して最良のものを選択する."""

    def test_better_draft_selected(self) -> None:
        """テスト可能な受入基準が多い草案が優先される."""
        # Arrange: draft_a は最小限、draft_b は measurable な基準 + リスク緩和あり
        draft_a = _make_draft(
            acceptance_criteria=["なんか動く"],
        )
        draft_b = _make_draft(
            goal="この仕様はユーザー認証機能の詳細設計である",
            acceptance_criteria=[
                _make_criterion("200 OK を返す", measurable=True),
                _make_criterion("レスポンスに user_id を含む", measurable=True),
            ],
            risk_mitigations=["認証エラー時はスタックトレースを隠蔽する"],
            constraints=["レスポンスタイム 500ms 以下"],
        )
        comparer = RefereeComparer()

        # Act
        result = comparer.compare(
            [draft_a, draft_b],
            draft_ids=["a", "b"],
        )

        # Assert: draft_b が選択される
        assert result.selected_draft_id == "b"
        assert len(result.scores) == 2

    def test_scores_ordered_by_draft_ids(self) -> None:
        """scores は draft_ids の順序で返される."""
        # Arrange
        drafts = [_make_draft(), _make_draft(), _make_draft()]
        ids = ["x", "y", "z"]
        comparer = RefereeComparer()

        # Act
        result = comparer.compare(drafts, draft_ids=ids)

        # Assert: scores の draft_id が ids 順
        assert [s.draft_id for s in result.scores] == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# スコア算出ロジック
# ---------------------------------------------------------------------------


class TestScoring:
    """個別スコアの算出ロジック."""

    def test_testability_increases_with_measurable_criteria(self) -> None:
        """measurable な受入基準が多いとテスト可能性スコアが上がる."""
        # Arrange
        draft_few = _make_draft(
            acceptance_criteria=["動く"],
        )
        draft_many = _make_draft(
            acceptance_criteria=[
                _make_criterion("200 を返す", measurable=True),
                _make_criterion("応答時間 < 500ms", measurable=True),
                _make_criterion("JSON形式", measurable=True),
            ],
        )
        comparer = RefereeComparer()

        # Act
        r_few = comparer.compare([draft_few], draft_ids=["few"])
        r_many = comparer.compare([draft_many], draft_ids=["many"])

        # Assert
        assert r_many.scores[0].testability > r_few.scores[0].testability

    def test_risk_coverage_increases_with_mitigations(self) -> None:
        """リスク緩和策が多いとリスクカバレッジスコアが上がる."""
        # Arrange
        draft_no_risk = _make_draft()
        draft_with_risk = _make_draft(
            risk_mitigations=[
                "タイムアウト時はリトライする",
                "メモリ使用量を監視する",
            ],
        )
        comparer = RefereeComparer()

        # Act
        r_no = comparer.compare([draft_no_risk], draft_ids=["no"])
        r_with = comparer.compare([draft_with_risk], draft_ids=["with"])

        # Assert
        assert r_with.scores[0].risk_coverage > r_no.scores[0].risk_coverage

    def test_clarity_increases_with_goal_length(self) -> None:
        """目標が詳細なほど明瞭性スコアが上がる."""
        # Arrange
        draft_short = _make_draft(goal="X")
        draft_long = _make_draft(
            goal="この仕様はユーザー認証機能の詳細設計であり、"
            "OAuth2フローの各ステップを明確に定義する。",
        )
        comparer = RefereeComparer()

        # Act
        r_short = comparer.compare([draft_short], draft_ids=["short"])
        r_long = comparer.compare([draft_long], draft_ids=["long"])

        # Assert
        assert r_long.scores[0].clarity > r_short.scores[0].clarity

    def test_completeness_combines_all_factors(self) -> None:
        """completeness は全要素の有無で決まる."""
        # Arrange: 全要素が揃った草案
        draft = _make_draft(
            goal="完全な仕様の目標説明",
            acceptance_criteria=[_make_criterion("基準1", measurable=True)],
            constraints=["制約1"],
            non_goals=["スコープ外事項"],
            risk_mitigations=["対策1"],
        )
        comparer = RefereeComparer()

        # Act
        result = comparer.compare([draft], draft_ids=["complete"])

        # Assert: completeness > 0.5 (全要素あり)
        assert result.scores[0].completeness > 0.5

    def test_total_is_weighted_average(self) -> None:
        """total は各軸の加重平均である."""
        # Arrange
        draft = _make_draft(
            acceptance_criteria=[_make_criterion("基準", measurable=True)],
            risk_mitigations=["対策"],
        )
        comparer = RefereeComparer()

        # Act
        result = comparer.compare([draft], draft_ids=["d1"])
        score = result.scores[0]

        # Assert: total は各軸の加重平均 (±0.01)
        expected = (
            score.testability * 0.3
            + score.risk_coverage * 0.25
            + score.clarity * 0.2
            + score.completeness * 0.25
        )
        assert abs(score.total - expected) < 0.01


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------


class TestValidation:
    """入力バリデーション."""

    def test_empty_drafts_raises(self) -> None:
        """空の草案リストは ValueError."""
        comparer = RefereeComparer()
        with pytest.raises(ValueError, match="drafts"):
            comparer.compare([], draft_ids=[])

    def test_mismatched_ids_raises(self) -> None:
        """drafts と draft_ids の長さ不一致は ValueError."""
        comparer = RefereeComparer()
        with pytest.raises(ValueError, match="length"):
            comparer.compare(
                [_make_draft()],
                draft_ids=["a", "b"],
            )
