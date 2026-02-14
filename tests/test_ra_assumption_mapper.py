"""AssumptionMapper テスト（§3.4）.

IntentGraph + コンテキスト情報から推定事項(Assumption)を抽出する
LLM Worker のテスト。

TDDサイクル: RED → GREEN → REFACTOR
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from colonyforge.requirement_analysis.assumption_mapper import AssumptionMapper
from colonyforge.requirement_analysis.models import (
    Assumption,
    AssumptionStatus,
    Constraint,
    ConstraintCategory,
    IntentGraph,
    SuccessCriterion,
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
    *,
    goals: list[str] | None = None,
    unknowns: list[str] | None = None,
    constraints: list[Constraint] | None = None,
    success_criteria: list[SuccessCriterion] | None = None,
) -> IntentGraph:
    """テスト用 IntentGraph を作成するヘルパー."""
    return IntentGraph(
        goals=goals or ["ログイン機能を実装する"],
        unknowns=unknowns or [],
        constraints=constraints or [],
        success_criteria=success_criteria or [],
    )


# ---------------------------------------------------------------------------
# §5.4 Assumption / AssumptionStatus モデルテスト
# ---------------------------------------------------------------------------


class TestAssumptionModel:
    """Assumption データモデルの基本テスト."""

    def test_create_assumption(self) -> None:
        """最小限のフィールドで Assumption を作成できる."""
        # Arrange & Act
        assumption = Assumption(
            assumption_id="A1",
            text="OAuth対応は不要",
            confidence=0.8,
        )

        # Assert
        assert assumption.assumption_id == "A1"
        assert assumption.text == "OAuth対応は不要"
        assert assumption.confidence == 0.8
        assert assumption.status == AssumptionStatus.PENDING
        assert assumption.evidence_ids == []
        assert assumption.user_response is None

    def test_assumption_with_all_fields(self) -> None:
        """全フィールドを指定して Assumption を作成できる."""
        # Arrange & Act
        assumption = Assumption(
            assumption_id="A2",
            text="既存認証モジュールを拡張する",
            confidence=0.6,
            evidence_ids=["RUN-018", "DEC-042"],
            status=AssumptionStatus.CONFIRMED,
            user_response="はい、既存モジュールを使います",
        )

        # Assert
        assert assumption.status == AssumptionStatus.CONFIRMED
        assert len(assumption.evidence_ids) == 2
        assert assumption.user_response is not None

    def test_assumption_is_frozen(self) -> None:
        """Assumption は frozen でフィールド変更不可."""
        # Arrange
        assumption = Assumption(assumption_id="A1", text="test", confidence=0.5)

        # Act & Assert
        with pytest.raises(Exception):
            assumption.status = AssumptionStatus.CONFIRMED  # type: ignore[misc]

    def test_assumption_confidence_boundaries(self) -> None:
        """confidence は 0.0 〜 1.0 の範囲."""
        # Arrange & Act
        low = Assumption(assumption_id="A1", text="test", confidence=0.0)
        high = Assumption(assumption_id="A2", text="test", confidence=1.0)

        # Assert
        assert low.confidence == 0.0
        assert high.confidence == 1.0

    def test_assumption_confidence_out_of_range(self) -> None:
        """confidence が範囲外の場合は ValidationError."""
        # Act & Assert
        with pytest.raises(Exception):
            Assumption(assumption_id="A1", text="test", confidence=1.1)

    def test_assumption_status_values(self) -> None:
        """AssumptionStatus の全値が存在する."""
        # Assert
        assert len(AssumptionStatus) == 4
        assert AssumptionStatus.PENDING == "pending"
        assert AssumptionStatus.CONFIRMED == "confirmed"
        assert AssumptionStatus.REJECTED == "rejected"
        assert AssumptionStatus.AUTO_APPROVED == "auto_approved"


# ---------------------------------------------------------------------------
# AssumptionMapper 初期化テスト
# ---------------------------------------------------------------------------


class TestAssumptionMapperInit:
    """AssumptionMapper の初期化テスト."""

    def test_accepts_llm_client(self) -> None:
        """LLMClient を受け取れる."""
        # Arrange
        client = AsyncMock()

        # Act
        mapper = AssumptionMapper(llm_client=client)

        # Assert: インスタンスが作成できること
        assert mapper is not None

    def test_none_client_accepted(self) -> None:
        """client=None でも初期化できる（extract時にエラー）."""
        # Act
        mapper = AssumptionMapper()

        # Assert
        assert mapper is not None


# ---------------------------------------------------------------------------
# extract() テスト
# ---------------------------------------------------------------------------


class TestAssumptionMapperExtract:
    """AssumptionMapper.extract() のテスト."""

    @pytest.mark.asyncio
    async def test_basic_extraction(self) -> None:
        """LLM から推定事項を抽出できる."""
        # Arrange: LLMが仮説リストを返す
        response = {
            "assumptions": [
                {
                    "assumption_id": "A1",
                    "text": "OAuth対応は不要",
                    "confidence": 0.8,
                    "evidence_ids": [],
                },
                {
                    "assumption_id": "A2",
                    "text": "既存認証モジュールを拡張する",
                    "confidence": 0.6,
                    "evidence_ids": [],
                },
            ]
        }
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert
        assert len(result) == 2
        assert all(isinstance(a, Assumption) for a in result)
        assert result[0].assumption_id == "A1"
        assert result[1].assumption_id == "A2"

    @pytest.mark.asyncio
    async def test_auto_approve_high_confidence(self) -> None:
        """confidence >= 0.8 の仮説は AUTO_APPROVED になる."""
        # Arrange
        response = {
            "assumptions": [
                {
                    "assumption_id": "A1",
                    "text": "明確な前提",
                    "confidence": 0.85,
                    "evidence_ids": ["DEC-042"],
                },
            ]
        }
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert: 高信頼度は自動承認
        assert result[0].status == AssumptionStatus.AUTO_APPROVED

    @pytest.mark.asyncio
    async def test_low_confidence_filtered_to_unknowns(self) -> None:
        """confidence < 0.3 の仮説はフィルタされる（unknowns扱い）."""
        # Arrange
        response = {
            "assumptions": [
                {
                    "assumption_id": "A1",
                    "text": "不確かな推定",
                    "confidence": 0.2,
                    "evidence_ids": [],
                },
                {
                    "assumption_id": "A2",
                    "text": "確度のある推定",
                    "confidence": 0.5,
                    "evidence_ids": [],
                },
            ]
        }
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert: confidence < 0.3 はフィルタされる
        assert len(result) == 1
        assert result[0].assumption_id == "A2"

    @pytest.mark.asyncio
    async def test_max_assumptions_limit(self) -> None:
        """仮説は最大10件まで."""
        # Arrange: 12件の仮説を返す
        response = {
            "assumptions": [
                {
                    "assumption_id": f"A{i}",
                    "text": f"仮説{i}",
                    "confidence": 0.5,
                    "evidence_ids": [],
                }
                for i in range(1, 13)
            ]
        }
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert: 最大10件に制限される
        assert len(result) <= 10

    @pytest.mark.asyncio
    async def test_no_client_raises(self) -> None:
        """LLMClient が設定されていない場合は RuntimeError."""
        # Arrange
        mapper = AssumptionMapper()
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(RuntimeError, match="LLMClient"):
            await mapper.extract(intent)

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        """LLM が無効な JSON を返した場合は例外."""
        # Arrange
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content="not json"))
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            await mapper.extract(intent)

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """システムプロンプトがメッセージに含まれる."""
        # Arrange
        response = {"assumptions": []}
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        await mapper.extract(intent)

        # Assert: chat() に system + user メッセージが送られている
        call_args = client.chat.call_args
        messages = call_args[0][0]
        assert any(m.role == "system" for m in messages)
        assert any(m.role == "user" for m in messages)

    @pytest.mark.asyncio
    async def test_intent_graph_in_user_message(self) -> None:
        """IntentGraph の情報がユーザーメッセージに含まれる."""
        # Arrange
        response = {"assumptions": []}
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph(
            goals=["ログイン機能"],
            unknowns=["OAuth対応は必要か"],
        )

        # Act
        await mapper.extract(intent)

        # Assert: user メッセージに IntentGraph の情報が含まれる
        call_args = client.chat.call_args
        messages = call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert len(user_msgs) == 1
        assert "ログイン機能" in user_msgs[0].content
        assert "OAuth" in user_msgs[0].content

    @pytest.mark.asyncio
    async def test_code_block_json_response(self) -> None:
        """コードブロックで囲まれた JSON を処理できる."""
        # Arrange
        raw_json = json.dumps(
            {
                "assumptions": [
                    {
                        "assumption_id": "A1",
                        "text": "テスト",
                        "confidence": 0.7,
                        "evidence_ids": [],
                    }
                ]
            }
        )
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content=f"```json\n{raw_json}\n```"))
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert
        assert len(result) == 1
        assert result[0].assumption_id == "A1"

    @pytest.mark.asyncio
    async def test_evidence_ids_preserved(self) -> None:
        """evidence_ids が保持される."""
        # Arrange
        response = {
            "assumptions": [
                {
                    "assumption_id": "A1",
                    "text": "既存認証モジュールを利用",
                    "confidence": 0.6,
                    "evidence_ids": ["RUN-018", "DEC-042"],
                },
            ]
        }
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert
        assert result[0].evidence_ids == ["RUN-018", "DEC-042"]

    @pytest.mark.asyncio
    async def test_empty_assumptions_allowed(self) -> None:
        """仮説が0件でも正常動作する."""
        # Arrange
        response = {"assumptions": []}
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await mapper.extract(intent)

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_constraints_in_user_message(self) -> None:
        """IntentGraph の制約情報がプロンプトに含まれる."""
        # Arrange
        response = {"assumptions": []}
        client = _make_mock_client(response)
        mapper = AssumptionMapper(llm_client=client)
        intent = _make_intent_graph(
            constraints=[
                Constraint(
                    text="認証方式は未定",
                    category=ConstraintCategory.TECHNICAL,
                    source="inferred",
                )
            ],
        )

        # Act
        await mapper.extract(intent)

        # Assert
        call_args = client.chat.call_args
        messages = call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert "認証方式は未定" in user_msgs[0].content
