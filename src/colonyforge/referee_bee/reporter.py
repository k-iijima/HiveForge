"""Referee Bee: Guard Bee連携レポーター

RefereeReportを生成し、Guard Bee用Evidence形式に変換する。
"""

from __future__ import annotations

from typing import Any

from .models import CandidateScore, RefereeReport, RefereeVerdict
from .tournament import Tournament


class RefereeReporter:
    """Guard Bee連携レポーター"""

    def create_report(
        self,
        run_id: str,
        colony_id: str,
        scores: list[CandidateScore],
        k: int = 1,
    ) -> RefereeReport:
        """CandidateScoreからRefereeReportを生成"""
        if not scores:
            return RefereeReport(
                run_id=run_id,
                colony_id=colony_id,
                candidate_count=0,
                selected_ids=[],
                scores=[],
                verdict=RefereeVerdict.NO_CANDIDATE,
            )

        if len(scores) == 1:
            return RefereeReport(
                run_id=run_id,
                colony_id=colony_id,
                candidate_count=1,
                selected_ids=[scores[0].candidate_id],
                scores=scores,
                verdict=RefereeVerdict.SINGLE_PASS,
            )

        # トーナメント実行
        tournament = Tournament(k=k)
        result = tournament.select(scores)

        return RefereeReport(
            run_id=run_id,
            colony_id=colony_id,
            candidate_count=len(scores),
            selected_ids=result.selected_ids,
            scores=result.rankings,
            verdict=RefereeVerdict.SELECTED,
        )

    def to_guard_bee_evidence(self, report: RefereeReport) -> dict[str, Any]:
        """Guard Bee用Evidence形式に変換"""
        top_score = 0.0
        if report.scores:
            top_score = max(s.final_score() for s in report.scores)

        return {
            "evidence_type": "referee_report",
            "verdict": report.verdict.value,
            "candidate_count": report.candidate_count,
            "selected_ids": report.selected_ids,
            "top_score": round(top_score, 4),
        }
