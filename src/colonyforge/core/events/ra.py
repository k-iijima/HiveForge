"""Requirement Analysis Colony — イベントクラス.

RA Colony Phase 1 の10種 + RA_REQ_CHANGED(§11.3) のイベントクラス定義。
設計書 §6.1 に対応。
"""

from __future__ import annotations

from typing import Literal

from .base import BaseEvent
from .types import EventType


class RAIntakeReceivedEvent(BaseEvent):
    """RA受領イベント — 生テキスト受領"""

    type: Literal[EventType.RA_INTAKE_RECEIVED] = EventType.RA_INTAKE_RECEIVED


class RATriageCompletedEvent(BaseEvent):
    """RAトリアージ完了イベント — Goal/制約/不明点に分解"""

    type: Literal[EventType.RA_TRIAGE_COMPLETED] = EventType.RA_TRIAGE_COMPLETED


class RAContextEnrichedEvent(BaseEvent):
    """RAコンテキスト収集完了イベント — 内部+外部証拠収集"""

    type: Literal[EventType.RA_CONTEXT_ENRICHED] = EventType.RA_CONTEXT_ENRICHED


class RAHypothesisBuiltEvent(BaseEvent):
    """RA仮説構築完了イベント — Risk Challenger Phase A 含む"""

    type: Literal[EventType.RA_HYPOTHESIS_BUILT] = EventType.RA_HYPOTHESIS_BUILT


class RAClarifyGeneratedEvent(BaseEvent):
    """RA質問生成イベント"""

    type: Literal[EventType.RA_CLARIFY_GENERATED] = EventType.RA_CLARIFY_GENERATED


class RAUserRespondedEvent(BaseEvent):
    """RAユーザー回答イベント"""

    type: Literal[EventType.RA_USER_RESPONDED] = EventType.RA_USER_RESPONDED


class RASpecSynthesizedEvent(BaseEvent):
    """RA仕様草案生成イベント — doorstop永続化+編集完了もpayloadで表現"""

    type: Literal[EventType.RA_SPEC_SYNTHESIZED] = EventType.RA_SPEC_SYNTHESIZED


class RAChallengeReviewedEvent(BaseEvent):
    """RA Risk Challenger検証完了イベント — BLOCK/PASSもpayloadで区別"""

    type: Literal[EventType.RA_CHALLENGE_REVIEWED] = EventType.RA_CHALLENGE_REVIEWED


class RAGateDecidedEvent(BaseEvent):
    """RA Guard Gate判定イベント — PASS/FAILをpayloadで区別"""

    type: Literal[EventType.RA_GATE_DECIDED] = EventType.RA_GATE_DECIDED


class RACompletedEvent(BaseEvent):
    """RA終端イベント — EXECUTION_READY / EXECUTION_READY_WITH_RISKS / ABANDONED"""

    type: Literal[EventType.RA_COMPLETED] = EventType.RA_COMPLETED


class RAReqChangedEvent(BaseEvent):
    """要件変更イベント — §11.3 要件版管理の基盤イベント

    Phase 2 だが Phase 1 と同時に導入。因果リンク付きで
    変更理由(cause)、版番号(prev_version/new_version)、差分(diff)を記録。
    """

    type: Literal[EventType.RA_REQ_CHANGED] = EventType.RA_REQ_CHANGED
