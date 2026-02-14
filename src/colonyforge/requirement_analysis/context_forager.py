"""ContextForager — AR/Honeycomb から内部証拠を収集（§5.3）.

過去の AR イベントを走査し、現在の要求分析に関連する
意思決定・Run結果・失敗履歴を構造化して EvidencePack にまとめる。

キーワードベースの関連度スコアで絞り込み、上位5件を返す。
"""

from __future__ import annotations

from colonyforge.core.events.base import BaseEvent
from colonyforge.core.events.types import EventType
from colonyforge.requirement_analysis.models import (
    DecisionRef,
    EvidencePack,
    FailureRef,
    IntentGraph,
    RunRef,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_MAX_RESULTS_PER_FIELD: int = 5
"""各フィールドの最大結果件数."""

_MIN_RELEVANCE_THRESHOLD: float = 0.1
"""bigram 関連度スコアの最小しきい値（ノイズ除去用）."""

# Run イベントタイプ
_RUN_EVENT_TYPES: frozenset[EventType] = frozenset({EventType.RUN_COMPLETED, EventType.RUN_FAILED})

_RUN_OUTCOME_MAP: dict[EventType, str] = {
    EventType.RUN_COMPLETED: "SUCCESS",
    EventType.RUN_FAILED: "FAILURE",
}


class ContextForager:
    """Context Forager — AR イベントから関連証拠を収集.

    DECISION_RECORDED → DecisionRef
    RUN_COMPLETED / RUN_FAILED → RunRef
    TASK_FAILED → FailureRef

    キーワード重複率で関連度スコアを算出し、上位5件を返す。
    """

    def __init__(self, *, events: list[BaseEvent] | None = None) -> None:
        self._events: list[BaseEvent] = events or []

    # ------------------------------------------------------------------
    # forage — メイン API
    # ------------------------------------------------------------------

    def forage(
        self,
        raw_input: str,
        *,
        intent_graph: IntentGraph | None = None,
    ) -> EvidencePack:
        """AR イベントから関連証拠を収集して EvidencePack を返す.

        Args:
            raw_input: ユーザーの入力テキスト
            intent_graph: 構造化された意図グラフ（あれば追加キーワードを抽出）

        Returns:
            EvidencePack: 収集された内部証拠
        """
        keywords = self._extract_keywords(raw_input, intent_graph)
        if not keywords:
            return EvidencePack()

        decisions = self._find_decisions(keywords)
        runs = self._find_runs(keywords)
        failures = self._find_failures(keywords)

        return EvidencePack(
            related_decisions=decisions,
            past_runs=runs,
            failure_history=failures,
        )

    # ------------------------------------------------------------------
    # should_search_web — WEB 検索の必要性判定
    # ------------------------------------------------------------------

    def should_search_web(
        self,
        raw_input: str,
        *,
        intent_graph: IntentGraph | None = None,
    ) -> tuple[bool, str]:
        """WEB 検索が必要かどうかを判定する.

        Args:
            raw_input: ユーザーの入力テキスト
            intent_graph: 意図グラフ

        Returns:
            (needed, reason): 検索の必要性と理由
        """
        if intent_graph is not None and intent_graph.unknowns:
            return (
                True,
                f"IntentGraph に {len(intent_graph.unknowns)} 件の unknown "
                "があるため WEB 検索が必要",
            )
        return (False, "WEB 検索不要: unknowns が空")

    # ------------------------------------------------------------------
    # private — キーワード抽出
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(
        raw_input: str,
        intent_graph: IntentGraph | None,
    ) -> set[str]:
        """入力テキストと IntentGraph からキーワードを抽出する."""
        words: set[str] = set()
        for w in raw_input.split():
            token = w.strip().lower()
            if len(token) >= 2:  # noqa: PLR2004 — 1文字トークンは除外
                words.add(token)
        if intent_graph is not None:
            for goal in intent_graph.goals:
                for w in goal.split():
                    token = w.strip().lower()
                    if len(token) >= 2:  # noqa: PLR2004
                        words.add(token)
        return words

    # ------------------------------------------------------------------
    # private — 関連度スコア
    # ------------------------------------------------------------------

    @staticmethod
    def _relevance_score(text: str, keywords: set[str]) -> float:
        """テキストとキーワードの bigram 重複率を返す (0.0–1.0).

        日本語テキストはスペースで区切られないため、
        キーワードから2文字 bigram を生成し、テキスト内での出現率で
        関連度を算出する。英語テキストでも同様に機能する。
        """
        if not keywords:
            return 0.0

        # キーワードから bigram セットを生成
        kw_bigrams: set[str] = set()
        for kw in keywords:
            kw_lower = kw.lower()
            for i in range(len(kw_lower) - 1):
                bg = kw_lower[i : i + 2]
                # 空白を含む bigram はスキップ
                if len(bg.strip()) >= 2:  # noqa: PLR2004
                    kw_bigrams.add(bg)

        if not kw_bigrams:
            return 0.0

        text_lower = text.lower()
        hits = sum(1 for bg in kw_bigrams if bg in text_lower)
        score = hits / len(kw_bigrams)

        # ノイズ除去: しきい値未満は 0.0
        return score if score >= _MIN_RELEVANCE_THRESHOLD else 0.0

    # ------------------------------------------------------------------
    # private — イベント種別ごとの抽出
    # ------------------------------------------------------------------

    def _find_decisions(self, keywords: set[str]) -> list[DecisionRef]:
        """DECISION_RECORDED イベントから DecisionRef を抽出する."""
        results: list[DecisionRef] = []
        for event in self._events:
            if event.type != EventType.DECISION_RECORDED:
                continue
            summary = event.payload.get("summary", "")
            score = self._relevance_score(summary, keywords)
            if score > 0.0:
                results.append(
                    DecisionRef(
                        decision_id=event.id,
                        summary=summary,
                        relevance_score=score,
                        superseded=bool(event.payload.get("superseded", False)),
                    )
                )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:_MAX_RESULTS_PER_FIELD]

    def _find_runs(self, keywords: set[str]) -> list[RunRef]:
        """RUN_COMPLETED / RUN_FAILED イベントから RunRef を抽出する."""
        results: list[RunRef] = []
        for event in self._events:
            if event.type not in _RUN_EVENT_TYPES:
                continue
            goal = event.payload.get("goal", "")
            score = self._relevance_score(goal, keywords)
            if score > 0.0:
                outcome = event.payload.get(
                    "outcome",
                    _RUN_OUTCOME_MAP.get(event.type, "UNKNOWN"),  # type: ignore[arg-type]
                )
                results.append(
                    RunRef(
                        run_id=event.id,
                        goal=goal,
                        outcome=outcome,
                        relevance_score=score,
                    )
                )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:_MAX_RESULTS_PER_FIELD]

    def _find_failures(self, keywords: set[str]) -> list[FailureRef]:
        """TASK_FAILED イベントから FailureRef を抽出する."""
        results: list[FailureRef] = []
        for event in self._events:
            if event.type != EventType.TASK_FAILED:
                continue
            summary = event.payload.get("summary", "")
            score = self._relevance_score(summary, keywords)
            if score > 0.0:
                results.append(
                    FailureRef(
                        run_id=event.id,
                        failure_class=event.payload.get("failure_class", "unknown"),
                        summary=summary,
                        relevance_score=score,
                    )
                )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:_MAX_RESULTS_PER_FIELD]
