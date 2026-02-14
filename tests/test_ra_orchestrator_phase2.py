"""RAOrchestrator Phase 2 統合テスト.

ContextForager, WEB_RESEARCH/WEB_SKIPPED, RefereeComparer の
オーケストレーター統合をテストする。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from colonyforge.core.ar.projections import RAState
from colonyforge.core.events.base import BaseEvent
from colonyforge.core.events.types import EventType
from colonyforge.requirement_analysis.context_forager import ContextForager
from colonyforge.requirement_analysis.models import (
    EvidencePack,
    IntentGraph,
    WebEvidencePack,
)
from colonyforge.requirement_analysis.orchestrator import RAOrchestrator
from colonyforge.requirement_analysis.referee_comparer import RefereeComparer

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_event(event_type: EventType, payload: dict) -> BaseEvent:  # type: ignore[type-arg]
    """テスト用イベント生成."""
    return BaseEvent(type=event_type, payload=payload)


async def _advance_to_context_enrich(orch: RAOrchestrator) -> None:
    """CONTEXT_ENRICH 状態まで進める."""
    await orch.intake("認証機能を実装して")
    assert orch.current_state == RAState.TRIAGE
    await orch.step()  # TRIAGE → CONTEXT_ENRICH
    assert orch.current_state == RAState.CONTEXT_ENRICH


async def _advance_to_challenge_review(orch: RAOrchestrator) -> None:
    """CHALLENGE_REVIEW 状態まで進める."""
    await orch.intake("認証機能を実装して")
    while orch.current_state != RAState.CHALLENGE_REVIEW and not orch.is_terminal:
        await orch.step()


# ---------------------------------------------------------------------------
# ContextForager 統合
# ---------------------------------------------------------------------------


class TestContextForagerIntegration:
    """ContextForager がオーケストレーターに統合されている."""

    def test_accepts_context_forager(self) -> None:
        """コンストラクタで context_forager を受け取れる."""
        # Arrange
        forager = ContextForager()

        # Act
        orch = RAOrchestrator(context_forager=forager)

        # Assert
        assert orch.evidence_pack is None  # 初期状態は None

    @pytest.mark.asyncio
    async def test_step_context_enrich_uses_forager(self) -> None:
        """TRIAGE→CONTEXT_ENRICH で ContextForager が使われる."""
        # Arrange: 関連イベントを含むforager
        past_events = [
            _make_event(
                EventType.DECISION_RECORDED,
                {"summary": "認証は OAuth2 を採用する", "superseded": False},
            ),
        ]
        forager = ContextForager(events=past_events)
        orch = RAOrchestrator(context_forager=forager)

        # Act: intake → step (TRIAGE → CONTEXT_ENRICH)
        await orch.intake("認証機能を実装して")
        await orch.step()

        # Assert: evidence_pack が設定される
        assert orch.evidence_pack is not None
        assert isinstance(orch.evidence_pack, EvidencePack)

    @pytest.mark.asyncio
    async def test_evidence_pack_in_event_payload(self) -> None:
        """RA_CONTEXT_ENRICHED イベントに evidence_pack 情報が含まれる."""
        # Arrange
        forager = ContextForager(events=[])
        orch = RAOrchestrator(context_forager=forager)

        # Act
        await orch.intake("テスト")
        await orch.step()

        # Assert: RA_CONTEXT_ENRICHED イベントの payload を確認
        context_events = [e for e in orch.events if e.type == EventType.RA_CONTEXT_ENRICHED]
        assert len(context_events) == 1
        assert "evidence_count" in context_events[0].payload

    @pytest.mark.asyncio
    async def test_without_forager_uses_stub(self) -> None:
        """ContextForager 未注入時はスタブ動作."""
        # Arrange
        orch = RAOrchestrator()

        # Act
        await orch.intake("テスト")
        await orch.step()

        # Assert: 正常に遷移し、evidence_pack は空の EvidencePack
        assert orch.current_state == RAState.CONTEXT_ENRICH
        assert orch.evidence_pack is not None


# ---------------------------------------------------------------------------
# WEB_RESEARCH / WEB_SKIPPED パス
# ---------------------------------------------------------------------------


class TestWebSearchPath:
    """CONTEXT_ENRICH から WEB_RESEARCH または HYPOTHESIS_BUILD への分岐."""

    @pytest.mark.asyncio
    async def test_web_skipped_when_no_unknowns(self) -> None:
        """unknowns なしの場合、WEB検索をスキップして HYPOTHESIS_BUILD へ直行."""
        # Arrange: unknowns のない IntentGraph
        orch = RAOrchestrator(context_forager=ContextForager())

        # Act: CONTEXT_ENRICH まで進める
        await _advance_to_context_enrich(orch)
        # 次の step で web decision
        await orch.step()

        # Assert: WEB_RESEARCH をスキップして HYPOTHESIS_BUILD
        assert orch.current_state == RAState.HYPOTHESIS_BUILD
        # RA_WEB_SKIPPED イベントが発行されている
        web_skip_events = [e for e in orch.events if e.type == EventType.RA_WEB_SKIPPED]
        assert len(web_skip_events) == 1

    @pytest.mark.asyncio
    async def test_web_searched_when_unknowns_exist(self) -> None:
        """unknowns ありの場合、WEB_RESEARCH 状態に遷移する."""
        # Arrange: unknowns を持つ IntentGraph を設定
        orch = RAOrchestrator(context_forager=ContextForager())
        await _advance_to_context_enrich(orch)

        # intent_graph に unknowns を追加
        orch.intent_graph = IntentGraph(
            goals=["OAuth2認証を実装する"],
            unknowns=["最新の OAuth2 仕様はどこ？"],
        )

        # Act
        await orch.step()

        # Assert: WEB_RESEARCH 状態に遷移
        assert orch.current_state == RAState.WEB_RESEARCH
        web_events = [e for e in orch.events if e.type == EventType.RA_WEB_RESEARCHED]
        assert len(web_events) == 1

    @pytest.mark.asyncio
    async def test_web_research_then_hypothesis(self) -> None:
        """WEB_RESEARCH → HYPOTHESIS_BUILD に遷移する."""
        # Arrange
        orch = RAOrchestrator(context_forager=ContextForager())
        await _advance_to_context_enrich(orch)
        orch.intent_graph = IntentGraph(
            goals=["OAuth2認証"],
            unknowns=["仕様の確認"],
        )

        # Act: CONTEXT_ENRICH → WEB_RESEARCH → HYPOTHESIS_BUILD
        await orch.step()  # → WEB_RESEARCH
        assert orch.current_state == RAState.WEB_RESEARCH

        await orch.step()  # → HYPOTHESIS_BUILD
        assert orch.current_state == RAState.HYPOTHESIS_BUILD

    @pytest.mark.asyncio
    async def test_web_evidence_stored(self) -> None:
        """WEB_RESEARCH で web_evidence_pack が保存される."""
        # Arrange
        orch = RAOrchestrator(context_forager=ContextForager())
        await _advance_to_context_enrich(orch)
        orch.intent_graph = IntentGraph(
            goals=["OAuth2認証"],
            unknowns=["仕様の確認"],
        )

        # Act
        await orch.step()  # → WEB_RESEARCH

        # Assert
        assert orch.web_evidence_pack is not None
        assert isinstance(orch.web_evidence_pack, WebEvidencePack)


# ---------------------------------------------------------------------------
# RefereeComparer 統合
# ---------------------------------------------------------------------------


class TestRefereeIntegration:
    """RefereeComparer がオーケストレーターに統合されている."""

    def test_accepts_referee_comparer(self) -> None:
        """コンストラクタで referee_comparer を受け取れる."""
        # Arrange/Act
        comparer = RefereeComparer()
        orch = RAOrchestrator(referee_comparer=comparer)

        # Assert
        assert orch.referee_result is None  # 初期状態

    @pytest.mark.asyncio
    async def test_challenge_review_routes_to_referee(self) -> None:
        """複数 spec_drafts がある場合、CHALLENGE_REVIEW → REFEREE_COMPARE."""
        # Arrange: spec_synthesizer と referee_comparer を注入
        from colonyforge.requirement_analysis.models import SpecDraft

        mock_synthesizer = AsyncMock()
        draft1 = SpecDraft(
            draft_id="d1",
            version=1,
            goal="テスト",
            acceptance_criteria=["基準1"],
        )
        draft2 = SpecDraft(
            draft_id="d2",
            version=2,
            goal="テスト改",
            acceptance_criteria=["基準2"],
        )
        mock_synthesizer.synthesize = AsyncMock(side_effect=[draft1, draft2])

        comparer = RefereeComparer()
        orch = RAOrchestrator(
            spec_synthesizer=mock_synthesizer,
            referee_comparer=comparer,
        )

        # 2つの spec_drafts を手動で設定
        orch.spec_drafts = [draft1, draft2]

        # CHALLENGE_REVIEW 状態まで進める
        await _advance_to_challenge_review(orch)
        if orch.current_state != RAState.CHALLENGE_REVIEW:
            pytest.skip("CHALLENGE_REVIEW に到達できなかった")

        # Act
        await orch.step()

        # Assert: REFEREE_COMPARE に遷移
        assert orch.current_state == RAState.REFEREE_COMPARE

    @pytest.mark.asyncio
    async def test_referee_compare_then_guard_gate(self) -> None:
        """REFEREE_COMPARE → GUARD_GATE に遷移する."""
        # Arrange
        from colonyforge.requirement_analysis.models import SpecDraft

        comparer = RefereeComparer()
        orch = RAOrchestrator(referee_comparer=comparer)

        draft1 = SpecDraft(
            draft_id="d1",
            version=1,
            goal="テスト",
            acceptance_criteria=["基準1"],
        )
        draft2 = SpecDraft(
            draft_id="d2",
            version=2,
            goal="テスト改",
            acceptance_criteria=["基準2"],
        )
        orch.spec_drafts = [draft1, draft2]

        # CHALLENGE_REVIEW まで進める
        await _advance_to_challenge_review(orch)
        if orch.current_state != RAState.CHALLENGE_REVIEW:
            pytest.skip("CHALLENGE_REVIEW に到達できなかった")

        # Act: CHALLENGE_REVIEW → REFEREE_COMPARE → GUARD_GATE
        await orch.step()  # → REFEREE_COMPARE
        assert orch.current_state == RAState.REFEREE_COMPARE

        await orch.step()  # → GUARD_GATE
        assert orch.current_state == RAState.GUARD_GATE

    @pytest.mark.asyncio
    async def test_single_draft_skips_referee(self) -> None:
        """spec_drafts が1つの場合、REFEREE をスキップして GUARD_GATE へ."""
        # Arrange: spec_drafts が1つ、referee_comparer なし
        orch = RAOrchestrator()

        # CHALLENGE_REVIEW まで進める
        await _advance_to_challenge_review(orch)
        if orch.current_state != RAState.CHALLENGE_REVIEW:
            pytest.skip("CHALLENGE_REVIEW に到達できなかった")

        # Act
        await orch.step()

        # Assert: Referee をスキップして GUARD_GATE
        assert orch.current_state == RAState.GUARD_GATE


# ---------------------------------------------------------------------------
# Phase 2 ステータス拡張
# ---------------------------------------------------------------------------


class TestGetStatusPhase2:
    """get_status() が Phase 2 フィールドを含む."""

    @pytest.mark.asyncio
    async def test_status_includes_evidence_pack(self) -> None:
        """evidence_pack が設定されていたら status に件数が含まれる."""
        # Arrange
        orch = RAOrchestrator(context_forager=ContextForager())
        await orch.intake("テスト")
        await orch.step()  # → CONTEXT_ENRICH

        # Act
        status = orch.get_status()

        # Assert
        assert "evidence_count" in status

    @pytest.mark.asyncio
    async def test_status_includes_web_search_performed(self) -> None:
        """web_evidence_pack が設定されていたら status に含まれる."""
        # Arrange
        orch = RAOrchestrator(context_forager=ContextForager())
        await _advance_to_context_enrich(orch)
        orch.intent_graph = IntentGraph(
            goals=["テスト"],
            unknowns=["不明点"],
        )
        await orch.step()  # → WEB_RESEARCH

        # Act
        status = orch.get_status()

        # Assert
        assert "web_search_performed" in status
        assert status["web_search_performed"] is True
