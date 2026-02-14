"""RiskChallenger テスト（§3.5 Phase A）.

IntentGraph + Assumption リストから失敗仮説(FailureHypothesis)を生成する
LLM Worker のテスト。

Phase A: 仮説段階の失敗仮説生成
Phase B: 仕様草案への Challenge Review（W4 で実装）

TDDサイクル: RED → GREEN → REFACTOR
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from colonyforge.requirement_analysis.models import (
    Assumption,
    FailureHypothesis,
    IntentGraph,
)
from colonyforge.requirement_analysis.risk_challenger import RiskChallenger

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


def _make_assumptions(
    items: list[tuple[str, str, float]] | None = None,
) -> list[Assumption]:
    """テスト用 Assumption リスト. items: [(id, text, confidence), ...]"""
    if items is None:
        items = [
            ("A1", "OAuth対応は不要", 0.8),
            ("A2", "既存認証モジュールを拡張する", 0.6),
        ]
    return [Assumption(assumption_id=aid, text=text, confidence=conf) for aid, text, conf in items]


# ---------------------------------------------------------------------------
# §5.5 FailureHypothesis モデルテスト
# ---------------------------------------------------------------------------


class TestFailureHypothesisModel:
    """FailureHypothesis データモデルの基本テスト."""

    def test_create_failure_hypothesis(self) -> None:
        """最小限のフィールドで FailureHypothesis を作成できる."""
        # Arrange & Act
        fh = FailureHypothesis(
            hypothesis_id="F1",
            text="セッション管理を無視するとセキュリティ脆弱性",
            severity="HIGH",
        )

        # Assert
        assert fh.hypothesis_id == "F1"
        assert fh.severity == "HIGH"
        assert fh.mitigation is None
        assert fh.addressed is False

    def test_create_with_mitigation(self) -> None:
        """緩和策付きで作成できる."""
        # Arrange & Act
        fh = FailureHypothesis(
            hypothesis_id="F1",
            text="パスワードハッシュ方式が未定義",
            severity="MEDIUM",
            mitigation="bcrypt指定を仕様に追加",
        )

        # Assert
        assert fh.mitigation == "bcrypt指定を仕様に追加"

    def test_failure_hypothesis_is_frozen(self) -> None:
        """FailureHypothesis は frozen でフィールド変更不可."""
        # Arrange
        fh = FailureHypothesis(hypothesis_id="F1", text="test", severity="LOW")

        # Act & Assert
        with pytest.raises(Exception):
            fh.addressed = True  # type: ignore[misc]

    def test_severity_values(self) -> None:
        """severity の各値で作成できる."""
        # Arrange & Act & Assert
        for sev in ("LOW", "MEDIUM", "HIGH"):
            fh = FailureHypothesis(hypothesis_id="F1", text="test", severity=sev)
            assert fh.severity == sev


# ---------------------------------------------------------------------------
# RiskChallenger 初期化テスト
# ---------------------------------------------------------------------------


class TestRiskChallengerInit:
    """RiskChallenger の初期化テスト."""

    def test_accepts_llm_client(self) -> None:
        """LLMClient を受け取れる."""
        # Arrange
        client = AsyncMock()

        # Act
        challenger = RiskChallenger(llm_client=client)

        # Assert
        assert challenger is not None

    def test_none_client_accepted(self) -> None:
        """client=None でも初期化できる."""
        # Act
        challenger = RiskChallenger()

        # Assert
        assert challenger is not None


# ---------------------------------------------------------------------------
# challenge() テスト — Phase A: 失敗仮説生成
# ---------------------------------------------------------------------------


class TestRiskChallengerChallenge:
    """RiskChallenger.challenge() のテスト（Phase A）."""

    @pytest.mark.asyncio
    async def test_basic_challenge(self) -> None:
        """LLM から失敗仮説を抽出できる."""
        # Arrange
        response = {
            "failure_hypotheses": [
                {
                    "hypothesis_id": "F1",
                    "text": "セッション管理を無視するとセキュリティ脆弱性",
                    "severity": "HIGH",
                    "mitigation": "セッションTTLを仕様に含める",
                },
                {
                    "hypothesis_id": "F2",
                    "text": "パスワードハッシュ方式が未定義",
                    "severity": "MEDIUM",
                    "mitigation": "bcrypt指定を仕様に追加",
                },
            ]
        }
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()
        assumptions = _make_assumptions()

        # Act
        result = await challenger.challenge(intent, assumptions)

        # Assert
        assert len(result) == 2
        assert all(isinstance(fh, FailureHypothesis) for fh in result)
        assert result[0].hypothesis_id == "F1"
        assert result[0].severity == "HIGH"
        assert result[0].mitigation is not None

    @pytest.mark.asyncio
    async def test_max_hypotheses_limit(self) -> None:
        """失敗仮説は最大5件まで."""
        # Arrange: 7件返す
        response = {
            "failure_hypotheses": [
                {
                    "hypothesis_id": f"F{i}",
                    "text": f"リスク{i}",
                    "severity": "MEDIUM",
                    "mitigation": None,
                }
                for i in range(1, 8)
            ]
        }
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await challenger.challenge(intent, [])

        # Assert: 最大5件に制限
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_no_client_raises(self) -> None:
        """LLMClient が設定されていない場合は RuntimeError."""
        # Arrange
        challenger = RiskChallenger()
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(RuntimeError, match="LLMClient"):
            await challenger.challenge(intent, [])

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        """LLM が無効な JSON を返した場合は例外."""
        # Arrange
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content="invalid"))
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            await challenger.challenge(intent, [])

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """システムプロンプトが含まれる."""
        # Arrange
        response = {"failure_hypotheses": []}
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act
        await challenger.challenge(intent, [])

        # Assert
        messages = client.chat.call_args[0][0]
        assert any(m.role == "system" for m in messages)

    @pytest.mark.asyncio
    async def test_intent_and_assumptions_in_message(self) -> None:
        """IntentGraph と Assumption が入力メッセージに含まれる."""
        # Arrange
        response = {"failure_hypotheses": []}
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph(goals=["認証機能を実装"])
        assumptions = _make_assumptions([("A1", "パスワード方式はbcrypt", 0.7)])

        # Act
        await challenger.challenge(intent, assumptions)

        # Assert
        messages = client.chat.call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert len(user_msgs) == 1
        content = user_msgs[0].content
        assert "認証機能を実装" in content
        assert "bcrypt" in content

    @pytest.mark.asyncio
    async def test_empty_hypotheses_allowed(self) -> None:
        """失敗仮説が0件でも正常動作する."""
        # Arrange
        response = {"failure_hypotheses": []}
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await challenger.challenge(intent, [])

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_code_block_json_response(self) -> None:
        """コードブロックで囲まれた JSON を処理できる."""
        # Arrange
        raw_json = json.dumps(
            {
                "failure_hypotheses": [
                    {
                        "hypothesis_id": "F1",
                        "text": "テスト",
                        "severity": "LOW",
                        "mitigation": None,
                    }
                ]
            }
        )
        client = AsyncMock()
        client.chat = AsyncMock(return_value=FakeLLMResponse(content=f"```json\n{raw_json}\n```"))
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await challenger.challenge(intent, [])

        # Assert
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_mitigation_optional(self) -> None:
        """mitigation は省略可能."""
        # Arrange
        response = {
            "failure_hypotheses": [
                {
                    "hypothesis_id": "F1",
                    "text": "緩和策なしのリスク",
                    "severity": "HIGH",
                },
            ]
        }
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph()

        # Act
        result = await challenger.challenge(intent, [])

        # Assert
        assert result[0].mitigation is None

    @pytest.mark.asyncio
    async def test_unknowns_in_message(self) -> None:
        """IntentGraph の unknowns がメッセージに含まれる."""
        # Arrange
        response = {"failure_hypotheses": []}
        client = _make_mock_client(response)
        challenger = RiskChallenger(llm_client=client)
        intent = _make_intent_graph(unknowns=["2FAは必要か"])

        # Act
        await challenger.challenge(intent, [])

        # Assert
        messages = client.chat.call_args[0][0]
        user_msgs = [m for m in messages if m.role == "user"]
        assert "2FA" in user_msgs[0].content
