"""Requirement Analysis Colony — 状態機械のテスト.

RAStateMachine の状態遷移を設計書 §4 の仕様に基づき検証する。
"""

import pytest

from colonyforge.core.ar.projections import RAState
from colonyforge.core.events import EventType
from colonyforge.core.events.ra import (
    RAChallengeReviewedEvent,
    RAClarifyGeneratedEvent,
    RACompletedEvent,
    RAContextEnrichedEvent,
    RAGateDecidedEvent,
    RAHypothesisBuiltEvent,
    RAIntakeReceivedEvent,
    RASpecSynthesizedEvent,
    RATriageCompletedEvent,
    RAUserRespondedEvent,
)
from colonyforge.core.state import RAStateMachine, TransitionError


class TestRAStateMachineInitial:
    """RAStateMachine の初期状態テスト"""

    def test_initial_state_is_intake(self):
        """初期状態はINTAKE

        RA Colony はユーザーの生テキスト受領から開始する。
        """
        # Arrange: なし

        # Act
        sm = RAStateMachine()

        # Assert
        assert sm.current_state == RAState.INTAKE


class TestRAStateMachineHappyPath:
    """RAStateMachine の正常系遷移テスト — 設計書 §4.2 のメインパス"""

    def test_intake_to_triage(self):
        """INTAKE → TRIAGE: 生テキスト受領後に分解へ進む"""
        # Arrange
        sm = RAStateMachine()
        event = RATriageCompletedEvent(run_id="run-001", payload={"goal": "ユーザー認証"})

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.TRIAGE

    def test_triage_to_context_enrich(self):
        """TRIAGE → CONTEXT_ENRICH: 分解完了後にコンテキスト収集へ"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.TRIAGE
        event = RAContextEnrichedEvent(run_id="run-001", payload={"evidence_count": 3})

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.CONTEXT_ENRICH

    def test_context_enrich_to_hypothesis_build(self):
        """CONTEXT_ENRICH → HYPOTHESIS_BUILD: WEB検索不要時のスキップパス"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.CONTEXT_ENRICH
        event = RAHypothesisBuiltEvent(
            run_id="run-001",
            payload={"assumptions_count": 3, "failure_hypotheses_count": 2},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.HYPOTHESIS_BUILD

    def test_hypothesis_build_to_clarify_gen(self):
        """HYPOTHESIS_BUILD → CLARIFY_GEN: 仮説構築後に質問生成へ"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.HYPOTHESIS_BUILD
        event = RAClarifyGeneratedEvent(
            run_id="run-001",
            payload={"questions": ["OAuth対応は？"], "round": 1},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.CLARIFY_GEN

    def test_clarify_gen_to_spec_synthesis_when_no_questions(self):
        """CLARIFY_GEN → SPEC_SYNTHESIS: 質問不要の場合"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.CLARIFY_GEN
        event = RASpecSynthesizedEvent(
            run_id="run-001",
            payload={"draft_id": "draft-001", "version": 1},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.SPEC_SYNTHESIS

    def test_spec_synthesis_to_challenge_review(self):
        """SPEC_SYNTHESIS → CHALLENGE_REVIEW: 仕様草案生成後にChallenge Reviewへ"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.SPEC_SYNTHESIS
        event = RAChallengeReviewedEvent(
            run_id="run-001",
            payload={"verdict": "PASS_WITH_RISKS"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.CHALLENGE_REVIEW

    def test_challenge_review_to_guard_gate(self):
        """CHALLENGE_REVIEW → GUARD_GATE: PASS_WITH_RISKS時にGuard Gateへ"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.CHALLENGE_REVIEW
        event = RAGateDecidedEvent(
            run_id="run-001",
            payload={"result": "PASS"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.GUARD_GATE

    def test_guard_gate_to_execution_ready(self):
        """GUARD_GATE → EXECUTION_READY: PASS時に実行可能状態へ"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RACompletedEvent(
            run_id="run-001",
            payload={"outcome": "EXECUTION_READY"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.EXECUTION_READY


class TestRAStateMachineAlternativePaths:
    """RAStateMachine の代替パス（分岐遷移）テスト"""

    def test_guard_gate_to_execution_ready_with_risks(self):
        """GUARD_GATE → EXECUTION_READY_WITH_RISKS: LOW/MEDIUM残存時"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RACompletedEvent(
            run_id="run-001",
            payload={"outcome": "EXECUTION_READY_WITH_RISKS"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.EXECUTION_READY_WITH_RISKS

    def test_guard_gate_to_clarify_gen_on_fail(self):
        """GUARD_GATE → CLARIFY_GEN: FAIL時にループバック"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RAClarifyGeneratedEvent(
            run_id="run-001",
            payload={"questions": ["追加質問"], "round": 2},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.CLARIFY_GEN

    def test_guard_gate_to_abandoned(self):
        """GUARD_GATE → ABANDONED: FAIL + ループ上限 + HIGH未対処"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RACompletedEvent(
            run_id="run-001",
            payload={"outcome": "ABANDONED"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.ABANDONED

    def test_challenge_review_to_spec_synthesis_on_block(self):
        """CHALLENGE_REVIEW → SPEC_SYNTHESIS: BLOCK時に仕様修正差し戻し"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.CHALLENGE_REVIEW
        event = RASpecSynthesizedEvent(
            run_id="run-001",
            payload={"draft_id": "draft-001", "version": 2, "sub_type": "revision"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.SPEC_SYNTHESIS

    def test_user_feedback_to_hypothesis_build(self):
        """USER_FEEDBACK → HYPOTHESIS_BUILD: 追加仮説が必要な場合"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.USER_FEEDBACK
        event = RAHypothesisBuiltEvent(
            run_id="run-001",
            payload={"assumptions_count": 2, "failure_hypotheses_count": 1},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.HYPOTHESIS_BUILD

    def test_user_feedback_to_spec_synthesis(self):
        """USER_FEEDBACK → SPEC_SYNTHESIS: 仮説十分な場合"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.USER_FEEDBACK
        event = RASpecSynthesizedEvent(
            run_id="run-001",
            payload={"draft_id": "draft-001", "version": 1},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.SPEC_SYNTHESIS

    def test_user_feedback_to_abandoned(self):
        """USER_FEEDBACK → ABANDONED: ユーザーが放棄"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.USER_FEEDBACK
        event = RACompletedEvent(
            run_id="run-001",
            payload={"outcome": "ABANDONED"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.ABANDONED

    def test_clarify_gen_to_user_feedback(self):
        """CLARIFY_GEN → USER_FEEDBACK: 質問がある場合にユーザー待ち"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.CLARIFY_GEN
        event = RAUserRespondedEvent(
            run_id="run-001",
            payload={"answers": {"q1": "回答"}, "round": 1},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == RAState.USER_FEEDBACK


class TestRAStateMachineTerminalStates:
    """RAStateMachine の終端状態テスト — 遷移不可の検証"""

    def test_execution_ready_is_terminal(self):
        """EXECUTION_READY は終端状態 — いかなる遷移も不可"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.EXECUTION_READY
        event = RAIntakeReceivedEvent(run_id="run-001", payload={"raw_text": "テスト"})

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_execution_ready_with_risks_is_terminal(self):
        """EXECUTION_READY_WITH_RISKS は終端状態"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.EXECUTION_READY_WITH_RISKS
        event = RAIntakeReceivedEvent(run_id="run-001", payload={"raw_text": "テスト"})

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_abandoned_is_terminal(self):
        """ABANDONED は終端状態"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.ABANDONED
        event = RAIntakeReceivedEvent(run_id="run-001", payload={"raw_text": "テスト"})

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)


class TestRAStateMachineInvalidTransitions:
    """RAStateMachine の不正遷移テスト — 設計書で許可されていないパスの検証"""

    def test_intake_cannot_jump_to_spec_synthesis(self):
        """INTAKE → SPEC_SYNTHESIS: 途中ステップをスキップした遷移は不可"""
        # Arrange
        sm = RAStateMachine()
        event = RASpecSynthesizedEvent(
            run_id="run-001",
            payload={"draft_id": "draft-001", "version": 1},
        )

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_triage_cannot_go_to_clarify_gen(self):
        """TRIAGE → CLARIFY_GEN: 直接質問生成に飛ぶのは不可"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.TRIAGE
        event = RAClarifyGeneratedEvent(
            run_id="run-001",
            payload={"questions": ["質問"], "round": 1},
        )

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_hypothesis_build_cannot_jump_to_guard_gate(self):
        """HYPOTHESIS_BUILD → GUARD_GATE: ゲートに直接飛ぶのは不可"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.HYPOTHESIS_BUILD
        event = RAGateDecidedEvent(run_id="run-001", payload={"result": "PASS"})

        # Act & Assert
        with pytest.raises(TransitionError):
            sm.transition(event)

    def test_guard_gate_unknown_outcome_raises_error(self):
        """GUARD_GATE + RA_COMPLETED で不正な outcome を指定するとエラー

        payloadルーティングで EXECUTION_READY / EXECUTION_READY_WITH_RISKS /
        ABANDONED 以外の outcome は TransitionError を発生させる。
        """
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RACompletedEvent(
            run_id="run-001",
            payload={"outcome": "INVALID"},
        )

        # Act & Assert
        with pytest.raises(TransitionError, match="Unknown outcome 'INVALID'"):
            sm.transition(event)

    def test_guard_gate_empty_outcome_raises_error(self):
        """GUARD_GATE + RA_COMPLETED で outcome が未指定だとエラー"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE
        event = RACompletedEvent(
            run_id="run-001",
            payload={},
        )

        # Act & Assert
        with pytest.raises(TransitionError, match="Unknown outcome"):
            sm.transition(event)


class TestRAStateMachineGetValidEvents:
    """RAStateMachine の get_valid_events テスト"""

    def test_intake_valid_events(self):
        """INTAKE状態から遷移可能なイベントはRA_TRIAGE_COMPLETEDのみ"""
        # Arrange
        sm = RAStateMachine()

        # Act
        valid = sm.get_valid_events()

        # Assert
        assert EventType.RA_TRIAGE_COMPLETED in valid
        assert len(valid) == 1

    def test_guard_gate_valid_events(self):
        """GUARD_GATE状態からは3方向に遷移可能

        EXECUTION_READY, EXECUTION_READY_WITH_RISKS, CLARIFY_GEN, ABANDONED
        """
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE

        # Act
        valid = sm.get_valid_events()

        # Assert: RA_COMPLETED(→3終端) と RA_CLARIFY_GENERATED(→ループ)
        assert EventType.RA_COMPLETED in valid
        assert EventType.RA_CLARIFY_GENERATED in valid

    def test_terminal_state_no_valid_events(self):
        """終端状態からは遷移可能なイベントがない"""
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.EXECUTION_READY

        # Act
        valid = sm.get_valid_events()

        # Assert
        assert len(valid) == 0

    def test_guard_gate_can_transition_ra_completed(self):
        """GUARD_GATE状態でRA_COMPLETEDに遷移可能と判定される

        payloadルーティングのため can_transition をオーバーライドしている。
        """
        # Arrange
        sm = RAStateMachine()
        sm.current_state = RAState.GUARD_GATE

        # Act & Assert
        assert sm.can_transition(EventType.RA_COMPLETED) is True

    def test_intake_cannot_transition_ra_completed(self):
        """INTAKE状態ではRA_COMPLETEDに遷移不可"""
        # Arrange
        sm = RAStateMachine()

        # Act & Assert
        assert sm.can_transition(EventType.RA_COMPLETED) is False


class TestRAStateEnum:
    """RAState enum の基本テスト"""

    def test_all_states_exist(self):
        """設計書 §4.1 の全16状態が定義されている"""
        # Arrange: 期待される状態名
        expected = {
            "INTAKE",
            "TRIAGE",
            "CONTEXT_ENRICH",
            "WEB_RESEARCH",
            "HYPOTHESIS_BUILD",
            "CLARIFY_GEN",
            "USER_FEEDBACK",
            "SPEC_SYNTHESIS",
            "SPEC_PERSIST",
            "USER_EDIT",
            "CHALLENGE_REVIEW",
            "REFEREE_COMPARE",
            "GUARD_GATE",
            "EXECUTION_READY",
            "EXECUTION_READY_WITH_RISKS",
            "ABANDONED",
        }

        # Act: 実際の状態名を取得
        actual = {state.name for state in RAState}

        # Assert: 全状態が存在
        assert actual == expected

    def test_state_values_are_lowercase(self):
        """RAState の値はすべて小文字の snake_case"""
        # Arrange & Act
        for state in RAState:
            # Assert
            assert state.value == state.value.lower(), (
                f"{state.name} の値 '{state.value}' が小文字ではない"
            )
