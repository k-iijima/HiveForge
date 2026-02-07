"""Scout Bee（偵察蜂 / 編成最適化）のテスト

Honeycombの過去エピソードから類似タスクを検索し、
最適なColonyテンプレートを推薦する。
"""

from __future__ import annotations

from hiveforge.core.honeycomb.models import Episode, Outcome
from hiveforge.scout_bee.matcher import EpisodeMatcher, SimilarEpisode
from hiveforge.scout_bee.models import (
    OptimizationProposal,
    ScoutReport,
    ScoutVerdict,
    TemplateStats,
)

# ==================== M3-8-a: 類似エピソード検索ロジック ====================


def _make_episode(
    episode_id: str = "ep-001",
    run_id: str = "run-001",
    colony_id: str = "col-001",
    template_used: str = "balanced",
    task_features: dict[str, float] | None = None,
    outcome: Outcome = Outcome.SUCCESS,
    duration_seconds: float = 60.0,
    goal: str = "テストタスク",
) -> Episode:
    """テスト用Episodeを生成"""
    return Episode(
        episode_id=episode_id,
        run_id=run_id,
        colony_id=colony_id,
        template_used=template_used,
        task_features=task_features or {"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
        outcome=outcome,
        duration_seconds=duration_seconds,
        goal=goal,
    )


class TestEpisodeMatcher:
    """類似エピソード検索のテスト"""

    def test_empty_episodes_returns_empty(self):
        """エピソードがなければ空リスト"""
        # Arrange: 空リスト
        matcher = EpisodeMatcher()

        # Act: 類似検索
        results = matcher.find_similar(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
            episodes=[],
        )

        # Assert: 空
        assert results == []

    def test_identical_features_high_similarity(self):
        """同一特徴量は類似度1.0"""
        # Arrange: 同じ特徴量のエピソード
        matcher = EpisodeMatcher()
        episodes = [_make_episode(task_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0})]

        # Act
        results = matcher.find_similar(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0},
            episodes=episodes,
        )

        # Assert: 類似度1.0
        assert len(results) == 1
        assert results[0].similarity == 1.0

    def test_different_features_lower_similarity(self):
        """異なる特徴量は類似度が下がる"""
        # Arrange
        matcher = EpisodeMatcher()
        episodes = [_make_episode(task_features={"complexity": 1.0, "risk": 1.0, "urgency": 1.0})]

        # Act
        results = matcher.find_similar(
            target_features={"complexity": 5.0, "risk": 5.0, "urgency": 5.0},
            episodes=episodes,
        )

        # Assert: 類似度 < 1.0
        assert len(results) == 1
        assert results[0].similarity < 1.0

    def test_top_k_returns_limited_results(self):
        """top_kで結果数を制限"""
        # Arrange
        matcher = EpisodeMatcher()
        episodes = [
            _make_episode(
                episode_id=f"ep-{i:03d}",
                task_features={"complexity": float(i), "risk": 2.0, "urgency": 3.0},
            )
            for i in range(1, 11)
        ]

        # Act
        results = matcher.find_similar(
            target_features={"complexity": 5.0, "risk": 2.0, "urgency": 3.0},
            episodes=episodes,
            top_k=3,
        )

        # Assert: 最大3件
        assert len(results) == 3

    def test_results_sorted_by_similarity_desc(self):
        """結果は類似度降順でソート"""
        # Arrange
        matcher = EpisodeMatcher()
        episodes = [
            _make_episode(
                episode_id="ep-far",
                task_features={"complexity": 1.0, "risk": 1.0, "urgency": 1.0},
            ),
            _make_episode(
                episode_id="ep-close",
                task_features={"complexity": 3.0, "risk": 3.0, "urgency": 3.0},
            ),
        ]

        # Act
        results = matcher.find_similar(
            target_features={"complexity": 3.0, "risk": 3.0, "urgency": 3.0},
            episodes=episodes,
        )

        # Assert: 類似度が高い順
        assert results[0].episode.episode_id == "ep-close"
        assert results[0].similarity >= results[1].similarity

    def test_min_similarity_threshold(self):
        """最低類似度を下回るエピソードは除外"""
        # Arrange
        matcher = EpisodeMatcher()
        episodes = [
            _make_episode(
                episode_id="ep-far",
                task_features={"complexity": 1.0, "risk": 1.0, "urgency": 1.0},
            ),
            _make_episode(
                episode_id="ep-close",
                task_features={"complexity": 5.0, "risk": 5.0, "urgency": 5.0},
            ),
        ]

        # Act: 高い閾値で検索
        results = matcher.find_similar(
            target_features={"complexity": 5.0, "risk": 5.0, "urgency": 5.0},
            episodes=episodes,
            min_similarity=0.9,
        )

        # Assert: 類似度の低いものは除外
        assert all(r.similarity >= 0.9 for r in results)

    def test_similar_episode_has_episode_and_similarity(self):
        """SimilarEpisodeにepisodeとsimilarityが含まれる"""
        # Arrange
        matcher = EpisodeMatcher()
        episodes = [_make_episode()]

        # Act
        results = matcher.find_similar(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
            episodes=episodes,
        )

        # Assert
        assert isinstance(results[0], SimilarEpisode)
        assert hasattr(results[0], "episode")
        assert hasattr(results[0], "similarity")

    def test_missing_feature_keys_handled(self):
        """特徴量キーが欠けていても動作する"""
        # Arrange: 部分的な特徴量
        matcher = EpisodeMatcher()
        episodes = [
            _make_episode(
                task_features={"complexity": 3.0},
            )
        ]

        # Act: 全キーで検索
        results = matcher.find_similar(
            target_features={"complexity": 3.0, "risk": 3.0, "urgency": 3.0},
            episodes=episodes,
        )

        # Assert: エラーにならない
        assert len(results) == 1


# ==================== M3-8-b: テンプレート成功率分析 ====================

from hiveforge.scout_bee.analyzer import TemplateAnalyzer  # noqa: E402


class TestTemplateAnalyzer:
    """テンプレート成功率分析のテスト"""

    def test_empty_episodes_empty_stats(self):
        """エピソードなしの場合は空のstats"""
        # Arrange
        analyzer = TemplateAnalyzer()

        # Act
        stats = analyzer.analyze([])

        # Assert
        assert stats == {}

    def test_single_template_stats(self):
        """単一テンプレートの統計"""
        # Arrange
        analyzer = TemplateAnalyzer()
        episodes = [
            _make_episode(template_used="balanced", outcome=Outcome.SUCCESS),
            _make_episode(
                episode_id="ep-002",
                template_used="balanced",
                outcome=Outcome.FAILURE,
            ),
        ]

        # Act
        stats = analyzer.analyze(episodes)

        # Assert
        assert "balanced" in stats
        assert stats["balanced"].total_count == 2
        assert stats["balanced"].success_count == 1
        assert stats["balanced"].success_rate == 0.5

    def test_multiple_templates_stats(self):
        """複数テンプレートの統計"""
        # Arrange
        analyzer = TemplateAnalyzer()
        episodes = [
            _make_episode(
                episode_id="ep-s1",
                template_used="speed",
                outcome=Outcome.SUCCESS,
            ),
            _make_episode(
                episode_id="ep-s2",
                template_used="speed",
                outcome=Outcome.SUCCESS,
            ),
            _make_episode(
                episode_id="ep-q1",
                template_used="quality",
                outcome=Outcome.FAILURE,
            ),
        ]

        # Act
        stats = analyzer.analyze(episodes)

        # Assert
        assert stats["speed"].success_rate == 1.0
        assert stats["quality"].success_rate == 0.0

    def test_avg_duration_calculated(self):
        """平均所要時間が計算される"""
        # Arrange
        analyzer = TemplateAnalyzer()
        episodes = [
            _make_episode(
                episode_id="ep-001",
                template_used="balanced",
                duration_seconds=60.0,
            ),
            _make_episode(
                episode_id="ep-002",
                template_used="balanced",
                duration_seconds=120.0,
            ),
        ]

        # Act
        stats = analyzer.analyze(episodes)

        # Assert
        assert stats["balanced"].avg_duration_seconds == 90.0

    def test_best_template_returns_highest_success_rate(self):
        """best_templateは成功率最高のテンプレートを返す"""
        # Arrange
        analyzer = TemplateAnalyzer()
        episodes = [
            _make_episode(
                episode_id="ep-s1",
                template_used="speed",
                outcome=Outcome.SUCCESS,
            ),
            _make_episode(
                episode_id="ep-b1",
                template_used="balanced",
                outcome=Outcome.FAILURE,
            ),
        ]

        # Act
        best = analyzer.best_template(episodes)

        # Assert
        assert best == "speed"

    def test_best_template_empty_returns_none(self):
        """エピソードなしならNone"""
        analyzer = TemplateAnalyzer()
        assert analyzer.best_template([]) is None

    def test_template_stats_model(self):
        """TemplateStatsモデルが正しいフィールドを持つ"""
        stats = TemplateStats(
            template_name="balanced",
            total_count=10,
            success_count=8,
            success_rate=0.8,
            avg_duration_seconds=90.0,
        )

        assert stats.template_name == "balanced"
        assert stats.success_rate == 0.8


# ==================== M3-8-c: Beekeeperへの最適化提案統合 ====================

from hiveforge.scout_bee.scout import ScoutBee  # noqa: E402


class TestScoutBee:
    """Scout Bee 統合テスト"""

    def test_recommend_with_data(self):
        """十分なデータがある場合の推薦"""
        # Arrange: 複数エピソード
        scout = ScoutBee(min_episodes=2)
        episodes = [
            _make_episode(
                episode_id="ep-001",
                template_used="speed",
                outcome=Outcome.SUCCESS,
                task_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0},
                duration_seconds=30.0,
            ),
            _make_episode(
                episode_id="ep-002",
                template_used="speed",
                outcome=Outcome.SUCCESS,
                task_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0},
                duration_seconds=45.0,
            ),
            _make_episode(
                episode_id="ep-003",
                template_used="balanced",
                outcome=Outcome.FAILURE,
                task_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0},
                duration_seconds=120.0,
            ),
        ]

        # Act
        report = scout.recommend(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 4.0},
            episodes=episodes,
        )

        # Assert
        assert isinstance(report, ScoutReport)
        assert report.verdict == ScoutVerdict.RECOMMENDED
        assert report.recommended_template == "speed"

    def test_cold_start_fallback(self):
        """データ不足時のコールドスタートフォールバック"""
        # Arrange: エピソードが少ない
        scout = ScoutBee(min_episodes=5)
        episodes = [
            _make_episode(episode_id="ep-001"),
        ]

        # Act
        report = scout.recommend(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
            episodes=episodes,
        )

        # Assert: フォールバック
        assert report.verdict == ScoutVerdict.COLD_START
        assert report.recommended_template == "balanced"

    def test_no_episodes_cold_start(self):
        """エピソードゼロはコールドスタート"""
        scout = ScoutBee(min_episodes=3)
        report = scout.recommend(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
            episodes=[],
        )

        assert report.verdict == ScoutVerdict.COLD_START
        assert report.recommended_template == "balanced"

    def test_report_contains_proposal(self):
        """レポートに最適化提案が含まれる"""
        # Arrange
        scout = ScoutBee(min_episodes=1)
        episodes = [
            _make_episode(
                episode_id="ep-001",
                template_used="quality",
                outcome=Outcome.SUCCESS,
                task_features={"complexity": 4.0, "risk": 4.0, "urgency": 2.0},
            ),
        ]

        # Act
        report = scout.recommend(
            target_features={"complexity": 4.0, "risk": 4.0, "urgency": 2.0},
            episodes=episodes,
        )

        # Assert
        assert report.proposal is not None
        assert isinstance(report.proposal, OptimizationProposal)
        assert report.proposal.template_name != ""

    def test_report_contains_similar_episodes(self):
        """レポートに類似エピソード情報が含まれる"""
        scout = ScoutBee(min_episodes=1)
        episodes = [_make_episode()]

        report = scout.recommend(
            target_features={"complexity": 3.0, "risk": 2.0, "urgency": 3.0},
            episodes=episodes,
        )

        assert report.similar_count >= 0

    def test_scout_verdict_values(self):
        """ScoutVerdictの値"""
        assert ScoutVerdict.RECOMMENDED is not None
        assert ScoutVerdict.COLD_START is not None
        assert ScoutVerdict.INSUFFICIENT_DATA is not None

    def test_optimization_proposal_model(self):
        """OptimizationProposalモデル"""
        proposal = OptimizationProposal(
            template_name="speed",
            success_rate=0.9,
            avg_duration_seconds=45.0,
            reason="類似タスクで成功率90%",
            similar_episode_count=5,
        )

        assert proposal.template_name == "speed"
        assert proposal.success_rate == 0.9
        assert proposal.reason != ""

    def test_recommend_uses_similar_episodes(self):
        """推薦は類似エピソードに基づく"""
        # Arrange: 異なる特徴量のエピソード
        scout = ScoutBee(min_episodes=1)
        episodes = [
            # 類似: complexity=4, risk=4
            _make_episode(
                episode_id="ep-similar",
                template_used="quality",
                outcome=Outcome.SUCCESS,
                task_features={"complexity": 4.0, "risk": 4.0, "urgency": 2.0},
            ),
            # 非類似: complexity=1, risk=1
            _make_episode(
                episode_id="ep-different",
                template_used="speed",
                outcome=Outcome.SUCCESS,
                task_features={"complexity": 1.0, "risk": 1.0, "urgency": 5.0},
            ),
        ]

        # Act
        report = scout.recommend(
            target_features={"complexity": 4.0, "risk": 4.0, "urgency": 2.0},
            episodes=episodes,
        )

        # Assert: 類似エピソードのテンプレートが推薦される
        assert report.recommended_template == "quality"
