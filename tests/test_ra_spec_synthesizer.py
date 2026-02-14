"""SpecSynthesizer テスト — §3.7 仕様草案統合.

SpecSynthesizer は全分析結果を統合して検証可能な SpecDraft を生成する。
LLM Worker Bee として実装し、IntentGraph + Assumption + FailureHypothesis から
構造化された仕様草案を出力する。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from colonyforge.requirement_analysis.models import (
    Assumption,
    AssumptionStatus,
    ChallengeReport,
    ChallengeVerdict,
    FailureHypothesis,
    IntentGraph,
    SpecDraft,
)

# ---------------------------------------------------------------------------
# W4 モデル テスト（GateCheck, RAGateResult, ChallengeReport 等）
# ---------------------------------------------------------------------------


class TestGateCheckModel:
    """GateCheck モデルの検証."""

    def test_valid_gate_check(self) -> None:
        """正常なゲートチェック結果."""
        from colonyforge.requirement_analysis.models import GateCheck

        # Arrange & Act
        check = GateCheck(name="goal_clarity", passed=True, reason="Goal is clear")

        # Assert
        assert check.name == "goal_clarity"
        assert check.passed is True
        assert check.reason == "Goal is clear"

    def test_gate_check_requires_name(self) -> None:
        """name は必須."""
        from colonyforge.requirement_analysis.models import GateCheck

        with pytest.raises(ValidationError):
            GateCheck(name="", passed=True, reason="ok")

    def test_gate_check_requires_reason(self) -> None:
        """reason は必須."""
        from colonyforge.requirement_analysis.models import GateCheck

        with pytest.raises(ValidationError):
            GateCheck(name="test", passed=True, reason="")


class TestRAGateResultModel:
    """RAGateResult モデルの検証."""

    def test_valid_gate_result(self) -> None:
        """正常なゲート結果."""
        from colonyforge.requirement_analysis.models import GateCheck, RAGateResult

        # Arrange
        checks = [GateCheck(name="goal_clarity", passed=True, reason="clear")]

        # Act
        result = RAGateResult(passed=True, checks=checks)

        # Assert
        assert result.passed is True
        assert len(result.checks) == 1
        assert result.required_actions == []

    def test_gate_result_with_actions(self) -> None:
        """必要アクション付きのゲート結果."""
        from colonyforge.requirement_analysis.models import GateCheck, RAGateResult

        # Arrange & Act
        result = RAGateResult(
            passed=False,
            checks=[GateCheck(name="risks_addressed", passed=False, reason="HIGH未対処")],
            required_actions=["Risk Challengerに再分析を要求"],
        )

        # Assert
        assert result.passed is False
        assert len(result.required_actions) == 1


class TestChallengeReportModel:
    """ChallengeReport モデルの検証."""

    def test_valid_challenge_report(self) -> None:
        """正常な ChallengeReport."""
        from colonyforge.requirement_analysis.models import (
            Challenge,
            RequiredAction,
        )

        # Arrange
        challenges = [
            Challenge(
                challenge_id="CH-001",
                claim="認証トークン漏洩",
                evidence="HTTPS未強制",
                severity="HIGH",
                required_action=RequiredAction.SPEC_REVISION,
                counterexample="HTTP接続でトークンが平文送信される",
            ),
        ]

        # Act
        report = ChallengeReport(
            report_id="cr1",
            draft_id="d1",
            challenges=challenges,
            verdict=ChallengeVerdict.BLOCK,
            summary="HIGH未対処あり",
        )

        # Assert
        assert report.unresolved_high == 1
        assert report.unresolved_medium == 0

    def test_challenge_report_resolved(self) -> None:
        """全件対処済みの場合 unresolved_high=0."""
        from colonyforge.requirement_analysis.models import (
            Challenge,
            RequiredAction,
        )

        # Arrange & Act
        report = ChallengeReport(
            report_id="cr2",
            draft_id="d1",
            challenges=[
                Challenge(
                    challenge_id="CH-001",
                    claim="c",
                    evidence="e",
                    severity="HIGH",
                    required_action=RequiredAction.BLOCK,
                    counterexample="cx",
                    addressed=True,
                    resolution="Fixed",
                ),
            ],
            verdict=ChallengeVerdict.PASS_WITH_RISKS,
            summary="全件対処済み",
        )

        # Assert
        assert report.unresolved_high == 0

    def test_challenge_report_max_5(self) -> None:
        """challenges は最大5件."""
        from colonyforge.requirement_analysis.models import (
            Challenge,
            RequiredAction,
        )

        # Arrange
        challenges = [
            Challenge(
                challenge_id=f"CH-{i:03d}",
                claim=f"claim{i}",
                evidence=f"evidence{i}",
                severity="LOW",
                required_action=RequiredAction.LOG_ONLY,
                counterexample=f"cx{i}",
            )
            for i in range(6)
        ]

        # Act & Assert
        with pytest.raises(ValidationError):
            ChallengeReport(
                report_id="cr3",
                draft_id="d1",
                challenges=challenges,
                verdict=ChallengeVerdict.PASS_WITH_RISKS,
                summary="too many",
            )


# ---------------------------------------------------------------------------
# SpecSynthesizer 初期化テスト
# ---------------------------------------------------------------------------


class TestSpecSynthesizerInit:
    """SpecSynthesizer の初期化."""

    def test_init_without_client(self) -> None:
        """LLMClient なしで初期化できる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange & Act
        synth = SpecSynthesizer()

        # Assert
        assert synth._client is None

    def test_init_with_client(self) -> None:
        """LLMClient を注入できる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()

        # Act
        synth = SpecSynthesizer(llm_client=client)

        # Assert
        assert synth._client is client


# ---------------------------------------------------------------------------
# SpecSynthesizer.synthesize() テスト
# ---------------------------------------------------------------------------


class TestSpecSynthesizerSynthesize:
    """SpecSynthesizer.synthesize() のテスト."""

    def _make_intent(self) -> IntentGraph:
        """テスト用 IntentGraph を生成."""
        return IntentGraph(
            goals=["ユーザー認証機能を実装する"],
            non_goals=["管理画面は対象外"],
            unknowns=["SSO対応は未定"],
        )

    def _make_assumptions(self) -> list[Assumption]:
        """テスト用 Assumption リストを生成."""
        return [
            Assumption(
                assumption_id="a1",
                text="メール+パスワード認証を使用",
                confidence=0.9,
                status=AssumptionStatus.AUTO_APPROVED,
            ),
        ]

    def _make_hypotheses(self) -> list[FailureHypothesis]:
        """テスト用 FailureHypothesis リストを生成."""
        return [
            FailureHypothesis(
                hypothesis_id="fh1",
                text="ブルートフォース攻撃",
                severity="HIGH",
                mitigation="レート制限を実装",
            ),
        ]

    def _make_llm_response(self, data: dict[str, Any]) -> MagicMock:
        """LLMResponse モックを生成."""
        resp = MagicMock()
        resp.content = json.dumps(data)
        return resp

    @pytest.mark.asyncio
    async def test_raises_without_client(self) -> None:
        """LLMClient 未注入時は RuntimeError."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        synth = SpecSynthesizer()

        # Act & Assert
        with pytest.raises(RuntimeError):
            await synth.synthesize(self._make_intent())

    @pytest.mark.asyncio
    async def test_returns_spec_draft(self) -> None:
        """LLM応答から SpecDraft を生成する."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "ユーザー認証機能を実装する",
                    "acceptance_criteria": [
                        {
                            "text": "ログイン成功時にJWT発行",
                            "measurable": True,
                            "metric": "JWT発行有無",
                            "threshold": "成功時に必ず発行",
                        }
                    ],
                    "constraints": ["HTTPS必須"],
                    "non_goals": ["管理画面"],
                    "open_items": ["SSO対応時期"],
                    "risk_mitigations": ["レート制限実装"],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent())

        # Assert
        assert isinstance(draft, SpecDraft)
        assert draft.goal == "ユーザー認証機能を実装する"
        assert len(draft.acceptance_criteria) == 1
        assert draft.version == 1

    @pytest.mark.asyncio
    async def test_passes_assumptions_to_prompt(self) -> None:
        """Assumption リストがプロンプトに含まれる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        await synth.synthesize(
            self._make_intent(),
            assumptions=self._make_assumptions(),
        )

        # Assert: chat が呼ばれ、メッセージにassumptionsが含まれる
        call_args = client.chat.call_args
        messages = call_args[0][0]
        user_msg = messages[-1].content
        assert "メール+パスワード認証を使用" in user_msg

    @pytest.mark.asyncio
    async def test_passes_failure_hypotheses_to_prompt(self) -> None:
        """FailureHypothesis リストがプロンプトに含まれる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        await synth.synthesize(
            self._make_intent(),
            failure_hypotheses=self._make_hypotheses(),
        )

        # Assert
        call_args = client.chat.call_args
        messages = call_args[0][0]
        user_msg = messages[-1].content
        assert "ブルートフォース攻撃" in user_msg

    @pytest.mark.asyncio
    async def test_version_increments(self) -> None:
        """version パラメータが SpecDraft に反映される."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent(), version=3)

        # Assert
        assert draft.version == 3

    @pytest.mark.asyncio
    async def test_draft_id_generated(self) -> None:
        """draft_id が自動生成される."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent())

        # Assert
        assert isinstance(draft.draft_id, str)
        assert len(draft.draft_id) > 0

    @pytest.mark.asyncio
    async def test_handles_code_block_response(self) -> None:
        """JSON がコードブロックに包まれている場合も正しくパースする."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        response_content = '```json\n{"goal": "テスト", "acceptance_criteria": [{"text": "AC1", "measurable": false}]}\n```'
        resp = MagicMock()
        resp.content = response_content
        client.chat = AsyncMock(return_value=resp)
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent())

        # Assert
        assert draft.goal == "テスト"

    @pytest.mark.asyncio
    async def test_acceptance_criteria_as_strings(self) -> None:
        """acceptance_criteria が文字列リストの場合も受け入れる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": ["AC1: テスト通過", "AC2: カバレッジ80%以上"],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent())

        # Assert
        assert len(draft.acceptance_criteria) == 2

    @pytest.mark.asyncio
    async def test_defaults_for_optional_fields(self) -> None:
        """LLM が省略したオプションフィールドはデフォルト値."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "最小限の仕様",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        draft = await synth.synthesize(self._make_intent())

        # Assert
        assert draft.constraints == []
        assert draft.non_goals == []
        assert draft.open_items == []
        assert draft.risk_mitigations == []

    @pytest.mark.asyncio
    async def test_system_prompt_contains_schema(self) -> None:
        """システムプロンプトに SpecDraft スキーマが含まれる."""
        from colonyforge.requirement_analysis.spec_synthesizer import SpecSynthesizer

        # Arrange
        client = MagicMock()
        client.chat = AsyncMock(
            return_value=self._make_llm_response(
                {
                    "goal": "テスト",
                    "acceptance_criteria": [{"text": "AC1", "measurable": False}],
                }
            )
        )
        synth = SpecSynthesizer(llm_client=client)

        # Act
        await synth.synthesize(self._make_intent())

        # Assert
        call_args = client.chat.call_args
        messages = call_args[0][0]
        system_msg = messages[0].content
        assert "acceptance_criteria" in system_msg
        assert "goal" in system_msg
