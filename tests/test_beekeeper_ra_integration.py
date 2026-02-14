"""Beekeeper RA Colony 統合テスト

BeekeeperMCPServer が RA Colony（要求分析）をタスク委譲前に実行し、
ClarificationQuestions を _ask_user() 経由でユーザーに提示する統合を検証する。

§2: 「Beekeeperと実行Colonyの間にRA Colonyを挿入」
§10: UXパターン（質問提示、高速パス）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from colonyforge.beekeeper.ra_integration import RAAnalysisResult, RequirementAnalysisMixin
from colonyforge.beekeeper.server import BeekeeperMCPServer
from colonyforge.core import AkashicRecord
from colonyforge.requirement_analysis.models import (
    AnalysisPath,
    ClarificationQuestion,
    ClarificationRound,
    QuestionType,
    RAGateResult,
    SpecDraft,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ar(tmp_path):
    """テスト用 Akashic Record"""
    return AkashicRecord(vault_path=tmp_path)


@pytest.fixture
def beekeeper(ar):
    """テスト用 Beekeeper（RA統合あり）"""
    return BeekeeperMCPServer(ar=ar)


# ---------------------------------------------------------------------------
# ヘルパー: モック付き RAOrchestrator
# ---------------------------------------------------------------------------


def _make_orchestrator_instant_pass() -> RAOrchestrator:
    """instant_pass パスを模擬する RAOrchestrator を構築する.

    スコアが低い入力を intake して全ステップを通す。
    """
    orch = RAOrchestrator()
    return orch


def _make_orchestrator_with_questions(
    questions: list[ClarificationQuestion],
) -> RAOrchestrator:
    """質問つきの RAOrchestrator を返す（clarification_rounds に手動注入）."""
    orch = RAOrchestrator()
    orch.clarification_rounds = [
        ClarificationRound(round_number=1, questions=questions),
    ]
    return orch


# ---------------------------------------------------------------------------
# RAAnalysisResult モデル
# ---------------------------------------------------------------------------


class TestRAAnalysisResult:
    """RAAnalysisResult データクラスの基本テスト"""

    def test_default_passed_true(self):
        """デフォルトで passed=True"""
        # Arrange & Act
        result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.INSTANT_PASS,
        )

        # Assert
        assert result.passed is True
        assert result.analysis_path == AnalysisPath.INSTANT_PASS
        assert result.spec_draft is None
        assert result.gate_result is None
        assert result.answers == {}

    def test_with_spec_draft(self):
        """SpecDraft を含む結果"""
        # Arrange
        draft = SpecDraft(
            draft_id="draft-1",
            goal="ログイン機能",
            acceptance_criteria=["認証成功時にJWTが発行される"],
            constraints=[],
            non_goals=[],
            open_items=[],
            version=1,
        )

        # Act
        result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            spec_draft=draft,
        )

        # Assert
        assert result.spec_draft is not None
        assert result.spec_draft.goal == "ログイン機能"

    def test_with_answers(self):
        """回答辞書を含む結果"""
        # Arrange & Act
        result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            answers={"Q1": "必要", "Q2": "不要"},
        )

        # Assert
        assert result.answers == {"Q1": "必要", "Q2": "不要"}

    def test_failed_with_gate_result(self):
        """Gate 失敗の結果"""
        # Arrange
        from colonyforge.requirement_analysis.models import GateCheck

        gate = RAGateResult(
            passed=False,
            checks=[
                GateCheck(name="goal_clarity", passed=False, reason="ゴールが空"),
            ],
            required_actions=["ゴールが空"],
        )

        # Act
        result = RAAnalysisResult(
            passed=False,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            gate_result=gate,
        )

        # Assert
        assert result.passed is False
        assert result.gate_result is not None
        assert not result.gate_result.passed


# ---------------------------------------------------------------------------
# RequirementAnalysisMixin — _analyze_requirements
# ---------------------------------------------------------------------------


class TestAnalyzeRequirements:
    """_analyze_requirements メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_instant_pass_returns_passed(self, beekeeper):
        """低曖昧性タスクは即パスする

        ambiguity<0.3, context_sufficiency>0.8, execution_risk<0.3 の
        タスクは INSTANT_PASS と判定され、質問なしで passed=True が返る。
        """
        # Arrange: 低曖昧性タスク
        task = "修正"  # 短い単純なタスク → 低曖昧性

        # Act
        result = await beekeeper._analyze_requirements(task)

        # Assert
        assert result.passed is True
        assert result.analysis_path is not None

    @pytest.mark.asyncio
    async def test_full_analysis_with_questions(self, beekeeper):
        """質問が生成される場合、_ask_user で提示される

        ClarifyGenerator が質問を生成した場合、RequirementAnalysisMixin は
        各質問を _ask_user() 経由でユーザーに提示する。
        """
        # Arrange: ClarifyGenerator をモックして質問を返す
        questions = [
            ClarificationQuestion(
                question_id="Q1",
                text="OAuth認証は必要ですか？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=["必要", "不要", "将来対応"],
                impact="high",
            ),
        ]

        mock_clarify = AsyncMock()
        mock_clarify.generate.return_value = ClarificationRound(round_number=1, questions=questions)

        # _ask_user をモックして即座に回答を返す
        beekeeper._ask_user = AsyncMock(return_value="approved: 不要")

        # RA コンポーネントを注入
        beekeeper._ra_components = {"clarify_generator": mock_clarify}

        # Act
        result = await beekeeper._analyze_requirements(
            "ログイン機能を作って。メール+パスワード認証で"
        )

        # Assert: _ask_user が呼ばれた
        assert beekeeper._ask_user.called
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_analysis_with_gate_failure(self, beekeeper):
        """Guard Gate がブロックした場合 passed=False が返る"""
        # Arrange: SpecSynthesizer + Guard Gate をモックして失敗を返す
        from colonyforge.requirement_analysis.gate import RAGuardGate
        from colonyforge.requirement_analysis.models import GateCheck

        # SpecSynthesizer が draft を生成しないと Gate は呼ばれない
        mock_synthesizer = AsyncMock()
        mock_synthesizer.synthesize.return_value = SpecDraft(
            draft_id="draft-fail",
            goal="ログイン機能",
            acceptance_criteria=["認証が動作する"],
            constraints=[],
            non_goals=[],
            open_items=[],
            version=1,
        )

        mock_gate = RAGuardGate()
        failed_result = RAGateResult(
            passed=False,
            checks=[GateCheck(name="goal_clarity", passed=False, reason="ゴール不明")],
            required_actions=["ゴール不明"],
        )
        mock_gate.evaluate = lambda spec, **kwargs: failed_result  # type: ignore[assignment]

        beekeeper._ra_components = {
            "spec_synthesizer": mock_synthesizer,
            "guard_gate": mock_gate,
        }
        beekeeper._ask_user = AsyncMock(return_value="approved: OK")

        # Act
        result = await beekeeper._analyze_requirements("ログイン機能を作って")

        # Assert
        assert result.passed is False
        assert result.gate_result is not None
        assert not result.gate_result.passed

    @pytest.mark.asyncio
    async def test_ra_disabled_returns_immediate_pass(self, beekeeper):
        """RA無効化時は即 passed=True を返す"""
        # Arrange
        beekeeper._ra_enabled = False

        # Act
        result = await beekeeper._analyze_requirements("何でも")

        # Assert
        assert result.passed is True
        assert result.analysis_path == AnalysisPath.INSTANT_PASS
        assert result.spec_draft is None

    @pytest.mark.asyncio
    async def test_analysis_stores_events(self, beekeeper):
        """分析結果にRAイベントが含まれる"""
        # Arrange
        beekeeper._ask_user = AsyncMock(return_value="approved: OK")

        # Act
        result = await beekeeper._analyze_requirements("テストを実行して")

        # Assert: イベントが記録されている
        assert len(result.events) > 0

    @pytest.mark.asyncio
    async def test_analysis_stores_spec_draft(self, beekeeper):
        """SpecSynthesizer 注入時に SpecDraft が結果に含まれる"""
        # Arrange: SpecSynthesizer モック
        mock_synthesizer = AsyncMock()
        mock_synthesizer.synthesize.return_value = SpecDraft(
            draft_id="draft-test",
            goal="テスト実行",
            acceptance_criteria=["テストが全件通過する"],
            constraints=[],
            non_goals=[],
            open_items=[],
            version=1,
        )
        beekeeper._ra_components = {"spec_synthesizer": mock_synthesizer}
        beekeeper._ask_user = AsyncMock(return_value="approved: OK")

        # Act
        result = await beekeeper._analyze_requirements("テストを実行して")

        # Assert
        assert result.spec_draft is not None
        assert result.spec_draft.goal == "テスト実行"

    @pytest.mark.asyncio
    async def test_analysis_path_in_result(self, beekeeper):
        """AnalysisPath が結果に含まれる"""
        # Act
        result = await beekeeper._analyze_requirements("テスト")

        # Assert
        assert result.analysis_path in (
            AnalysisPath.INSTANT_PASS,
            AnalysisPath.ASSUMPTION_PASS,
            AnalysisPath.FULL_ANALYSIS,
        )


# ---------------------------------------------------------------------------
# RequirementAnalysisMixin — _present_clarification_questions
# ---------------------------------------------------------------------------


class TestPresentClarificationQuestions:
    """_present_clarification_questions のテスト"""

    @pytest.mark.asyncio
    async def test_single_question_presented(self, beekeeper):
        """単一質問が _ask_user に渡される"""
        # Arrange
        questions = [
            ClarificationQuestion(
                question_id="Q1",
                text="認証方式は？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=["JWT", "Session", "OAuth"],
                impact="high",
            ),
        ]
        round_ = ClarificationRound(round_number=1, questions=questions)
        beekeeper._ask_user = AsyncMock(return_value="approved: JWT")

        # Act
        answers = await beekeeper._present_clarification_questions(round_)

        # Assert
        beekeeper._ask_user.assert_called_once()
        call_kwargs = beekeeper._ask_user.call_args.kwargs
        assert call_kwargs["question"] == "認証方式は？"
        assert answers["Q1"] == "approved: JWT"

    @pytest.mark.asyncio
    async def test_multiple_questions_all_presented(self, beekeeper):
        """複数質問が全てユーザーに提示される"""
        # Arrange
        questions = [
            ClarificationQuestion(
                question_id="Q1",
                text="OAuth必要？",
                question_type=QuestionType.YES_NO,
                options=["はい", "いいえ"],
                impact="high",
            ),
            ClarificationQuestion(
                question_id="Q2",
                text="2FA必要？",
                question_type=QuestionType.YES_NO,
                options=["はい", "いいえ"],
                impact="medium",
            ),
            ClarificationQuestion(
                question_id="Q3",
                text="権限分離は？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=["不要", "必要", "後で決める"],
                impact="low",
            ),
        ]
        round_ = ClarificationRound(round_number=1, questions=questions)
        beekeeper._ask_user = AsyncMock(
            side_effect=["approved: いいえ", "approved: いいえ", "approved: 不要"]
        )

        # Act
        answers = await beekeeper._present_clarification_questions(round_)

        # Assert: 3回呼ばれた
        assert beekeeper._ask_user.call_count == 3
        assert len(answers) == 3
        assert "Q1" in answers
        assert "Q2" in answers
        assert "Q3" in answers

    @pytest.mark.asyncio
    async def test_question_options_passed_to_ask_user(self, beekeeper):
        """選択肢が _ask_user の options に渡される"""
        # Arrange
        questions = [
            ClarificationQuestion(
                question_id="Q1",
                text="デプロイ先は？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=["AWS", "GCP", "Azure"],
                impact="high",
            ),
        ]
        round_ = ClarificationRound(round_number=1, questions=questions)
        beekeeper._ask_user = AsyncMock(return_value="approved: AWS")

        # Act
        await beekeeper._present_clarification_questions(round_)

        # Assert: options が渡されている
        call_kwargs = beekeeper._ask_user.call_args
        # _ask_user(question, options) の形式
        if call_kwargs[1]:
            passed_options = call_kwargs[1].get("options")
        else:
            passed_options = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None
        assert passed_options == ["AWS", "GCP", "Azure"]

    @pytest.mark.asyncio
    async def test_free_text_question_no_options(self, beekeeper):
        """自由記述の質問は選択肢なしで提示される"""
        # Arrange
        questions = [
            ClarificationQuestion(
                question_id="Q1",
                text="詳細を教えてください",
                question_type=QuestionType.FREE_TEXT,
                options=[],
                impact="medium",
            ),
        ]
        round_ = ClarificationRound(round_number=1, questions=questions)
        beekeeper._ask_user = AsyncMock(return_value="approved: 詳細説明テキスト")

        # Act
        await beekeeper._present_clarification_questions(round_)

        # Assert: options は None
        call_kwargs = beekeeper._ask_user.call_args
        if call_kwargs[1]:
            passed_options = call_kwargs[1].get("options")
        else:
            passed_options = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None
        assert passed_options is None

    @pytest.mark.asyncio
    async def test_empty_round_returns_empty_answers(self, beekeeper):
        """質問が空のラウンドは空の回答辞書を返す"""
        # Arrange
        round_ = ClarificationRound(round_number=1, questions=[])
        beekeeper._ask_user = AsyncMock()

        # Act
        answers = await beekeeper._present_clarification_questions(round_)

        # Assert
        assert answers == {}
        beekeeper._ask_user.assert_not_called()


# ---------------------------------------------------------------------------
# RequirementAnalysisMixin — _format_analysis_summary
# ---------------------------------------------------------------------------


class TestFormatAnalysisSummary:
    """_format_analysis_summary のテスト"""

    def test_instant_pass_summary(self, beekeeper):
        """高速パスのサマリフォーマット"""
        # Arrange
        result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.INSTANT_PASS,
        )

        # Act
        summary = beekeeper._format_analysis_summary(result)

        # Assert
        assert "即実行" in summary or "instant" in summary.lower()

    def test_passed_with_spec_draft_summary(self, beekeeper):
        """仕様草案つき通過のサマリ"""
        # Arrange
        draft = SpecDraft(
            draft_id="draft-summary",
            goal="ログイン機能実装",
            acceptance_criteria=["認証成功時にJWTが発行される"],
            constraints=[],
            non_goals=[],
            open_items=[],
            version=1,
        )
        result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            spec_draft=draft,
        )

        # Act
        summary = beekeeper._format_analysis_summary(result)

        # Assert
        assert "ログイン機能実装" in summary

    def test_failed_summary_includes_reason(self, beekeeper):
        """失敗サマリに理由が含まれる"""
        # Arrange
        from colonyforge.requirement_analysis.models import GateCheck

        gate = RAGateResult(
            passed=False,
            checks=[GateCheck(name="goal_clarity", passed=False, reason="ゴール不明")],
            required_actions=["ゴール不明"],
        )
        result = RAAnalysisResult(
            passed=False,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            gate_result=gate,
        )

        # Act
        summary = beekeeper._format_analysis_summary(result)

        # Assert
        assert "ゴール不明" in summary


# ---------------------------------------------------------------------------
# _delegate_to_queen RA 統合
# ---------------------------------------------------------------------------


class TestDelegateToQueenRAIntegration:
    """_delegate_to_queen での RA Colony 統合テスト"""

    @pytest.mark.asyncio
    async def test_delegate_calls_analyze_requirements(self, beekeeper):
        """_delegate_to_queen は _analyze_requirements を呼ぶ"""
        # Arrange: _analyze_requirements をモック
        mock_result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.INSTANT_PASS,
        )
        beekeeper._analyze_requirements = AsyncMock(return_value=mock_result)

        # _delegate_to_queen の Queen Bee 部分もモック
        with patch.object(
            beekeeper, "_delegate_to_queen_internal", new_callable=AsyncMock
        ) as mock_queen:
            mock_queen.return_value = "タスク完了 (1/1)"
            await beekeeper._delegate_to_queen("colony-1", "テスト実行")

        # Assert: _analyze_requirements が呼ばれた
        beekeeper._analyze_requirements.assert_called_once_with("テスト実行", None)

    @pytest.mark.asyncio
    async def test_delegate_blocks_on_gate_failure(self, beekeeper):
        """Gate 失敗時は委譲をブロックする"""
        # Arrange: _analyze_requirements が失敗を返す
        from colonyforge.requirement_analysis.models import GateCheck

        failed_gate = RAGateResult(
            passed=False,
            checks=[GateCheck(name="goal_clarity", passed=False, reason="ゴール不明")],
            required_actions=["ゴール不明"],
        )
        mock_result = RAAnalysisResult(
            passed=False,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            gate_result=failed_gate,
        )
        beekeeper._analyze_requirements = AsyncMock(return_value=mock_result)

        # Act
        result = await beekeeper._delegate_to_queen("colony-1", "曖昧なタスク")

        # Assert: ブロックメッセージが返される
        assert "要求分析" in result or "ブロック" in result or "中止" in result

    @pytest.mark.asyncio
    async def test_delegate_passes_context_to_analyze(self, beekeeper):
        """context が _analyze_requirements に渡される"""
        # Arrange
        mock_result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.INSTANT_PASS,
        )
        beekeeper._analyze_requirements = AsyncMock(return_value=mock_result)

        with patch.object(
            beekeeper, "_delegate_to_queen_internal", new_callable=AsyncMock
        ) as mock_queen:
            mock_queen.return_value = "タスク完了"
            context = {"complexity": 3, "risk": 2}
            await beekeeper._delegate_to_queen("colony-1", "タスク", context)

        # Assert: context が渡された
        beekeeper._analyze_requirements.assert_called_once_with("タスク", context)

    @pytest.mark.asyncio
    async def test_delegate_enriches_context_with_spec_draft(self, beekeeper):
        """RA結果のSpecDraftがQueen委譲時のcontextに含まれる"""
        # Arrange
        draft = SpecDraft(
            draft_id="draft-delegate",
            goal="テスト機能",
            acceptance_criteria=["テストが通過する"],
            constraints=[],
            non_goals=[],
            open_items=[],
            version=1,
        )
        mock_result = RAAnalysisResult(
            passed=True,
            analysis_path=AnalysisPath.FULL_ANALYSIS,
            spec_draft=draft,
        )
        beekeeper._analyze_requirements = AsyncMock(return_value=mock_result)

        with patch.object(
            beekeeper, "_delegate_to_queen_internal", new_callable=AsyncMock
        ) as mock_queen:
            mock_queen.return_value = "タスク完了"
            await beekeeper._delegate_to_queen("colony-1", "テスト", {})

        # Assert: _delegate_to_queen_internal にSpecDraft情報が渡された
        call_args = mock_queen.call_args
        passed_context = call_args[1].get("context") or call_args[0][2]
        assert "spec_draft" in passed_context or "ra_spec_goal" in passed_context


# ---------------------------------------------------------------------------
# _create_ra_orchestrator
# ---------------------------------------------------------------------------


class TestCreateRAOrchestrator:
    """_create_ra_orchestrator のテスト"""

    def test_creates_orchestrator_with_default_scorer(self, beekeeper):
        """デフォルトの AmbiguityScorer で orchestrator が作られる"""
        # Act
        orch = beekeeper._create_ra_orchestrator()

        # Assert
        assert isinstance(orch, RAOrchestrator)

    def test_creates_orchestrator_with_injected_components(self, beekeeper):
        """_ra_components から注入されたコンポーネントが使われる"""
        # Arrange
        mock_gate = object()
        beekeeper._ra_components = {"guard_gate": mock_gate}

        # Act
        orch = beekeeper._create_ra_orchestrator()

        # Assert
        assert isinstance(orch, RAOrchestrator)
        assert orch._guard_gate is mock_gate


# ---------------------------------------------------------------------------
# BeekeeperMCPServer Mixin 継承確認
# ---------------------------------------------------------------------------


class TestBeekeeperHasRAMixin:
    """BeekeeperMCPServer が RequirementAnalysisMixin を継承していること"""

    def test_beekeeper_is_instance_of_ra_mixin(self, beekeeper):
        """BeekeeperMCPServer は RequirementAnalysisMixin のインスタンス"""
        # Assert
        assert isinstance(beekeeper, RequirementAnalysisMixin)

    def test_beekeeper_has_analyze_requirements(self, beekeeper):
        """_analyze_requirements メソッドが存在する"""
        # Assert
        assert hasattr(beekeeper, "_analyze_requirements")
        assert callable(beekeeper._analyze_requirements)

    def test_beekeeper_has_present_clarification(self, beekeeper):
        """_present_clarification_questions メソッドが存在する"""
        # Assert
        assert hasattr(beekeeper, "_present_clarification_questions")
        assert callable(beekeeper._present_clarification_questions)

    def test_beekeeper_has_format_summary(self, beekeeper):
        """_format_analysis_summary メソッドが存在する"""
        # Assert
        assert hasattr(beekeeper, "_format_analysis_summary")
        assert callable(beekeeper._format_analysis_summary)

    def test_beekeeper_has_ra_enabled(self, beekeeper):
        """_ra_enabled 属性が存在する（デフォルト True）"""
        # Assert
        assert hasattr(beekeeper, "_ra_enabled")
        assert beekeeper._ra_enabled is True
