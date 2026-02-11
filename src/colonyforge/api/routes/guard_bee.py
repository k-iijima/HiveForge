"""Guard Bee APIエンドポイント

品質検証エンジンのREST API。
POST /guard-bee/verify: 証拠を受け取り検証を実行
GET /guard-bee/reports/{run_id}: 検証レポート一覧を取得
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...core.events import EventType
from ...guard_bee import Evidence, EvidenceType, GuardBeeVerifier
from ..helpers import get_active_runs, get_ar

router = APIRouter(prefix="/guard-bee", tags=["Guard Bee"])


# --- リクエスト/レスポンスモデル ---


class EvidenceRequest(BaseModel):
    """証拠リクエスト"""

    evidence_type: EvidenceType = Field(..., description="証拠の種類")
    source: str = Field(..., description="証拠の出所")
    content: dict[str, Any] = Field(default_factory=dict, description="証拠データ")


class VerifyRequest(BaseModel):
    """検証リクエスト"""

    colony_id: str = Field(..., description="検証対象Colony ID")
    task_id: str = Field(..., description="検証対象Task ID")
    run_id: str = Field(..., description="Run ID")
    evidence: list[EvidenceRequest] = Field(default_factory=list, description="証拠リスト")
    context: dict[str, Any] = Field(default_factory=dict, description="追加コンテキスト")


class RuleResultResponse(BaseModel):
    """ルール結果レスポンス"""

    rule_name: str
    level: str
    passed: bool
    message: str
    evidence_type: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class VerifyResponse(BaseModel):
    """検証レスポンス"""

    colony_id: str
    task_id: str
    run_id: str
    verdict: str
    rule_results: list[RuleResultResponse]
    evidence_count: int
    l1_passed: bool
    l2_passed: bool
    remand_reason: str | None = None
    improvement_instructions: list[str] = Field(default_factory=list)
    verified_at: datetime


class ReportSummary(BaseModel):
    """レポートサマリー（一覧用）"""

    colony_id: str
    task_id: str
    verdict: str
    l1_passed: bool
    l2_passed: bool
    evidence_count: int
    rules_total: int
    rules_passed: int
    remand_reason: str | None = None
    improvement_instructions: list[str] = Field(default_factory=list)


# --- エンドポイント ---


@router.post("/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest) -> VerifyResponse:
    """Guard Bee検証を実行

    証拠リストを受け取り、L1/L2の検証を実行して結果を返す。
    検証イベントはARに記録される。
    """
    ar = get_ar()
    active_runs = get_active_runs()

    # Runの存在確認
    if request.run_id not in active_runs and request.run_id not in ar.list_runs():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{request.run_id}' が見つかりません",
        )

    # Evidence変換
    evidence_list = [
        Evidence(
            evidence_type=e.evidence_type,
            source=e.source,
            content=e.content,
        )
        for e in request.evidence
    ]

    # 検証実行
    verifier = GuardBeeVerifier(ar=ar)
    report = verifier.verify(
        colony_id=request.colony_id,
        task_id=request.task_id,
        run_id=request.run_id,
        evidence=evidence_list,
        context=request.context if request.context else None,
    )

    # レスポンス変換
    return VerifyResponse(
        colony_id=report.colony_id,
        task_id=report.task_id,
        run_id=report.run_id,
        verdict=report.verdict.value,
        rule_results=[
            RuleResultResponse(
                rule_name=r.rule_name,
                level=r.level.value,
                passed=r.passed,
                message=r.message,
                evidence_type=r.evidence_type.value if r.evidence_type else None,
                details=r.details,
            )
            for r in report.rule_results
        ],
        evidence_count=report.evidence_count,
        l1_passed=report.l1_passed,
        l2_passed=report.l2_passed,
        remand_reason=report.remand_reason,
        improvement_instructions=list(report.improvement_instructions),
        verified_at=report.verified_at,
    )


# Guard Bee関連イベントタイプ
_GUARD_EVENT_TYPES = {
    EventType.GUARD_PASSED,
    EventType.GUARD_CONDITIONAL_PASSED,
    EventType.GUARD_FAILED,
}


@router.get("/reports/{run_id}", response_model=list[ReportSummary])
async def get_reports(run_id: str) -> list[ReportSummary]:
    """Run配下の検証レポート一覧を取得

    ARのイベントから guard.passed / guard.conditional_passed / guard.failed
    イベントを抽出してレポートサマリーを返す。
    """
    ar = get_ar()
    active_runs = get_active_runs()

    # Runの存在確認
    if run_id not in active_runs and run_id not in ar.list_runs():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' が見つかりません",
        )

    # ARから検証イベントを抽出
    reports: list[ReportSummary] = []
    for event in ar.replay(run_id):
        if event.type in _GUARD_EVENT_TYPES:
            payload = event.payload
            reports.append(
                ReportSummary(
                    colony_id=payload.get("colony_id", ""),
                    task_id=payload.get("task_id", ""),
                    verdict=payload.get("verdict", ""),
                    l1_passed=payload.get("l1_passed", False),
                    l2_passed=payload.get("l2_passed", False),
                    evidence_count=payload.get("evidence_count", 0),
                    rules_total=payload.get("rules_total", 0),
                    rules_passed=payload.get("rules_passed", 0),
                    remand_reason=payload.get("remand_reason"),
                    improvement_instructions=payload.get("improvement_instructions", []),
                )
            )

    return reports
