"""ClarifyGenerator テスト（§3.7 Clarification Generator）.

未解決の unknowns / pending Assumptions / FailureHypotheses から
ユーザーへの質問リスト (ClarificationRound) を生成する LLM Worker のテスト。

§4.3 ルール:
- 最大3ラウンド、各ラウンド最大3問
- 質問不要の場合は空ラウンド（skip_to_spec フラグ）

TDDサイクル: RED → GREEN → REFACTOR
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from colonyforge.requirement_analysis.clarify_generator import ClarifyGenerator
from colonyforge.requirement_analysis.models import (
    Assumption,
    ClarificationQuestion,
    ClarificationRound,
    FailureHypothesis,
    IntentGraph,
    QuestionType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeLLMResponse:
    """テスト用LLMレスポンス."""

    content: str | None
    tool_calls: list[Any] = None  # type: ignore[assignment]
    finish_reason: str = "stop"

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = []


def _make_mock_client(response_json: dict[str, Any]) -> AsyncMock:
    """LLMClient のモックを作成する."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=FakeLLMResponse(content=json.dumps(response_json)))
    return client


def _make_intent_graph(
    goals: list[str] | None = None,
    unknowns: list[str] | None = None,
) -> IntentGraph:
    """テスト用 IntentGraph."""
    return IntentGraph(
        goals=goals or ["ログイン機能を実装する"],
        unknowns=unknowns or [],
    )


# ---------------------------------------------------------------------------
# §5.6 ClarificationQuestion / ClarificationRound モデルテスト
# ---------------------------------------------------------------------------


class TestClarificationQuestionModel:
    """ClarificationQuestion データモデルの基本テスト."""

    def test_create_question(self) -> None:
        """最小限のフィールドで質問を作成できる."""
        # Arrange & Act
        q = ClarificationQuestion(
            question_id="Q1",
            text="OAuth対応は必要ですか？",
        )

        # Assert
        assert q.question_id == "Q1"
        assert q.question_type == QuestionType.FREE_TEXT
        assert q.options == []
        assert q.impact == "medium"
        assert q.answer is None

    def test_question_with_options(self) -> None:
        """選択肢付き質問を作成できる."""
        # Arrange & Act
        q = ClarificationQuestion(
            question_id="Q1",
            text="認証方式はどれですか？",
            question_type=QuestionType.SINGLE_CHOICE,
            options=["メール/パスワード", "OAuth", "SAML"],
        )

        # Assert
        assert q.question_type == QuestionType.SINGLE_CHOICE
        assert len(q.options) == 3

    def test_question_is_frozen(self) -> None:
        """ClarificationQuestion は frozen."""
        # Arrange
        q = ClarificationQuestion(question_id="Q1", text="test?")

        # Act & Assert
        with pytest.raises(Exception):
            q.answer = "yes"  # type: ignore[misc]

    def test_question_type_values(self) -> None:
        """QuestionType の全値が存在する."""
        # Assert
        assert len(QuestionType) == 4
        assert QuestionType.YES_NO == "yes_no"
        assert QuestionType.SINGLE_CHOICE == "single_choice"
        assert QuestionType.MULTI_CHOICE == "multi_choice"
        assert QuestionType.FREE_TEXT == "free_text"


class TestClarificationRoundModel:
    """ClarificationRound データモデルの基本テスト."""

    def test_create_round(self) -> None:
        """ラウンドを作成できる."""
        # Arrange
        q = ClarificationQuestion(question_id="Q1", text="test?")

        # Act
        r = ClarificationRound(round_number=1, questions=[q])

        # Assert
        assert r.round_number == 1
        assert len(r.questions) == 1

    def test_max_three_questions(self) -> None:
        """1ラウンドの質問数が3件以下."""
        # Arrange
        questions = [ClarificationQuestion(question_id=f"Q{i}", text=f"Q{i}?") for i in range(1, 4)]

        # Act
        r = ClarificationRound(round_number=1, questions=questions)

        # Assert
        assert len(r.questions) == 3

    def test_exceed_max_questions_raises(self) -> None:
        """4件以上の質問は ValidationError."""
        # Arrange
        questions = [ClarificationQuestion(question_id=f"Q{i}", text=f"Q{i}?") for i in range(1, 5)]

        # Act & Assert
        with pytest.raises(Exception):
            ClarificationRound(round_number=1, questions=questions)

    def test_round_is_frozen(self) -> None:
        """ClarificationRound は frozen."""
        # Arrange
        q = ClarificationQuestion(question_id="Q1", text="test?")
        r = ClarificationRound(round_number=1, questions=[q])

        # Act & Assert
        with pytest.raises(Exception):
            r.round_number = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ClarifyGenerator 初期化テスト
# ---------------------------------------------------------------------------


class TestClarifyGeneratorInit:
    """ClarifyGenerator の初期化テスト."""

    def test_accepts_llm_client(self) -> None:
        """LLMClient を受け取れる."""
        # Arrange & Act
        gen = ClarifyGenerator(llm_client=AsyncMock())

        # Assert
        assert gen is not None

    def test_none_client_accepted(self) -> None:
        """client=None でも初期化できる."""
        # Act
        gen = ClarifyGenerator()

        # Assert
        assert gen is not None


# ---------------------------------------------------------------------------
# generate() テスト
# ---------------------------------------------------------------------------


class TestClarifyGeneratorGenerate:
    """ClarifyGenerator.generate() のテスト."""

    @pytest.mark.asyncio
    async def test_basic_generation(self) -> None:
        """LLM から質問を生成できる."""
        # Arrange
        response = {
            "questions": [
                {
                    "question_id": "Q1",
                    "text": "OAuth対応は必要ですか？",
                    "question_type": "yes_no",
                    "options": [],
                    "impact": "high",
                    "related_assumption_ids": ["A1"],
                },
                {
                    "question_id": "Q2",
                    "text": "2FAは必要ですか？",
                    "question_type": "yes_no",
                    "options": [],
                    "impact": "medium",
                    "related_assumption_ids": [],
                },
            ]
        }
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph(unknowns=["OAuth対応", "2FA対応"])
        assumptions = [
            Assumption(assumption_id="A1", text="OAuth不要", confidence=0.5),
        ]

        # Act
        result = await gen.generate(
            intent=intent,
            assumptions=assumptions,
            round_number=1,
        )

        # Assert
        assert isinstance(result, ClarificationRound)
        assert result.round_number == 1
        assert len(result.questions) == 2
        assert result.questions[0].question_id == "Q1"

    @pytest.mark.asyncio
    async def test_max_three_questions_enforced(self) -> None:
        """LLMが4件以上返しても3件に制限される."""
        # Arrange: 5件返す
        response = {
            "questions": [
                {
                    "question_id": f"Q{i}",
                    "text": f"質問{i}？",
                    "question_type": "free_text",
                    "impact": "medium",
                }
                for i in range(1, 6)
            ]
        }
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await gen.generate(intent=intent, round_number=1)

        # Assert: 最大3件に制限
        assert len(result.questions) <= 3

    @pytest.mark.asyncio
    async def test_no_questions_needed(self) -> None:
        """質問不要の場合は空の質問リスト."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await gen.generate(intent=intent, round_number=1)

        # Assert
        assert len(result.questions) == 0

    @pytest.mark.asyncio
    async def test_no_client_raises(self) -> None:
        """LLMClient が設定されていない場合は RuntimeError."""
        # Arrange
        gen = ClarifyGenerator()
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(RuntimeError, match="LLMClient"):
            await gen.generate(intent=intent, round_number=1)

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        """LLM が無効な JSON を返した場合は例外."""
        # Arrange
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content="not json"))
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            await gen.generate(intent=intent, round_number=1)

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """システムプロンプトが含まれる."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        await gen.generate(intent=intent, round_number=1)

        # Assert
        messages = client.chat.call_args[0][0]
        assert any(m.role == "system" for m in messages)

    @pytest.mark.asyncio
    async def test_unknowns_in_prompt(self) -> None:
        """unknowns がプロンプトに含まれる."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph(unknowns=["2FAは必要か"])

        # Act
        await gen.generate(intent=intent, round_number=1)

        # Assert
        messages = client.chat.call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert "2FA" in user_msgs[0].content

    @pytest.mark.asyncio
    async def test_assumptions_in_prompt(self) -> None:
        """pending の Assumption がプロンプトに含まれる."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()
        assumptions = [
            Assumption(assumption_id="A1", text="bcrypt使用", confidence=0.5),
        ]

        # Act
        await gen.generate(intent=intent, assumptions=assumptions, round_number=1)

        # Assert
        messages = client.chat.call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert "bcrypt" in user_msgs[0].content

    @pytest.mark.asyncio
    async def test_failure_hypotheses_in_prompt(self) -> None:
        """FailureHypothesis がプロンプトに含まれる."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()
        fh = [
            FailureHypothesis(
                hypothesis_id="F1",
                text="セッションTTL未設定",
                severity="HIGH",
            ),
        ]

        # Act
        await gen.generate(intent=intent, failure_hypotheses=fh, round_number=1)

        # Assert
        messages = client.chat.call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert "セッションTTL" in user_msgs[0].content

    @pytest.mark.asyncio
    async def test_code_block_json_response(self) -> None:
        """コードブロックで囲まれた JSON を処理できる."""
        # Arrange
        raw_json = json.dumps(
            {
                "questions": [
                    {
                        "question_id": "Q1",
                        "text": "テスト質問？",
                        "question_type": "free_text",
                        "impact": "low",
                    }
                ]
            }
        )
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content=f"```json\n{raw_json}\n```"))
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await gen.generate(intent=intent, round_number=1)

        # Assert
        assert len(result.questions) == 1

    @pytest.mark.asyncio
    async def test_round_number_preserved(self) -> None:
        """指定した round_number が結果に反映される."""
        # Arrange
        response = {"questions": []}
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await gen.generate(intent=intent, round_number=2)

        # Assert
        assert result.round_number == 2

    @pytest.mark.asyncio
    async def test_question_type_preserved(self) -> None:
        """LLM が返した question_type が保持される."""
        # Arrange
        response = {
            "questions": [
                {
                    "question_id": "Q1",
                    "text": "対応は必要？",
                    "question_type": "single_choice",
                    "options": ["はい", "いいえ", "未定"],
                    "impact": "high",
                }
            ]
        }
        client = _make_mock_client(response)
        gen = ClarifyGenerator(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await gen.generate(intent=intent, round_number=1)

        # Assert
        assert result.questions[0].question_type == QuestionType.SINGLE_CHOICE
        assert result.questions[0].options == ["はい", "いいえ", "未定"]
