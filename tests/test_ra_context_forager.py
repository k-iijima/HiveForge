"""ContextForager テスト — AR イベントから内部証拠を収集.

§5.3 EvidencePack の生成をテストする。
ContextForager は過去の AR イベントを検索し、
現在の要求分析に関連する証拠を構造化して返す。
"""

from __future__ import annotations

from colonyforge.core.events.base import BaseEvent
from colonyforge.core.events.types import EventType
from colonyforge.requirement_analysis.context_forager import ContextForager
from colonyforge.requirement_analysis.models import (
    DecisionRef,
    EvidencePack,
    FailureRef,
    IntentGraph,
    RunRef,
)

# ---------------------------------------------------------------------------
# ヘルパー: テスト用イベント生成
# ---------------------------------------------------------------------------


def _make_event(event_type: EventType, payload: dict) -> BaseEvent:  # type: ignore[type-arg]
    """テスト用のイベントを簡易生成する."""
    return BaseEvent(type=event_type, payload=payload)


# ---------------------------------------------------------------------------
# イベントなし → 空の EvidencePack
# ---------------------------------------------------------------------------


class TestContextForagerEmpty:
    """イベントが空のときは空の EvidencePack を返す."""

    def test_no_events_returns_empty_pack(self) -> None:
        """イベントが空の場合、全フィールドが空リストの EvidencePack を返す."""
        # Arrange: イベントなし
        forager = ContextForager(events=[])

        # Act: forage 実行
        pack = forager.forage("ログイン機能を実装して")

        # Assert: 全フィールドが空
        assert isinstance(pack, EvidencePack)
        assert pack.related_decisions == []
        assert pack.past_runs == []
        assert pack.failure_history == []
        assert pack.code_context == []
        assert pack.similar_episodes == []

    def test_default_constructor_no_events(self) -> None:
        """events 省略時も空の EvidencePack を返す."""
        # Arrange/Act
        forager = ContextForager()
        pack = forager.forage("テスト")

        # Assert
        assert pack.related_decisions == []


# ---------------------------------------------------------------------------
# DecisionRef 抽出 (DECISION_RECORDED イベントから)
# ---------------------------------------------------------------------------


class TestDecisionExtraction:
    """DECISION_RECORDED イベントから DecisionRef を抽出する."""

    def test_matching_decision_extracted(self) -> None:
        """キーワードが一致する DECISION_RECORDED イベントから DecisionRef を抽出する."""
        # Arrange: ログインに関する意思決定イベント
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "ログイン機能は OAuth2 を採用する",
                    "superseded": False,
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("ログイン機能を実装して")

        # Assert: DecisionRef が1件抽出される
        assert len(pack.related_decisions) == 1
        ref = pack.related_decisions[0]
        assert isinstance(ref, DecisionRef)
        assert "ログイン" in ref.summary or "OAuth2" in ref.summary
        assert ref.relevance_score > 0.0
        assert ref.superseded is False

    def test_non_matching_decision_excluded(self) -> None:
        """キーワードが一致しない DECISION_RECORDED は除外される."""
        # Arrange: 無関係なイベント
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "データベースはPostgreSQLを採用する",
                    "superseded": False,
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("ログイン機能を実装して")

        # Assert: 一致しないので空
        assert len(pack.related_decisions) == 0

    def test_superseded_decision_has_flag(self) -> None:
        """superseded=True の DECISION_RECORDED はフラグが保持される."""
        # Arrange
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "認証はBasic認証を採用する",
                    "superseded": True,
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("認証機能")

        # Assert
        assert len(pack.related_decisions) == 1
        assert pack.related_decisions[0].superseded is True


# ---------------------------------------------------------------------------
# RunRef 抽出 (RUN_COMPLETED / RUN_FAILED イベントから)
# ---------------------------------------------------------------------------


class TestRunExtraction:
    """RUN_COMPLETED / RUN_FAILED イベントから RunRef を抽出する."""

    def test_completed_run_extracted(self) -> None:
        """RUN_COMPLETED イベントから RunRef を抽出する."""
        # Arrange
        events = [
            _make_event(
                EventType.RUN_COMPLETED,
                {
                    "goal": "ユーザー認証の実装",
                    "outcome": "SUCCESS",
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("認証機能を追加して")

        # Assert
        assert len(pack.past_runs) == 1
        ref = pack.past_runs[0]
        assert isinstance(ref, RunRef)
        assert ref.outcome == "SUCCESS"
        assert ref.relevance_score > 0.0

    def test_failed_run_extracted(self) -> None:
        """RUN_FAILED イベントから RunRef を抽出する."""
        # Arrange
        events = [
            _make_event(
                EventType.RUN_FAILED,
                {
                    "goal": "認証のE2Eテスト",
                    "outcome": "FAILURE",
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("認証テスト")

        # Assert
        assert len(pack.past_runs) == 1
        assert pack.past_runs[0].outcome == "FAILURE"


# ---------------------------------------------------------------------------
# FailureRef 抽出 (TASK_FAILED イベントから)
# ---------------------------------------------------------------------------


class TestFailureExtraction:
    """TASK_FAILED イベントから FailureRef を抽出する."""

    def test_failed_task_extracted(self) -> None:
        """TASK_FAILED イベントから FailureRef を抽出する."""
        # Arrange
        events = [
            _make_event(
                EventType.TASK_FAILED,
                {
                    "failure_class": "RuntimeError",
                    "summary": "APIエンドポイントのタイムアウト",
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("APIタイムアウト対策")

        # Assert
        assert len(pack.failure_history) == 1
        ref = pack.failure_history[0]
        assert isinstance(ref, FailureRef)
        assert ref.failure_class == "RuntimeError"
        assert ref.relevance_score > 0.0

    def test_non_matching_failure_excluded(self) -> None:
        """キーワードが一致しない TASK_FAILED は除外される."""
        # Arrange
        events = [
            _make_event(
                EventType.TASK_FAILED,
                {
                    "failure_class": "PermissionError",
                    "summary": "ファイル書き込み権限エラー",
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("ログイン画面レイアウト")

        # Assert
        assert len(pack.failure_history) == 0


# ---------------------------------------------------------------------------
# IntentGraph によるキーワード強化
# ---------------------------------------------------------------------------


class TestIntentGraphEnhancement:
    """IntentGraph の goals からキーワードを追加して検索精度を上げる."""

    def test_intent_graph_goals_enhance_matching(self) -> None:
        """IntentGraph の goals にあるキーワードでマッチする."""
        # Arrange: raw_input だけではマッチしないが goals でマッチする
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "OAuth2 プロバイダとして Google を使用する",
                    "superseded": False,
                },
            ),
        ]
        forager = ContextForager(events=events)
        intent_graph = IntentGraph(
            goals=["OAuth2 認証を実装する"],
        )

        # Act
        pack = forager.forage("認証機能", intent_graph=intent_graph)

        # Assert: goals のキーワード "OAuth2" でマッチ
        assert len(pack.related_decisions) == 1


# ---------------------------------------------------------------------------
# 複数イベント × 複数タイプの統合
# ---------------------------------------------------------------------------


class TestMixedEvents:
    """複数タイプのイベントが混在する場合のテスト."""

    def test_mixed_events_separated_into_correct_fields(self) -> None:
        """異なるタイプのイベントが適切なフィールドに振り分けられる."""
        # Arrange
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "認証は JWT トークンを使用する",
                    "superseded": False,
                },
            ),
            _make_event(
                EventType.RUN_COMPLETED,
                {
                    "goal": "認証エンドポイントの実装",
                    "outcome": "SUCCESS",
                },
            ),
            _make_event(
                EventType.TASK_FAILED,
                {
                    "failure_class": "AuthError",
                    "summary": "認証トークンの検証に失敗",
                },
            ),
            # 無関係なイベント（除外される）
            _make_event(
                EventType.TASK_COMPLETED,
                {
                    "summary": "データベースマイグレーション完了",
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("認証機能を改善して")

        # Assert: 各フィールドに適切に振り分けられる
        assert len(pack.related_decisions) == 1  # DECISION_RECORDED
        assert len(pack.past_runs) == 1  # RUN_COMPLETED
        assert len(pack.failure_history) == 1  # TASK_FAILED

    def test_results_sorted_by_relevance(self) -> None:
        """結果は relevance_score 降順でソートされる."""
        # Arrange: 関連度が異なる2つの意思決定
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {"summary": "ログ出力にログレベルを設定する", "superseded": False},
            ),
            _make_event(
                EventType.DECISION_RECORDED,
                {
                    "summary": "ログイン機能のログインフローはOAuth2ログインを採用する",
                    "superseded": False,
                },
            ),
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("ログイン機能を実装")

        # Assert: 「ログイン」を多く含む方が先に来る
        if len(pack.related_decisions) >= 2:
            assert (
                pack.related_decisions[0].relevance_score
                >= pack.related_decisions[1].relevance_score
            )

    def test_max_5_results_per_field(self) -> None:
        """各フィールドの結果は最大5件に制限される."""
        # Arrange: 7件の DECISION_RECORDED（全てマッチする）
        events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {"summary": f"認証に関する決定 {i}", "superseded": False},
            )
            for i in range(7)
        ]
        forager = ContextForager(events=events)

        # Act
        pack = forager.forage("認証")

        # Assert: 最大5件
        assert len(pack.related_decisions) <= 5


# ---------------------------------------------------------------------------
# should_search_web() — WEB検索の必要性判定
# ---------------------------------------------------------------------------


class TestWebSearchDecision:
    """should_search_web() で WEB検索の必要性を判定する."""

    def test_unknowns_trigger_web_search(self) -> None:
        """IntentGraph に unknowns があると WEB検索が必要."""
        # Arrange
        forager = ContextForager()
        intent_graph = IntentGraph(
            goals=["OAuth2を実装する"],
            unknowns=["最新のOAuth2仕様はどこで確認できるか"],
        )

        # Act
        needed, reason = forager.should_search_web(
            raw_input="OAuth2を実装",
            intent_graph=intent_graph,
        )

        # Assert
        assert needed is True
        assert "unknown" in reason.lower() or "不明" in reason.lower()

    def test_no_unknowns_skips_web_search(self) -> None:
        """unknowns が空なら WEB検索不要."""
        # Arrange
        forager = ContextForager()
        intent_graph = IntentGraph(
            goals=["ユーザーリストを表示する"],
            unknowns=[],
        )

        # Act
        needed, reason = forager.should_search_web(
            raw_input="ユーザーリスト表示",
            intent_graph=intent_graph,
        )

        # Assert
        assert needed is False

    def test_no_intent_graph_skips_web_search(self) -> None:
        """IntentGraph なしでは WEB検索不要."""
        # Arrange
        forager = ContextForager()

        # Act
        needed, reason = forager.should_search_web(
            raw_input="テスト",
            intent_graph=None,
        )

        # Assert
        assert needed is False
