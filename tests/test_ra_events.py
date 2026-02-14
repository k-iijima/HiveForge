"""Requirement Analysis Colony — イベントのテスト.

RA Colony Phase 1 の10種 + RA_REQ_CHANGED の EventType と
対応するイベントクラスの検証。設計書 §6.1 に対応。
"""

import pytest

from colonyforge.core.events import EventType, parse_event
from colonyforge.core.events.ra import (
    RAChallengeReviewedEvent,
    RAClarifyGeneratedEvent,
    RACompletedEvent,
    RAContextEnrichedEvent,
    RAGateDecidedEvent,
    RAHypothesisBuiltEvent,
    RAIntakeReceivedEvent,
    RAReqChangedEvent,
    RASpecSynthesizedEvent,
    RATriageCompletedEvent,
    RAUserRespondedEvent,
)
from colonyforge.core.events.registry import EVENT_TYPE_MAP


class TestRAEventTypes:
    """RA Colony EventType enum値の存在確認"""

    @pytest.mark.parametrize(
        ("member", "value"),
        [
            ("RA_INTAKE_RECEIVED", "ra.intake.received"),
            ("RA_TRIAGE_COMPLETED", "ra.triage.completed"),
            ("RA_CONTEXT_ENRICHED", "ra.context.enriched"),
            ("RA_HYPOTHESIS_BUILT", "ra.hypothesis.built"),
            ("RA_CLARIFY_GENERATED", "ra.clarify.generated"),
            ("RA_USER_RESPONDED", "ra.user.responded"),
            ("RA_SPEC_SYNTHESIZED", "ra.spec.synthesized"),
            ("RA_CHALLENGE_REVIEWED", "ra.challenge.reviewed"),
            ("RA_GATE_DECIDED", "ra.gate.decided"),
            ("RA_COMPLETED", "ra.completed"),
            ("RA_REQ_CHANGED", "ra.req.changed"),
        ],
    )
    def test_event_type_exists_with_correct_value(self, member: str, value: str):
        """各RA EventTypeが正しい文字列値を持つ

        設計書 §6.1 で定義された命名規則 ra.category.action に従う。
        """
        # Arrange: なし（EventType enum定義の検証）

        # Act: enum名でアクセス
        event_type = EventType[member]

        # Assert: 値が設計書どおり
        assert event_type.value == value

    def test_ra_event_types_count(self):
        """Phase 1 の10種 + RA_REQ_CHANGED = 11種のRAイベントが存在する"""
        # Arrange: RA関連のEventTypeを収集
        ra_types = [et for et in EventType if et.value.startswith("ra.")]

        # Act & Assert: 11種
        assert len(ra_types) == 11


class TestRAEventClasses:
    """RA Colony イベントクラスの基本動作テスト"""

    def test_intake_received_event_creation(self):
        """RAIntakeReceivedEvent — 生テキスト受領イベントを生成できる

        payloadに元のユーザー入力テキストを含む。
        """
        # Arrange: ユーザーからの生テキスト
        payload = {"raw_text": "ログイン機能を作って", "colony_id": "ra-001"}

        # Act: イベント生成
        event = RAIntakeReceivedEvent(run_id="run-001", payload=payload)

        # Assert: type値とpayloadが正しい
        assert event.type == EventType.RA_INTAKE_RECEIVED
        assert event.payload["raw_text"] == "ログイン機能を作って"
        assert event.run_id == "run-001"

    def test_triage_completed_event_creation(self):
        """RATriageCompletedEvent — 分解完了イベントを生成できる"""
        # Arrange
        payload = {"goal": "ユーザー認証", "unknowns_count": 3}

        # Act
        event = RATriageCompletedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_TRIAGE_COMPLETED

    def test_context_enriched_event_creation(self):
        """RAContextEnrichedEvent — 証拠収集完了イベントを生成できる

        sub_typeでWEB検索実行/スキップを区別する。
        """
        # Arrange: WEB検索スキップの場合
        payload = {"evidence_count": 5, "sub_type": "internal_only"}

        # Act
        event = RAContextEnrichedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_CONTEXT_ENRICHED
        assert event.payload["sub_type"] == "internal_only"

    def test_hypothesis_built_event_creation(self):
        """RAHypothesisBuiltEvent — 仮説構築完了イベントを生成できる"""
        # Arrange
        payload = {"assumptions_count": 5, "failure_hypotheses_count": 3}

        # Act
        event = RAHypothesisBuiltEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_HYPOTHESIS_BUILT

    def test_clarify_generated_event_creation(self):
        """RAClarifyGeneratedEvent — 質問生成イベントを生成できる"""
        # Arrange
        payload = {"questions": ["OAuth対応は必要ですか？", "2FAは必要ですか？"], "round": 1}

        # Act
        event = RAClarifyGeneratedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_CLARIFY_GENERATED
        assert len(event.payload["questions"]) == 2

    def test_user_responded_event_creation(self):
        """RAUserRespondedEvent — ユーザー回答イベントを生成できる"""
        # Arrange
        payload = {"answers": {"q1": "OAuth不要", "q2": "2FAも不要"}, "round": 1}

        # Act
        event = RAUserRespondedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_USER_RESPONDED

    def test_spec_synthesized_event_creation(self):
        """RASpecSynthesizedEvent — 仕様草案生成イベントを生成できる"""
        # Arrange
        payload = {"draft_id": "draft-001", "version": 1, "sub_type": "synthesized"}

        # Act
        event = RASpecSynthesizedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_SPEC_SYNTHESIZED
        assert event.payload["draft_id"] == "draft-001"

    def test_challenge_reviewed_event_creation(self):
        """RAChallengeReviewedEvent — Risk Challenger検証完了イベントを生成できる

        verdict (BLOCK/PASS_WITH_RISKS/REVIEW_REQUIRED) をpayloadに含む。
        """
        # Arrange
        payload = {
            "verdict": "BLOCK",
            "challenges_count": 2,
            "high_severity_count": 1,
        }

        # Act
        event = RAChallengeReviewedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_CHALLENGE_REVIEWED
        assert event.payload["verdict"] == "BLOCK"

    def test_gate_decided_event_creation(self):
        """RAGateDecidedEvent — Guard Gate判定イベントを生成できる"""
        # Arrange
        payload = {"result": "PASS", "remaining_risks": []}

        # Act
        event = RAGateDecidedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_GATE_DECIDED

    def test_completed_event_creation(self):
        """RACompletedEvent — 終端イベントを生成できる

        outcome で EXECUTION_READY / EXECUTION_READY_WITH_RISKS / ABANDONED を区別。
        """
        # Arrange
        payload = {"outcome": "EXECUTION_READY", "draft_id": "draft-001"}

        # Act
        event = RACompletedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_COMPLETED
        assert event.payload["outcome"] == "EXECUTION_READY"

    def test_req_changed_event_creation(self):
        """RAReqChangedEvent — 要件変更イベントを生成できる

        §11.3 要件版管理の基盤イベント。Phase 2だがPhase 1と同時に導入。
        """
        # Arrange
        payload = {
            "requirement_id": "REQ001",
            "cause": "CLARIFICATION",
            "prev_version": 1,
            "new_version": 2,
            "diff": [{"field": "text", "old": "旧テキスト", "new": "新テキスト"}],
        }

        # Act
        event = RAReqChangedEvent(run_id="run-001", payload=payload)

        # Assert
        assert event.type == EventType.RA_REQ_CHANGED
        assert event.payload["cause"] == "CLARIFICATION"
        assert event.payload["prev_version"] == 1


class TestRAEventRegistry:
    """RA イベントがレジストリに登録されている"""

    @pytest.mark.parametrize(
        ("event_type", "event_class"),
        [
            (EventType.RA_INTAKE_RECEIVED, RAIntakeReceivedEvent),
            (EventType.RA_TRIAGE_COMPLETED, RATriageCompletedEvent),
            (EventType.RA_CONTEXT_ENRICHED, RAContextEnrichedEvent),
            (EventType.RA_HYPOTHESIS_BUILT, RAHypothesisBuiltEvent),
            (EventType.RA_CLARIFY_GENERATED, RAClarifyGeneratedEvent),
            (EventType.RA_USER_RESPONDED, RAUserRespondedEvent),
            (EventType.RA_SPEC_SYNTHESIZED, RASpecSynthesizedEvent),
            (EventType.RA_CHALLENGE_REVIEWED, RAChallengeReviewedEvent),
            (EventType.RA_GATE_DECIDED, RAGateDecidedEvent),
            (EventType.RA_COMPLETED, RACompletedEvent),
            (EventType.RA_REQ_CHANGED, RAReqChangedEvent),
        ],
    )
    def test_event_type_mapped_to_class(self, event_type: EventType, event_class: type):
        """各RA EventTypeが対応するイベントクラスにマッピングされている"""
        # Arrange: なし

        # Act: レジストリからクラスを取得
        mapped_class = EVENT_TYPE_MAP.get(event_type)

        # Assert: 正しいクラスにマッピング
        assert mapped_class is event_class

    def test_parse_ra_intake_event_from_dict(self):
        """parse_event() でRA イベントをdictからパースできる"""
        # Arrange: RAIntakeReceivedEvent のdictデータ
        data = {
            "type": "ra.intake.received",
            "id": "test-id",
            "actor": "beekeeper",
            "run_id": "run-001",
            "payload": {"raw_text": "ログイン機能"},
        }

        # Act: パース
        event = parse_event(data)

        # Assert: 正しいクラスでパースされる
        assert isinstance(event, RAIntakeReceivedEvent)
        assert event.type == EventType.RA_INTAKE_RECEIVED
        assert event.payload["raw_text"] == "ログイン機能"

    def test_parse_ra_req_changed_event_from_dict(self):
        """parse_event() でRA_REQ_CHANGEDイベントをdictからパースできる"""
        # Arrange
        data = {
            "type": "ra.req.changed",
            "id": "test-id",
            "actor": "spec_persister",
            "run_id": "run-001",
            "payload": {
                "requirement_id": "REQ001",
                "cause": "USER_EDIT",
                "prev_version": 1,
                "new_version": 2,
            },
        }

        # Act
        event = parse_event(data)

        # Assert
        assert isinstance(event, RAReqChangedEvent)
        assert event.payload["cause"] == "USER_EDIT"


class TestRAEventHashIntegrity:
    """RA イベントのハッシュ整合性テスト"""

    def test_ra_event_has_valid_hash(self):
        """RAイベントが他イベントと同様にSHA-256ハッシュを持つ"""
        # Arrange & Act
        event = RAIntakeReceivedEvent(
            run_id="run-001",
            payload={"raw_text": "テスト入力"},
        )

        # Assert: ハッシュが生成されている
        assert event.hash is not None
        assert len(event.hash) == 64  # SHA-256 の16進文字列長

    def test_ra_event_prev_hash_chain(self):
        """RAイベントがprev_hashでチェーンを形成できる"""
        # Arrange: 最初のイベント
        event1 = RAIntakeReceivedEvent(
            run_id="run-001",
            payload={"raw_text": "テスト"},
        )

        # Act: 2番目のイベントをチェーン
        event2 = RATriageCompletedEvent(
            run_id="run-001",
            prev_hash=event1.hash,
            payload={"goal": "ゴール"},
        )

        # Assert: チェーンが正しい
        assert event2.prev_hash == event1.hash
        assert event2.hash != event1.hash
