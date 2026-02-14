"""Requirement Analysis Colony — Phase 2 モデルのテスト.

§5.3 EvidencePack / WebEvidencePack, §5.7 SpecScore / RefereeResult,
§11.3 ChangeReason / RequirementChangedPayload / ImpactReport のテスト。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from colonyforge.requirement_analysis.models import (
    ChangeReason,
    CodeRef,
    DecisionRef,
    EpisodeRef,
    EvidencePack,
    FailureRef,
    Freshness,
    ImpactReport,
    RefereeResult,
    RequirementChangedPayload,
    RunRef,
    SpecScore,
    WebEvidencePack,
    WebFinding,
    WebSourceType,
)

# ===========================================================================
# §5.3 DecisionRef
# ===========================================================================


class TestDecisionRef:
    """DecisionRef — 過去の意思決定への参照."""

    def test_create_valid(self) -> None:
        """有効な DecisionRef を作成できる."""
        # Arrange & Act
        ref = DecisionRef(
            decision_id="dec-001",
            summary="認証方式をJWTに決定",
            relevance_score=0.85,
        )

        # Assert
        assert ref.decision_id == "dec-001"
        assert ref.summary == "認証方式をJWTに決定"
        assert ref.relevance_score == 0.85
        assert ref.superseded is False

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        # Arrange
        ref = DecisionRef(
            decision_id="dec-001",
            summary="test",
            relevance_score=0.5,
        )

        # Act & Assert
        with pytest.raises(ValidationError):
            ref.decision_id = "dec-002"  # type: ignore[misc]

    def test_relevance_score_boundary_zero(self) -> None:
        """relevance_score=0.0 は許容される."""
        ref = DecisionRef(decision_id="d", summary="s", relevance_score=0.0)
        assert ref.relevance_score == 0.0

    def test_relevance_score_boundary_one(self) -> None:
        """relevance_score=1.0 は許容される."""
        ref = DecisionRef(decision_id="d", summary="s", relevance_score=1.0)
        assert ref.relevance_score == 1.0

    def test_relevance_score_over_one_rejected(self) -> None:
        """relevance_score > 1.0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            DecisionRef(decision_id="d", summary="s", relevance_score=1.1)

    def test_relevance_score_negative_rejected(self) -> None:
        """relevance_score < 0.0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            DecisionRef(decision_id="d", summary="s", relevance_score=-0.1)

    def test_superseded_true(self) -> None:
        """superseded=True を指定できる."""
        ref = DecisionRef(decision_id="d", summary="s", relevance_score=0.5, superseded=True)
        assert ref.superseded is True


# ===========================================================================
# §5.3 RunRef
# ===========================================================================


class TestRunRef:
    """RunRef — 過去の Run 実行結果への参照."""

    def test_create_valid(self) -> None:
        """有効な RunRef を作成できる."""
        ref = RunRef(
            run_id="run-001",
            goal="ログイン実装",
            outcome="SUCCESS",
            relevance_score=0.9,
        )
        assert ref.run_id == "run-001"
        assert ref.outcome == "SUCCESS"

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        ref = RunRef(run_id="r", goal="g", outcome="SUCCESS", relevance_score=0.5)
        with pytest.raises(ValidationError):
            ref.run_id = "changed"  # type: ignore[misc]

    def test_relevance_score_boundary(self) -> None:
        """0.0 と 1.0 の境界値."""
        ref_zero = RunRef(run_id="r", goal="g", outcome="FAILURE", relevance_score=0.0)
        ref_one = RunRef(run_id="r", goal="g", outcome="PARTIAL", relevance_score=1.0)
        assert ref_zero.relevance_score == 0.0
        assert ref_one.relevance_score == 1.0


# ===========================================================================
# §5.3 FailureRef
# ===========================================================================


class TestFailureRef:
    """FailureRef — 過去の失敗への参照."""

    def test_create_valid(self) -> None:
        """有効な FailureRef を作成できる."""
        ref = FailureRef(
            run_id="run-001",
            failure_class="TimeoutError",
            summary="API呼び出しタイムアウト",
            relevance_score=0.7,
        )
        assert ref.failure_class == "TimeoutError"
        assert ref.relevance_score == 0.7

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        ref = FailureRef(run_id="r", failure_class="E", summary="s", relevance_score=0.5)
        with pytest.raises(ValidationError):
            ref.run_id = "changed"  # type: ignore[misc]


# ===========================================================================
# §5.3 CodeRef
# ===========================================================================


class TestCodeRef:
    """CodeRef — 関連コードファイルへの参照."""

    def test_create_valid(self) -> None:
        """有効な CodeRef を作成できる."""
        ref = CodeRef(
            file_path="src/auth/handler.py",
            summary="認証ハンドラ",
            relevance_score=0.6,
        )
        assert ref.file_path == "src/auth/handler.py"

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        ref = CodeRef(file_path="f", summary="s", relevance_score=0.5)
        with pytest.raises(ValidationError):
            ref.file_path = "changed"  # type: ignore[misc]


# ===========================================================================
# §5.3 EpisodeRef
# ===========================================================================


class TestEpisodeRef:
    """EpisodeRef — 過去の Honeycomb エピソードへの参照."""

    def test_create_valid(self) -> None:
        """有効な EpisodeRef を作成できる."""
        ref = EpisodeRef(
            episode_id="ep-001",
            goal="認証機能実装",
            template_used="web-api",
            outcome="SUCCESS",
            similarity=0.92,
        )
        assert ref.episode_id == "ep-001"
        assert ref.similarity == 0.92

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        ref = EpisodeRef(
            episode_id="e",
            goal="g",
            template_used="t",
            outcome="o",
            similarity=0.5,
        )
        with pytest.raises(ValidationError):
            ref.episode_id = "changed"  # type: ignore[misc]

    def test_similarity_boundary(self) -> None:
        """similarity の境界値 0.0 / 1.0."""
        ref0 = EpisodeRef(
            episode_id="e",
            goal="g",
            template_used="t",
            outcome="o",
            similarity=0.0,
        )
        ref1 = EpisodeRef(
            episode_id="e",
            goal="g",
            template_used="t",
            outcome="o",
            similarity=1.0,
        )
        assert ref0.similarity == 0.0
        assert ref1.similarity == 1.0


# ===========================================================================
# §5.3 EvidencePack
# ===========================================================================


class TestEvidencePack:
    """EvidencePack — Context Forager の出力."""

    def test_create_with_defaults(self) -> None:
        """デフォルト値で空の EvidencePack を作成できる."""
        # Arrange & Act
        pack = EvidencePack()

        # Assert
        assert pack.related_decisions == []
        assert pack.past_runs == []
        assert pack.failure_history == []
        assert pack.code_context == []
        assert pack.similar_episodes == []

    def test_create_with_all_refs(self) -> None:
        """全サブモデルを含む EvidencePack を作成できる."""
        # Arrange
        dec = DecisionRef(decision_id="d1", summary="s", relevance_score=0.5)
        run = RunRef(run_id="r1", goal="g", outcome="SUCCESS", relevance_score=0.5)
        fail = FailureRef(run_id="r2", failure_class="E", summary="s", relevance_score=0.5)
        code = CodeRef(file_path="f.py", summary="s", relevance_score=0.5)
        ep = EpisodeRef(
            episode_id="e1",
            goal="g",
            template_used="t",
            outcome="SUCCESS",
            similarity=0.5,
        )

        # Act
        pack = EvidencePack(
            related_decisions=[dec],
            past_runs=[run],
            failure_history=[fail],
            code_context=[code],
            similar_episodes=[ep],
        )

        # Assert
        assert len(pack.related_decisions) == 1
        assert len(pack.past_runs) == 1
        assert len(pack.failure_history) == 1
        assert len(pack.code_context) == 1
        assert len(pack.similar_episodes) == 1

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        pack = EvidencePack()
        with pytest.raises(ValidationError):
            pack.past_runs = []  # type: ignore[misc]


# ===========================================================================
# §5.3 WebSourceType / Freshness
# ===========================================================================


class TestWebSourceType:
    """WebSourceType enum の全メンバーを検証."""

    def test_all_members(self) -> None:
        """6つのソースタイプが定義されている."""
        assert len(WebSourceType) == 6
        assert WebSourceType.OFFICIAL_DOCS == "official_docs"
        assert WebSourceType.SECURITY_ADVISORY == "security_advisory"
        assert WebSourceType.BLOG_ARTICLE == "blog_article"
        assert WebSourceType.STACK_OVERFLOW == "stack_overflow"
        assert WebSourceType.CHANGELOG == "changelog"
        assert WebSourceType.OTHER == "other"


class TestFreshness:
    """Freshness enum の全メンバーを検証."""

    def test_all_members(self) -> None:
        """3つの鮮度ランクが定義されている."""
        assert len(Freshness) == 3
        assert Freshness.CURRENT == "current"
        assert Freshness.OUTDATED == "outdated"
        assert Freshness.UNKNOWN == "unknown"


# ===========================================================================
# §5.3 WebFinding
# ===========================================================================


class TestWebFinding:
    """WebFinding — WEB検索結果の1件."""

    def test_create_valid(self) -> None:
        """有効な WebFinding を作成できる."""
        finding = WebFinding(
            url="https://example.com/docs",
            title="認証ガイド",
            summary="OAuthの実装手順",
            search_query="OAuth implementation guide",
            relevance_score=0.8,
        )
        assert finding.url == "https://example.com/docs"
        assert finding.freshness == Freshness.UNKNOWN
        assert finding.source_type == WebSourceType.OTHER

    def test_summary_max_length(self) -> None:
        """summary は 500文字以下."""
        with pytest.raises(ValidationError):
            WebFinding(
                url="https://example.com",
                title="t",
                summary="x" * 501,
                search_query="q",
                relevance_score=0.5,
            )

    def test_summary_max_length_boundary(self) -> None:
        """summary = 500文字は許容される."""
        finding = WebFinding(
            url="https://example.com",
            title="t",
            summary="x" * 500,
            search_query="q",
            relevance_score=0.5,
        )
        assert len(finding.summary) == 500

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        finding = WebFinding(
            url="u",
            title="t",
            summary="s",
            search_query="q",
            relevance_score=0.5,
        )
        with pytest.raises(ValidationError):
            finding.url = "changed"  # type: ignore[misc]

    def test_relevance_score_out_of_range(self) -> None:
        """relevance_score > 1.0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            WebFinding(
                url="u",
                title="t",
                summary="s",
                search_query="q",
                relevance_score=1.5,
            )


# ===========================================================================
# §5.3 WebEvidencePack
# ===========================================================================


class TestWebEvidencePack:
    """WebEvidencePack — Web Researcher の出力."""

    def test_create_valid(self) -> None:
        """有効な WebEvidencePack を作成できる."""
        pack = WebEvidencePack(trigger_reason="ambiguity >= 0.7")
        assert pack.search_queries == []
        assert pack.findings == []
        assert pack.search_cost_seconds == 0.0
        assert pack.skipped is False

    def test_trigger_reason_required(self) -> None:
        """trigger_reason は必須."""
        with pytest.raises(ValidationError):
            WebEvidencePack()  # type: ignore[call-arg]

    def test_findings_max_length(self) -> None:
        """findings は最大5件."""
        findings = [
            WebFinding(
                url=f"https://example.com/{i}",
                title="t",
                summary="s",
                search_query="q",
                relevance_score=0.5,
            )
            for i in range(6)
        ]
        with pytest.raises(ValidationError):
            WebEvidencePack(trigger_reason="test", findings=findings)

    def test_findings_max_length_boundary(self) -> None:
        """findings = 5件は許容される."""
        findings = [
            WebFinding(
                url=f"https://example.com/{i}",
                title="t",
                summary="s",
                search_query="q",
                relevance_score=0.5,
            )
            for i in range(5)
        ]
        pack = WebEvidencePack(trigger_reason="test", findings=findings)
        assert len(pack.findings) == 5

    def test_search_cost_negative_rejected(self) -> None:
        """search_cost_seconds < 0.0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            WebEvidencePack(trigger_reason="test", search_cost_seconds=-1.0)

    def test_skipped_pack(self) -> None:
        """skipped=True の WebEvidencePack を作成できる."""
        pack = WebEvidencePack(trigger_reason="low ambiguity", skipped=True)
        assert pack.skipped is True

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        pack = WebEvidencePack(trigger_reason="test")
        with pytest.raises(ValidationError):
            pack.skipped = True  # type: ignore[misc]


# ===========================================================================
# §5.7 SpecScore / RefereeResult
# ===========================================================================


class TestSpecScore:
    """SpecScore — 草案のスコアリング."""

    def test_create_valid(self) -> None:
        """有効な SpecScore を作成できる."""
        score = SpecScore(
            draft_id="draft-001",
            testability=0.8,
            risk_coverage=0.7,
            clarity=0.9,
            completeness=0.6,
            total=0.75,
        )
        assert score.draft_id == "draft-001"
        assert score.total == 0.75

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        score = SpecScore(
            draft_id="d",
            testability=0.5,
            risk_coverage=0.5,
            clarity=0.5,
            completeness=0.5,
            total=0.5,
        )
        with pytest.raises(ValidationError):
            score.total = 1.0  # type: ignore[misc]

    def test_score_boundary_zero(self) -> None:
        """全スコア=0.0 は許容される."""
        score = SpecScore(
            draft_id="d",
            testability=0.0,
            risk_coverage=0.0,
            clarity=0.0,
            completeness=0.0,
            total=0.0,
        )
        assert score.testability == 0.0

    def test_score_boundary_one(self) -> None:
        """全スコア=1.0 は許容される."""
        score = SpecScore(
            draft_id="d",
            testability=1.0,
            risk_coverage=1.0,
            clarity=1.0,
            completeness=1.0,
            total=1.0,
        )
        assert score.total == 1.0

    def test_score_over_one_rejected(self) -> None:
        """total > 1.0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            SpecScore(
                draft_id="d",
                testability=0.5,
                risk_coverage=0.5,
                clarity=0.5,
                completeness=0.5,
                total=1.1,
            )


class TestRefereeResult:
    """RefereeResult — Referee Bee の比較結果."""

    def test_create_valid(self) -> None:
        """有効な RefereeResult を作成できる."""
        s1 = SpecScore(
            draft_id="d1",
            testability=0.8,
            risk_coverage=0.7,
            clarity=0.9,
            completeness=0.6,
            total=0.75,
        )
        s2 = SpecScore(
            draft_id="d2",
            testability=0.6,
            risk_coverage=0.8,
            clarity=0.7,
            completeness=0.7,
            total=0.70,
        )
        result = RefereeResult(selected_draft_id="d1", scores=[s1, s2])
        assert result.selected_draft_id == "d1"
        assert len(result.scores) == 2

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        score = SpecScore(
            draft_id="d",
            testability=0.5,
            risk_coverage=0.5,
            clarity=0.5,
            completeness=0.5,
            total=0.5,
        )
        result = RefereeResult(selected_draft_id="d", scores=[score])
        with pytest.raises(ValidationError):
            result.selected_draft_id = "other"  # type: ignore[misc]


# ===========================================================================
# §11.3 ChangeReason
# ===========================================================================


class TestChangeReason:
    """ChangeReason enum — 要件変更の理由分類."""

    def test_all_members(self) -> None:
        """6つの変更理由が定義されている."""
        assert len(ChangeReason) == 6
        assert ChangeReason.USER_EDIT == "user_edit"
        assert ChangeReason.CLARIFICATION == "clarification"
        assert ChangeReason.CHALLENGE_RESOLUTION == "challenge_resolution"
        assert ChangeReason.REFEREE_SELECTION == "referee_selection"
        assert ChangeReason.DEPENDENCY_UPDATE == "dependency_update"
        assert ChangeReason.FEEDBACK_LOOP == "feedback_loop"


# ===========================================================================
# §11.3 RequirementChangedPayload
# ===========================================================================


class TestRequirementChangedPayload:
    """RequirementChangedPayload — RA_REQ_CHANGED イベントのペイロード."""

    def test_create_valid(self) -> None:
        """有効な RequirementChangedPayload を作成できる."""
        payload = RequirementChangedPayload(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.USER_EDIT,
            diff_summary="タイトル変更",
        )
        assert payload.doorstop_id == "REQ001"
        assert payload.prev_version == 1
        assert payload.new_version == 2
        assert payload.reason == ChangeReason.USER_EDIT
        assert payload.cause_event_id is None
        assert payload.diff_lines == []
        assert payload.affected_links == []

    def test_prev_version_min(self) -> None:
        """prev_version >= 1 が必要."""
        with pytest.raises(ValidationError):
            RequirementChangedPayload(
                doorstop_id="REQ001",
                prev_version=0,
                new_version=2,
                reason=ChangeReason.USER_EDIT,
                diff_summary="s",
            )

    def test_new_version_min(self) -> None:
        """new_version >= 2 が必要."""
        with pytest.raises(ValidationError):
            RequirementChangedPayload(
                doorstop_id="REQ001",
                prev_version=1,
                new_version=1,
                reason=ChangeReason.USER_EDIT,
                diff_summary="s",
            )

    def test_with_cause_event_and_affected_links(self) -> None:
        """因果リンクと影響先要件を指定できる."""
        payload = RequirementChangedPayload(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.DEPENDENCY_UPDATE,
            cause_event_id="evt-123",
            diff_summary="依存先変更",
            diff_lines=["-old line", "+new line"],
            affected_links=["REQ002", "REQ003"],
        )
        assert payload.cause_event_id == "evt-123"
        assert len(payload.affected_links) == 2

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        payload = RequirementChangedPayload(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.USER_EDIT,
            diff_summary="s",
        )
        with pytest.raises(ValidationError):
            payload.doorstop_id = "REQ002"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "reason",
        list(ChangeReason),
        ids=[r.value for r in ChangeReason],
    )
    def test_all_reasons_accepted(self, reason: ChangeReason) -> None:
        """全ての ChangeReason が受け入れられる."""
        payload = RequirementChangedPayload(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=reason,
            diff_summary="test",
        )
        assert payload.reason == reason


# ===========================================================================
# §11.3 ImpactReport
# ===========================================================================


class TestImpactReport:
    """ImpactReport — ImpactAnalyzer の出力."""

    def test_create_valid(self) -> None:
        """有効な ImpactReport を作成できる."""
        report = ImpactReport(
            changed_id="REQ001",
            affected_ids=["REQ002"],
            requires_re_review=["REQ002"],
            cascade_depth=1,
        )
        assert report.changed_id == "REQ001"
        assert report.cascade_depth == 1

    def test_defaults(self) -> None:
        """デフォルト値で作成できる."""
        report = ImpactReport(changed_id="REQ001", cascade_depth=0)
        assert report.affected_ids == []
        assert report.requires_re_review == []

    def test_cascade_depth_zero(self) -> None:
        """cascade_depth=0 は許容される（影響なし）."""
        report = ImpactReport(changed_id="REQ001", cascade_depth=0)
        assert report.cascade_depth == 0

    def test_cascade_depth_negative_rejected(self) -> None:
        """cascade_depth < 0 はバリデーションエラー."""
        with pytest.raises(ValidationError):
            ImpactReport(changed_id="REQ001", cascade_depth=-1)

    def test_frozen(self) -> None:
        """frozen=True で変更不可."""
        report = ImpactReport(changed_id="REQ001", cascade_depth=0)
        with pytest.raises(ValidationError):
            report.changed_id = "REQ002"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SpecDraft ヘルパーメソッドのテスト
# ---------------------------------------------------------------------------


class TestSpecDraftCriteriaMethods:
    """SpecDraft.get_criteria_text / get_all_criteria_texts の検証."""

    def test_get_criteria_text_with_str(self) -> None:
        """str 形式の受入基準テキストをそのまま返す."""
        from colonyforge.requirement_analysis.models import SpecDraft

        # Arrange: str 受入基準を持つ SpecDraft
        draft = SpecDraft(
            draft_id="d-1",
            version=1,
            goal="テスト目標",
            acceptance_criteria=["AC1", "AC2"],
        )

        # Act
        text = draft.get_criteria_text(0)

        # Assert
        assert text == "AC1"

    def test_get_criteria_text_with_acceptance_criterion(self) -> None:
        """AcceptanceCriterion 形式の受入基準から .text を返す."""
        from colonyforge.requirement_analysis.models import (
            AcceptanceCriterion,
            SpecDraft,
        )

        # Arrange: AcceptanceCriterion オブジェクトを含む SpecDraft
        ac = AcceptanceCriterion(text="計測可能AC", measurable=True, metric="ms")
        draft = SpecDraft(
            draft_id="d-2",
            version=1,
            goal="テスト目標",
            acceptance_criteria=[ac],
        )

        # Act
        text = draft.get_criteria_text(0)

        # Assert
        assert text == "計測可能AC"

    def test_get_all_criteria_texts_mixed(self) -> None:
        """str と AcceptanceCriterion が混在するリストから全テキストを取得."""
        from colonyforge.requirement_analysis.models import (
            AcceptanceCriterion,
            SpecDraft,
        )

        # Arrange: 混合リスト
        ac = AcceptanceCriterion(text="構造化AC", measurable=False)
        draft = SpecDraft(
            draft_id="d-3",
            version=1,
            goal="テスト目標",
            acceptance_criteria=["文字列AC", ac, "もう1つ"],
        )

        # Act
        texts = draft.get_all_criteria_texts()

        # Assert
        assert texts == ["文字列AC", "構造化AC", "もう1つ"]
