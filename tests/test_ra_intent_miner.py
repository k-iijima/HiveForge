"""IntentMiner テスト — §3.1 意図グラフ抽出.

IntentMiner はユーザー入力テキストから LLM を使って構造化された
IntentGraph を抽出する。テストでは LLMClient をモックして
パース・バリデーションロジックを検証する。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from colonyforge.requirement_analysis.intent_miner import IntentMiner
from colonyforge.requirement_analysis.models import (
    Constraint,
    ConstraintCategory,
    IntentGraph,
    SuccessCriterion,
)

# ---------------------------------------------------------------------------
# IntentGraph モデルテスト（§5.2）
# ---------------------------------------------------------------------------


class TestIntentGraphModel:
    """IntentGraph Pydantic モデルの検証."""

    def test_minimal_creation(self) -> None:
        """goals のみで作成できる."""
        # Arrange & Act
        graph = IntentGraph(goals=["ログイン機能を作る"])

        # Assert
        assert graph.goals == ["ログイン機能を作る"]
        assert graph.success_criteria == []
        assert graph.constraints == []
        assert graph.non_goals == []
        assert graph.unknowns == []

    def test_full_creation(self) -> None:
        """全フィールドで作成できる."""
        # Arrange & Act
        graph = IntentGraph(
            goals=["認証機能を実装する"],
            success_criteria=[
                SuccessCriterion(text="JWT発行", measurable=True, source="explicit"),
            ],
            constraints=[
                Constraint(
                    text="既存DBを使用",
                    category=ConstraintCategory.TECHNICAL,
                    source="explicit",
                ),
            ],
            non_goals=["OAuth対応"],
            unknowns=["セッション有効期限"],
        )

        # Assert
        assert len(graph.goals) == 1
        assert len(graph.success_criteria) == 1
        assert graph.success_criteria[0].measurable is True
        assert len(graph.constraints) == 1
        assert graph.constraints[0].category == ConstraintCategory.TECHNICAL
        assert graph.non_goals == ["OAuth対応"]
        assert graph.unknowns == ["セッション有効期限"]

    def test_goals_required(self) -> None:
        """goals は必須（min_length=1）."""
        with pytest.raises(Exception):
            IntentGraph(goals=[])

    def test_frozen(self) -> None:
        """frozen=True で値変更が禁止される."""
        # Arrange
        graph = IntentGraph(goals=["test"])

        # Act & Assert
        with pytest.raises(Exception):
            graph.goals = ["changed"]  # type: ignore[misc]


class TestSuccessCriterionModel:
    """SuccessCriterion モデルの検証."""

    def test_default_source(self) -> None:
        """source のデフォルトは 'inferred'."""
        # Arrange & Act
        sc = SuccessCriterion(text="JWT発行")

        # Assert
        assert sc.source == "inferred"
        assert sc.measurable is False

    def test_explicit_source(self) -> None:
        """source を 'explicit' に設定できる."""
        sc = SuccessCriterion(text="200ms以内", measurable=True, source="explicit")
        assert sc.source == "explicit"
        assert sc.measurable is True


class TestConstraintModel:
    """Constraint モデルの検証."""

    def test_all_categories(self) -> None:
        """全 ConstraintCategory が使用可能."""
        # Arrange & Act & Assert
        for cat in ConstraintCategory:
            c = Constraint(text=f"test-{cat}", category=cat)
            assert c.category == cat

    def test_category_count(self) -> None:
        """ConstraintCategory は6種類（§5.2）."""
        assert len(ConstraintCategory) == 6


# ---------------------------------------------------------------------------
# IntentMiner テスト
# ---------------------------------------------------------------------------


def _make_mock_client(response_content: str) -> MagicMock:
    """LLMClient のモックを生成する."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_content
    mock_response.tool_calls = []
    client.chat = AsyncMock(return_value=mock_response)
    return client


def _intent_graph_json(
    *,
    goals: list[str] | None = None,
    success_criteria: list[dict[str, Any]] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    non_goals: list[str] | None = None,
    unknowns: list[str] | None = None,
) -> str:
    """IntentGraph の JSON 文字列を生成するヘルパー."""
    data: dict[str, Any] = {
        "goals": goals or ["ログイン機能を作る"],
        "success_criteria": success_criteria or [],
        "constraints": constraints or [],
        "non_goals": non_goals or [],
        "unknowns": unknowns or [],
    }
    return json.dumps(data, ensure_ascii=False)


class TestIntentMinerInit:
    """IntentMiner の初期化テスト."""

    def test_accepts_llm_client(self) -> None:
        """LLMClient を受け取れる."""
        # Arrange
        client = MagicMock()

        # Act
        miner = IntentMiner(llm_client=client)

        # Assert
        assert miner._client is client

    def test_none_client_accepted(self) -> None:
        """client=None でも初期化可能（後で設定）."""
        # Arrange & Act
        miner = IntentMiner(llm_client=None)

        # Assert
        assert miner._client is None


class TestIntentMinerExtract:
    """extract() — テキストから IntentGraph を抽出."""

    @pytest.mark.asyncio
    async def test_basic_extraction(self) -> None:
        """LLM レスポンスから IntentGraph を正しくパースする."""
        # Arrange
        response_json = _intent_graph_json(
            goals=["ユーザー認証機能を実装する"],
            success_criteria=[{"text": "JWT発行", "measurable": True, "source": "inferred"}],
            unknowns=["OAuth対応は必要か"],
        )
        client = _make_mock_client(response_json)
        miner = IntentMiner(llm_client=client)

        # Act
        graph = await miner.extract("ログイン機能を作って")

        # Assert
        assert isinstance(graph, IntentGraph)
        assert graph.goals == ["ユーザー認証機能を実装する"]
        assert len(graph.success_criteria) == 1
        assert graph.success_criteria[0].text == "JWT発行"
        assert graph.unknowns == ["OAuth対応は必要か"]

    @pytest.mark.asyncio
    async def test_code_block_extraction(self) -> None:
        """LLM がコードブロックでJSON を返した場合もパースできる."""
        # Arrange: LLM が ```json ... ``` で返すケース
        json_content = _intent_graph_json(goals=["テスト機能"])
        response = f"```json\n{json_content}\n```"
        client = _make_mock_client(response)
        miner = IntentMiner(llm_client=client)

        # Act
        graph = await miner.extract("テスト機能を追加して")

        # Assert
        assert graph.goals == ["テスト機能"]

    @pytest.mark.asyncio
    async def test_constraints_parsing(self) -> None:
        """制約条件が正しくパースされる."""
        # Arrange
        response_json = _intent_graph_json(
            goals=["API実装"],
            constraints=[
                {
                    "text": "既存DBを使用",
                    "category": "technical",
                    "source": "explicit",
                }
            ],
        )
        client = _make_mock_client(response_json)
        miner = IntentMiner(llm_client=client)

        # Act
        graph = await miner.extract("APIを作って、既存のDBを使って")

        # Assert
        assert len(graph.constraints) == 1
        assert graph.constraints[0].category == ConstraintCategory.TECHNICAL
        assert graph.constraints[0].source == "explicit"

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        """LLM が無効な JSON を返した場合は例外が伝搬する.

        フォールバック禁止原則: エラーを握りつぶさず伝搬させる。
        """
        # Arrange
        client = _make_mock_client("これはJSONではありません")
        miner = IntentMiner(llm_client=client)

        # Act & Assert
        with pytest.raises(Exception):
            await miner.extract("何かして")

    @pytest.mark.asyncio
    async def test_invalid_schema_raises(self) -> None:
        """LLM のJSON がスキーマに合わない場合は例外が伝搬する.

        goals が空配列の場合、Pydantic ValidationError が発生する。
        """
        # Arrange: goals が空 → min_length=1 に違反
        response_json = json.dumps({"goals": []})
        client = _make_mock_client(response_json)
        miner = IntentMiner(llm_client=client)

        # Act & Assert
        with pytest.raises(Exception):
            await miner.extract("何かして")

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self) -> None:
        """LLM にシステムプロンプトが送信される."""
        # Arrange
        client = _make_mock_client(_intent_graph_json())
        miner = IntentMiner(llm_client=client)

        # Act
        await miner.extract("テスト")

        # Assert: chat() が呼ばれ、最初のメッセージが system role
        client.chat.assert_called_once()
        messages = client.chat.call_args[0][0]
        assert messages[0].role == "system"

    @pytest.mark.asyncio
    async def test_user_text_in_messages(self) -> None:
        """ユーザー入力テキストがメッセージに含まれる."""
        # Arrange
        client = _make_mock_client(_intent_graph_json())
        miner = IntentMiner(llm_client=client)

        # Act
        await miner.extract("ログイン機能を作って")

        # Assert: user role のメッセージにユーザー入力が含まれる
        messages = client.chat.call_args[0][0]
        user_messages = [m for m in messages if m.role == "user"]
        assert len(user_messages) >= 1
        assert "ログイン機能を作って" in user_messages[0].content

    @pytest.mark.asyncio
    async def test_no_client_raises(self) -> None:
        """LLMClient が None の場合は例外が発生する.

        フォールバック禁止原則: None でフォールバックせず早期エラー。
        """
        # Arrange
        miner = IntentMiner(llm_client=None)

        # Act & Assert
        with pytest.raises(RuntimeError, match="LLMClient"):
            await miner.extract("何かして")

    @pytest.mark.asyncio
    async def test_non_goals_preserved(self) -> None:
        """non_goals がそのまま保存される."""
        # Arrange
        response_json = _intent_graph_json(
            goals=["機能実装"],
            non_goals=["OAuth対応", "2FA対応"],
        )
        client = _make_mock_client(response_json)
        miner = IntentMiner(llm_client=client)

        # Act
        graph = await miner.extract("機能を作って")

        # Assert
        assert graph.non_goals == ["OAuth対応", "2FA対応"]

    @pytest.mark.asyncio
    async def test_multiple_goals(self) -> None:
        """複数の goals が正しくパースされる."""
        # Arrange
        response_json = _intent_graph_json(
            goals=["認証機能", "ユーザー管理画面"],
        )
        client = _make_mock_client(response_json)
        miner = IntentMiner(llm_client=client)

        # Act
        graph = await miner.extract("認証機能とユーザー管理画面を作って")

        # Assert
        assert len(graph.goals) == 2
