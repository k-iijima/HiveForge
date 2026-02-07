"""Referee Bee（審判蜂 / 自動採点・生存選抜）のテスト

N案候補を多面的に自動採点し、上位候補のみをGuard Beeに渡す。
5指標: Correctness / Robustness / Consistency / Security / Latency
"""

import pytest

from hiveforge.referee_bee.models import (
    CandidateScore,
    DiffResult,
    RefereeReport,
    RefereeVerdict,
    ScoreWeights,
    ScoringDimension,
    SelectionResult,
)

# ==================== M3-5-a: スコアリングモデル ====================


class TestScoringDimension:
    """スコア指標の型テスト"""

    def test_all_dimensions_exist(self):
        """5次元スコア指標が定義されている"""
        assert ScoringDimension.CORRECTNESS is not None
        assert ScoringDimension.ROBUSTNESS is not None
        assert ScoringDimension.CONSISTENCY is not None
        assert ScoringDimension.SECURITY is not None
        assert ScoringDimension.LATENCY is not None


class TestScoreWeights:
    """スコア重み付けのテスト"""

    def test_default_weights(self):
        """デフォルト重み: コンセプトv6通り"""
        weights = ScoreWeights()

        # Arrange/Assert: 0.40/0.20/0.20/0.10/0.10
        assert weights.correctness == 0.40
        assert weights.robustness == 0.20
        assert weights.consistency == 0.20
        assert weights.security == 0.10
        assert weights.latency == 0.10

    def test_weights_sum_to_one(self):
        """重み合計が1.0"""
        weights = ScoreWeights()
        total = (
            weights.correctness
            + weights.robustness
            + weights.consistency
            + weights.security
            + weights.latency
        )
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights(self):
        """カスタム重み設定"""
        weights = ScoreWeights(
            correctness=0.50,
            robustness=0.20,
            consistency=0.10,
            security=0.10,
            latency=0.10,
        )
        assert weights.correctness == 0.50


class TestCandidateScore:
    """候補スコアのテスト"""

    def test_create_candidate_score(self):
        """候補スコアを作成"""
        score = CandidateScore(
            candidate_id="candidate-001",
            correctness=0.95,
            robustness=0.80,
            consistency=0.90,
            security=1.0,
            latency=0.85,
        )

        assert score.candidate_id == "candidate-001"
        assert score.correctness == 0.95

    def test_final_score_default_weights(self):
        """デフォルト重みでの最終スコア計算

        FinalScore = 0.40×Correctness + 0.20×Robustness
                   + 0.20×Consistency + 0.10×Security + 0.10×Latency
        """
        # Arrange
        score = CandidateScore(
            candidate_id="c1",
            correctness=1.0,
            robustness=1.0,
            consistency=1.0,
            security=1.0,
            latency=1.0,
        )

        # Act
        final = score.final_score()

        # Assert: 全1.0なら最終スコアも1.0
        assert abs(final - 1.0) < 1e-9

    def test_final_score_partial(self):
        """部分スコアでの最終スコア計算"""
        score = CandidateScore(
            candidate_id="c1",
            correctness=0.5,
            robustness=0.5,
            consistency=0.5,
            security=0.5,
            latency=0.5,
        )

        final = score.final_score()
        assert abs(final - 0.5) < 1e-9

    def test_final_score_with_custom_weights(self):
        """カスタム重みでの最終スコア計算"""
        score = CandidateScore(
            candidate_id="c1",
            correctness=1.0,
            robustness=0.0,
            consistency=0.0,
            security=0.0,
            latency=0.0,
        )

        weights = ScoreWeights(
            correctness=1.0,
            robustness=0.0,
            consistency=0.0,
            security=0.0,
            latency=0.0,
        )

        final = score.final_score(weights)
        assert abs(final - 1.0) < 1e-9

    def test_score_clamped_0_1(self):
        """スコアは0〜1に収まる"""
        score = CandidateScore(
            candidate_id="c1",
            correctness=0.0,
            robustness=0.0,
            consistency=0.0,
            security=0.0,
            latency=0.0,
        )
        assert score.final_score() == 0.0


# ==================== M3-5-b: Differential Testing ====================


class TestDiffResult:
    """差分実行結果のテスト"""

    def test_create_diff_result_match(self):
        """出力一致"""
        result = DiffResult(
            candidate_a="c1",
            candidate_b="c2",
            input_description="テストケースA",
            outputs_match=True,
        )

        assert result.outputs_match is True
        assert result.diff_details == {}

    def test_create_diff_result_mismatch(self):
        """出力不一致"""
        result = DiffResult(
            candidate_a="c1",
            candidate_b="c2",
            input_description="テストケースB",
            outputs_match=False,
            diff_details={
                "expected": "200 OK",
                "actual": "500 Error",
            },
        )

        assert result.outputs_match is False
        assert result.diff_details["expected"] == "200 OK"


from hiveforge.referee_bee.diff_tester import DiffTester  # noqa: E402


class TestDiffTester:
    """Differential Testingのテスト"""

    def test_compare_identical_outputs(self):
        """同一出力の場合、一致と判定"""
        tester = DiffTester()

        candidates = {
            "c1": {"output": "hello"},
            "c2": {"output": "hello"},
        }

        results = tester.compare(candidates, input_description="test input")

        assert len(results) == 1
        assert results[0].outputs_match is True

    def test_compare_different_outputs(self):
        """異なる出力の場合、不一致と判定"""
        tester = DiffTester()

        candidates = {
            "c1": {"output": "hello"},
            "c2": {"output": "world"},
        }

        results = tester.compare(candidates, input_description="test input")

        assert len(results) == 1
        assert results[0].outputs_match is False

    def test_compare_three_candidates(self):
        """3候補の場合、ペアワイズ比較"""
        tester = DiffTester()

        candidates = {
            "c1": {"output": "a"},
            "c2": {"output": "a"},
            "c3": {"output": "b"},
        }

        results = tester.compare(candidates, input_description="test")

        # 3C2 = 3ペア
        assert len(results) == 3

    def test_compare_single_candidate(self):
        """1候補ならペアなし"""
        tester = DiffTester()
        results = tester.compare({"c1": {"output": "x"}}, input_description="test")
        assert len(results) == 0

    def test_consistency_ratio(self):
        """一致率を計算"""
        tester = DiffTester()
        results = [
            DiffResult(
                candidate_a="c1", candidate_b="c2", input_description="t", outputs_match=True
            ),
            DiffResult(
                candidate_a="c1", candidate_b="c3", input_description="t", outputs_match=False
            ),
            DiffResult(
                candidate_a="c2", candidate_b="c3", input_description="t", outputs_match=False
            ),
        ]

        ratio = tester.consistency_ratio(results)
        assert abs(ratio - 1.0 / 3.0) < 1e-9

    def test_consistency_ratio_empty(self):
        """結果が空の場合は1.0（問題なし扱い）"""
        tester = DiffTester()
        assert tester.consistency_ratio([]) == 1.0


# ==================== M3-5-c: トーナメント選抜 ====================


from hiveforge.referee_bee.tournament import Tournament  # noqa: E402


class TestSelectionResult:
    """選抜結果モデルのテスト"""

    def test_create_selection_result(self):
        """選抜結果を作成"""
        result = SelectionResult(
            selected_ids=["c1"],
            rankings=[
                CandidateScore(
                    candidate_id="c1",
                    correctness=1.0,
                    robustness=0.9,
                    consistency=0.8,
                    security=1.0,
                    latency=0.7,
                ),
            ],
            reason="Highest final score",
        )

        assert result.selected_ids == ["c1"]
        assert len(result.rankings) == 1


class TestTournament:
    """トーナメント選抜のテスト"""

    def test_select_top_k(self):
        """上位K件を選抜"""
        # Arrange
        tournament = Tournament(k=1)
        scores = [
            CandidateScore(
                candidate_id="c1",
                correctness=0.5,
                robustness=0.5,
                consistency=0.5,
                security=0.5,
                latency=0.5,
            ),
            CandidateScore(
                candidate_id="c2",
                correctness=1.0,
                robustness=1.0,
                consistency=1.0,
                security=1.0,
                latency=1.0,
            ),
        ]

        # Act
        result = tournament.select(scores)

        # Assert: c2が最高スコア
        assert result.selected_ids == ["c2"]

    def test_select_top_2(self):
        """上位2件選抜"""
        tournament = Tournament(k=2)
        scores = [
            CandidateScore(
                candidate_id="c1",
                correctness=0.3,
                robustness=0.3,
                consistency=0.3,
                security=0.3,
                latency=0.3,
            ),
            CandidateScore(
                candidate_id="c2",
                correctness=1.0,
                robustness=1.0,
                consistency=1.0,
                security=1.0,
                latency=1.0,
            ),
            CandidateScore(
                candidate_id="c3",
                correctness=0.8,
                robustness=0.8,
                consistency=0.8,
                security=0.8,
                latency=0.8,
            ),
        ]

        result = tournament.select(scores)

        assert len(result.selected_ids) == 2
        assert "c2" in result.selected_ids
        assert "c3" in result.selected_ids

    def test_select_with_single_candidate(self):
        """単一候補はスキップ（そのまま選抜）"""
        tournament = Tournament(k=1)
        scores = [
            CandidateScore(
                candidate_id="c1",
                correctness=0.5,
                robustness=0.5,
                consistency=0.5,
                security=0.5,
                latency=0.5,
            ),
        ]

        result = tournament.select(scores)

        assert result.selected_ids == ["c1"]
        assert "single" in result.reason.lower() or "skip" in result.reason.lower()

    def test_select_empty(self):
        """候補なしでは空選抜"""
        tournament = Tournament(k=1)
        result = tournament.select([])

        assert result.selected_ids == []

    def test_rankings_sorted_by_score(self):
        """ランキングはスコア降順"""
        tournament = Tournament(k=3)
        scores = [
            CandidateScore(
                candidate_id="low",
                correctness=0.1,
                robustness=0.1,
                consistency=0.1,
                security=0.1,
                latency=0.1,
            ),
            CandidateScore(
                candidate_id="high",
                correctness=1.0,
                robustness=1.0,
                consistency=1.0,
                security=1.0,
                latency=1.0,
            ),
            CandidateScore(
                candidate_id="mid",
                correctness=0.5,
                robustness=0.5,
                consistency=0.5,
                security=0.5,
                latency=0.5,
            ),
        ]

        result = tournament.select(scores)

        assert result.rankings[0].candidate_id == "high"
        assert result.rankings[1].candidate_id == "mid"
        assert result.rankings[2].candidate_id == "low"


# ==================== M3-5-d: RefereeReport ====================


class TestRefereeVerdict:
    """Referee判定のテスト"""

    def test_verdicts(self):
        """3つの判定"""
        assert RefereeVerdict.SELECTED is not None
        assert RefereeVerdict.NO_CANDIDATE is not None
        assert RefereeVerdict.SINGLE_PASS is not None


class TestRefereeReport:
    """RefereeReportのテスト"""

    def test_create_report(self):
        """レポート作成"""
        report = RefereeReport(
            run_id="run-001",
            colony_id="colony-001",
            candidate_count=3,
            selected_ids=["c2"],
            scores=[
                CandidateScore(
                    candidate_id="c2",
                    correctness=1.0,
                    robustness=0.9,
                    consistency=0.8,
                    security=1.0,
                    latency=0.7,
                ),
            ],
            verdict=RefereeVerdict.SELECTED,
        )

        assert report.run_id == "run-001"
        assert report.candidate_count == 3
        assert report.selected_ids == ["c2"]

    def test_single_pass_report(self):
        """単一候補パスのレポート"""
        report = RefereeReport(
            run_id="run-001",
            colony_id="colony-001",
            candidate_count=1,
            selected_ids=["c1"],
            scores=[
                CandidateScore(
                    candidate_id="c1",
                    correctness=0.8,
                    robustness=0.8,
                    consistency=0.8,
                    security=0.8,
                    latency=0.8,
                ),
            ],
            verdict=RefereeVerdict.SINGLE_PASS,
        )

        assert report.verdict == RefereeVerdict.SINGLE_PASS

    def test_report_summary(self):
        """レポートサマリー"""
        report = RefereeReport(
            run_id="run-001",
            colony_id="colony-001",
            candidate_count=3,
            selected_ids=["c2"],
            scores=[
                CandidateScore(
                    candidate_id="c1",
                    correctness=0.3,
                    robustness=0.3,
                    consistency=0.3,
                    security=0.3,
                    latency=0.3,
                ),
                CandidateScore(
                    candidate_id="c2",
                    correctness=1.0,
                    robustness=1.0,
                    consistency=1.0,
                    security=1.0,
                    latency=1.0,
                ),
                CandidateScore(
                    candidate_id="c3",
                    correctness=0.5,
                    robustness=0.5,
                    consistency=0.5,
                    security=0.5,
                    latency=0.5,
                ),
            ],
            verdict=RefereeVerdict.SELECTED,
        )

        summary = report.summary()
        assert summary["candidate_count"] == 3
        assert summary["selected_count"] == 1
        assert summary["verdict"] == "selected"

    def test_no_candidate_report(self):
        """候補なしレポート"""
        report = RefereeReport(
            run_id="run-001",
            colony_id="colony-001",
            candidate_count=0,
            selected_ids=[],
            scores=[],
            verdict=RefereeVerdict.NO_CANDIDATE,
        )

        assert report.verdict == RefereeVerdict.NO_CANDIDATE


# ==================== M3-5-e: Guard Bee連携 ====================


from hiveforge.referee_bee.reporter import RefereeReporter  # noqa: E402


class TestRefereeReporter:
    """RefereeReporter（Guard Bee連携）のテスト"""

    def test_create_report(self):
        """スコアからRefereeReportを生成"""
        reporter = RefereeReporter()

        scores = [
            CandidateScore(
                candidate_id="c1",
                correctness=0.3,
                robustness=0.3,
                consistency=0.3,
                security=0.3,
                latency=0.3,
            ),
            CandidateScore(
                candidate_id="c2",
                correctness=1.0,
                robustness=1.0,
                consistency=1.0,
                security=1.0,
                latency=1.0,
            ),
        ]

        report = reporter.create_report(
            run_id="run-001",
            colony_id="colony-001",
            scores=scores,
            k=1,
        )

        assert isinstance(report, RefereeReport)
        assert report.selected_ids == ["c2"]
        assert report.verdict == RefereeVerdict.SELECTED

    def test_single_candidate_verdict(self):
        """単一候補はSINGLE_PASS"""
        reporter = RefereeReporter()

        scores = [
            CandidateScore(
                candidate_id="c1",
                correctness=0.8,
                robustness=0.8,
                consistency=0.8,
                security=0.8,
                latency=0.8,
            ),
        ]

        report = reporter.create_report(
            run_id="run-001",
            colony_id="colony-001",
            scores=scores,
        )

        assert report.verdict == RefereeVerdict.SINGLE_PASS

    def test_empty_candidates_verdict(self):
        """候補なしはNO_CANDIDATE"""
        reporter = RefereeReporter()

        report = reporter.create_report(
            run_id="run-001",
            colony_id="colony-001",
            scores=[],
        )

        assert report.verdict == RefereeVerdict.NO_CANDIDATE

    def test_to_guard_bee_evidence(self):
        """Guard Bee用Evidence形式に変換"""
        reporter = RefereeReporter()
        report = RefereeReport(
            run_id="run-001",
            colony_id="colony-001",
            candidate_count=2,
            selected_ids=["c2"],
            scores=[
                CandidateScore(
                    candidate_id="c1",
                    correctness=0.3,
                    robustness=0.3,
                    consistency=0.3,
                    security=0.3,
                    latency=0.3,
                ),
                CandidateScore(
                    candidate_id="c2",
                    correctness=1.0,
                    robustness=1.0,
                    consistency=1.0,
                    security=1.0,
                    latency=1.0,
                ),
            ],
            verdict=RefereeVerdict.SELECTED,
        )

        evidence = reporter.to_guard_bee_evidence(report)

        assert evidence["evidence_type"] == "referee_report"
        assert evidence["verdict"] == "selected"
        assert evidence["candidate_count"] == 2
        assert evidence["selected_ids"] == ["c2"]
        assert "top_score" in evidence


# ==================== M3-5-a: スコアリングエンジン ====================


from hiveforge.referee_bee.scoring import ScoringEngine  # noqa: E402


class TestScoringEngine:
    """スコアリングエンジンのテスト"""

    def test_score_from_metrics(self):
        """メトリクスからCandidateScoreを計算"""
        engine = ScoringEngine()

        metrics = {
            "tests_passed": 10,
            "tests_total": 10,
            "mutation_survived": 0,
            "mutation_total": 5,
            "diff_match_ratio": 1.0,
            "lint_violations": 0,
            "latency_ratio": 1.0,
        }

        score = engine.compute("c1", metrics)

        assert score.candidate_id == "c1"
        assert score.correctness == 1.0  # 10/10
        assert score.robustness == 1.0  # 0 survived / 5 total
        assert score.consistency == 1.0  # 1.0
        assert score.security == 1.0  # 0 violations
        assert score.latency == 1.0  # 1.0

    def test_score_partial_metrics(self):
        """部分的メトリクスでスコア計算"""
        engine = ScoringEngine()

        metrics = {
            "tests_passed": 5,
            "tests_total": 10,
            "mutation_survived": 3,
            "mutation_total": 5,
            "diff_match_ratio": 0.5,
            "lint_violations": 2,
            "latency_ratio": 0.8,
        }

        score = engine.compute("c1", metrics)

        assert score.correctness == 0.5  # 5/10
        assert score.robustness == pytest.approx(0.4)  # 1 - 3/5
        assert score.consistency == 0.5

    def test_score_missing_metrics_defaults(self):
        """メトリクス欠落時のデフォルト値"""
        engine = ScoringEngine()

        score = engine.compute("c1", {})

        # 欠落時はデフォルト0.0
        assert score.correctness == 0.0
        assert score.robustness == 0.0
        assert score.consistency == 0.0
        assert score.security == 0.0
        assert score.latency == 0.0
