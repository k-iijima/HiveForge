"""Conferenceモード

複数Colony間での合意形成会議機能。
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ulid import ULID


class ConferenceStatus(StrEnum):
    """会議ステータス"""

    PENDING = "pending"  # 開始待ち
    IN_PROGRESS = "in_progress"  # 進行中
    VOTING = "voting"  # 投票中
    CONCLUDED = "concluded"  # 結論済み
    CANCELLED = "cancelled"  # キャンセル


class VoteType(StrEnum):
    """投票タイプ"""

    APPROVE = "approve"  # 賛成
    REJECT = "reject"  # 反対
    ABSTAIN = "abstain"  # 棄権


@dataclass
class Opinion:
    """意見"""

    opinion_id: str = field(default_factory=lambda: str(ULID()))
    colony_id: str = ""
    content: str = ""
    rationale: str = ""  # 理由
    submitted_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Vote:
    """投票"""

    vote_id: str = field(default_factory=lambda: str(ULID()))
    colony_id: str = ""
    vote_type: VoteType = VoteType.ABSTAIN
    comment: str = ""
    voted_at: datetime = field(default_factory=datetime.now)


@dataclass
class ConferenceAgenda:
    """会議アジェンダ"""

    agenda_id: str = field(default_factory=lambda: str(ULID()))
    title: str = ""
    description: str = ""
    options: list[str] = field(default_factory=list)  # 選択肢
    requires_consensus: bool = False  # 全員一致必要か
    min_votes: int = 1  # 最低投票数


@dataclass
class ConferenceSession:
    """会議セッション"""

    session_id: str = field(default_factory=lambda: str(ULID()))
    hive_id: str = ""
    topic: str = ""
    agenda: ConferenceAgenda | None = None
    status: ConferenceStatus = ConferenceStatus.PENDING
    participants: list[str] = field(default_factory=list)  # colony_ids
    opinions: list[Opinion] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    conclusion: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """進行中か"""
        return self.status in (
            ConferenceStatus.IN_PROGRESS,
            ConferenceStatus.VOTING,
        )


class ConferenceManager:
    """会議管理

    Conferenceセッションのライフサイクルを管理。
    """

    def __init__(self):
        self._sessions: dict[str, ConferenceSession] = {}
        self._on_started: list[Callable[[ConferenceSession], None]] = []
        self._on_concluded: list[Callable[[ConferenceSession], None]] = []

    def add_listener(
        self,
        on_started: Callable[[ConferenceSession], None] | None = None,
        on_concluded: Callable[[ConferenceSession], None] | None = None,
    ) -> None:
        """リスナー追加"""
        if on_started:
            self._on_started.append(on_started)
        if on_concluded:
            self._on_concluded.append(on_concluded)

    def create_session(
        self,
        hive_id: str,
        topic: str,
        participants: list[str],
        agenda: ConferenceAgenda | None = None,
    ) -> ConferenceSession:
        """会議セッション作成"""
        session = ConferenceSession(
            hive_id=hive_id,
            topic=topic,
            participants=participants,
            agenda=agenda,
        )
        self._sessions[session.session_id] = session
        return session

    def start_session(self, session_id: str) -> bool:
        """会議開始"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status != ConferenceStatus.PENDING:
            return False

        session.status = ConferenceStatus.IN_PROGRESS
        session.started_at = datetime.now()

        for listener in self._on_started:
            with contextlib.suppress(Exception):
                listener(session)

        return True

    def submit_opinion(
        self,
        session_id: str,
        colony_id: str,
        content: str,
        rationale: str = "",
    ) -> Opinion | None:
        """意見を提出"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        if not session.is_active():
            return None

        if colony_id not in session.participants:
            return None

        opinion = Opinion(
            colony_id=colony_id,
            content=content,
            rationale=rationale,
        )
        session.opinions.append(opinion)

        return opinion

    def start_voting(self, session_id: str) -> bool:
        """投票開始"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status != ConferenceStatus.IN_PROGRESS:
            return False

        session.status = ConferenceStatus.VOTING
        return True

    def cast_vote(
        self,
        session_id: str,
        colony_id: str,
        vote_type: VoteType,
        comment: str = "",
    ) -> Vote | None:
        """投票"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        if session.status != ConferenceStatus.VOTING:
            return None

        if colony_id not in session.participants:
            return None

        # 既に投票していたら上書き
        session.votes = [v for v in session.votes if v.colony_id != colony_id]

        vote = Vote(
            colony_id=colony_id,
            vote_type=vote_type,
            comment=comment,
        )
        session.votes.append(vote)

        return vote

    def conclude_session(
        self,
        session_id: str,
        conclusion: str = "",
    ) -> bool:
        """会議を結論づける"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if not session.is_active():
            return False

        # 投票結果を集計
        if not conclusion:
            conclusion = self._summarize_votes(session)

        session.conclusion = conclusion
        session.status = ConferenceStatus.CONCLUDED
        session.ended_at = datetime.now()

        for listener in self._on_concluded:
            with contextlib.suppress(Exception):
                listener(session)

        return True

    def cancel_session(self, session_id: str, reason: str = "") -> bool:
        """会議をキャンセル"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.status == ConferenceStatus.CONCLUDED:
            return False

        session.status = ConferenceStatus.CANCELLED
        session.ended_at = datetime.now()
        session.metadata["cancel_reason"] = reason

        return True

    def _summarize_votes(self, session: ConferenceSession) -> str:
        """投票結果を要約"""
        approve = len([v for v in session.votes if v.vote_type == VoteType.APPROVE])
        reject = len([v for v in session.votes if v.vote_type == VoteType.REJECT])
        abstain = len([v for v in session.votes if v.vote_type == VoteType.ABSTAIN])

        total = len(session.participants)

        if session.agenda and session.agenda.requires_consensus:
            if approve == total:
                return "Consensus reached: Approved"
            elif reject > 0:
                return f"No consensus: {reject} rejections"
            else:
                return f"No consensus: {abstain} abstentions"

        if approve > reject:
            return f"Approved ({approve}/{total})"
        elif reject > approve:
            return f"Rejected ({reject}/{total})"
        else:
            return f"Tied ({approve}/{total})"

    def get_session(self, session_id: str) -> ConferenceSession | None:
        """セッション取得"""
        return self._sessions.get(session_id)

    def get_active_sessions(self) -> list[ConferenceSession]:
        """進行中セッション一覧"""
        return [s for s in self._sessions.values() if s.is_active()]

    def get_sessions_by_hive(self, hive_id: str) -> list[ConferenceSession]:
        """Hive別セッション一覧"""
        return [s for s in self._sessions.values() if s.hive_id == hive_id]

    def get_vote_summary(self, session_id: str) -> dict[str, int]:
        """投票サマリ"""
        session = self._sessions.get(session_id)
        if not session:
            return {}

        return {
            "approve": len([v for v in session.votes if v.vote_type == VoteType.APPROVE]),
            "reject": len([v for v in session.votes if v.vote_type == VoteType.REJECT]),
            "abstain": len([v for v in session.votes if v.vote_type == VoteType.ABSTAIN]),
            "pending": len(session.participants) - len(session.votes),
        }

    def get_stats(self) -> dict[str, Any]:
        """統計情報"""
        sessions = list(self._sessions.values())
        return {
            "total": len(sessions),
            "active": len([s for s in sessions if s.is_active()]),
            "concluded": len([s for s in sessions if s.status == ConferenceStatus.CONCLUDED]),
            "cancelled": len([s for s in sessions if s.status == ConferenceStatus.CANCELLED]),
        }
