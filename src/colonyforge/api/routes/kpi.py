"""KPI エンドポイント

KPIダッシュボード用のREST API。
Honeycomb KPICalculator を通じて基本KPI、協調メトリクス、
ゲート精度メトリクスを提供する。

M5-4: KPIダッシュボード（Hive Monitor統合）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ...core import get_settings
from ...core.honeycomb import HoneycombStore, KPICalculator

router = APIRouter(prefix="/kpi", tags=["KPI"])


def _get_calculator() -> KPICalculator:
    """KPICalculator を取得"""
    settings = get_settings()
    store = HoneycombStore(settings.get_vault_path())
    return KPICalculator(store)


@router.get("/scores")
async def get_kpi_scores(
    colony_id: str | None = Query(default=None, description="Colony ID（未指定時は全体）"),
) -> dict[str, Any]:
    """基本KPIスコアを取得

    5つのKPI指標を返す:
    - correctness: 正確性（一次合格率）
    - repeatability: 再現性
    - lead_time_seconds: リードタイム
    - incident_rate: インシデント率
    - recurrence_rate: 再発率
    """
    calc = _get_calculator()
    scores = calc.calculate_all(colony_id=colony_id)
    return {"kpi": scores.model_dump(mode="json")}


@router.get("/summary")
async def get_kpi_summary(
    colony_id: str | None = Query(default=None, description="Colony ID（未指定時は全体）"),
) -> dict[str, Any]:
    """KPIサマリーを取得

    基本KPIに加えてOutcome/FailureClass内訳を含む。
    """
    calc = _get_calculator()
    summary = calc.calculate_summary(colony_id=colony_id)
    return summary


@router.get("/collaboration")
async def get_collaboration_metrics(
    colony_id: str | None = Query(default=None, description="Colony ID（未指定時は全体）"),
    guard_reject_count: int = Query(default=0, ge=0, description="Guard Bee差戻し回数"),
    guard_total_count: int = Query(default=0, ge=0, description="Guard Bee検証総回数"),
    escalation_count: int = Query(default=0, ge=0, description="エスカレーション回数"),
    decision_count: int = Query(default=0, ge=0, description="意思決定回数"),
    referee_selected_count: int = Query(default=0, ge=0, description="Referee選抜数"),
    referee_candidate_count: int = Query(default=0, ge=0, description="Referee候補総数"),
) -> dict[str, Any]:
    """協調品質メトリクスを取得

    - rework_rate: 再作業率
    - escalation_ratio: エスカレーション率
    - n_proposal_yield: N案歩留まり
    - cost_per_task_tokens: タスク当たりトークン消費
    - collaboration_overhead: 協調オーバーヘッド
    """
    calc = _get_calculator()
    collab = calc.calculate_collaboration(
        colony_id=colony_id,
        guard_reject_count=guard_reject_count,
        guard_total_count=guard_total_count,
        escalation_count=escalation_count,
        decision_count=decision_count,
        referee_selected_count=referee_selected_count,
        referee_candidate_count=referee_candidate_count,
    )
    return {"collaboration": collab.model_dump(mode="json")}


@router.get("/gate-accuracy")
async def get_gate_accuracy(
    guard_pass_count: int = Query(default=0, ge=0, description="Guard Bee PASS数"),
    guard_conditional_count: int = Query(default=0, ge=0, description="Guard Bee CONDITIONAL数"),
    guard_fail_count: int = Query(default=0, ge=0, description="Guard Bee FAIL数"),
    sentinel_alert_count: int = Query(default=0, ge=0, description="Sentinel alert数"),
    sentinel_false_alarm_count: int = Query(default=0, ge=0, description="Sentinel 誤検知数"),
    total_monitoring_periods: int = Query(default=0, ge=0, description="監視期間数"),
) -> dict[str, Any]:
    """ゲート精度メトリクスを取得

    - guard_pass_rate / conditional_pass_rate / fail_rate
    - sentinel_detection_rate / false_alarm_rate
    """
    calc = _get_calculator()
    gate = calc.calculate_gate_accuracy(
        guard_pass_count=guard_pass_count,
        guard_conditional_count=guard_conditional_count,
        guard_fail_count=guard_fail_count,
        sentinel_alert_count=sentinel_alert_count,
        sentinel_false_alarm_count=sentinel_false_alarm_count,
        total_monitoring_periods=total_monitoring_periods,
    )
    return {"gate_accuracy": gate.model_dump(mode="json")}


@router.get("/evaluation")
async def get_evaluation_summary(
    colony_id: str | None = Query(default=None, description="Colony ID（未指定時は全体）"),
    guard_pass_count: int = Query(default=0, ge=0),
    guard_conditional_count: int = Query(default=0, ge=0),
    guard_fail_count: int = Query(default=0, ge=0),
    guard_reject_count: int = Query(default=0, ge=0),
    guard_total_count: int = Query(default=0, ge=0),
    escalation_count: int = Query(default=0, ge=0),
    decision_count: int = Query(default=0, ge=0),
    referee_selected_count: int = Query(default=0, ge=0),
    referee_candidate_count: int = Query(default=0, ge=0),
    sentinel_alert_count: int = Query(default=0, ge=0),
    sentinel_false_alarm_count: int = Query(default=0, ge=0),
    total_monitoring_periods: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """包括的評価サマリーを取得

    基本KPI + 協調品質 + ゲート精度を統合した
    KPIダッシュボード用データ。
    """
    calc = _get_calculator()
    summary = calc.calculate_evaluation(
        colony_id=colony_id,
        guard_pass_count=guard_pass_count,
        guard_conditional_count=guard_conditional_count,
        guard_fail_count=guard_fail_count,
        guard_reject_count=guard_reject_count,
        guard_total_count=guard_total_count,
        escalation_count=escalation_count,
        decision_count=decision_count,
        referee_selected_count=referee_selected_count,
        referee_candidate_count=referee_candidate_count,
        sentinel_alert_count=sentinel_alert_count,
        sentinel_false_alarm_count=sentinel_false_alarm_count,
        total_monitoring_periods=total_monitoring_periods,
    )
    return summary.model_dump(mode="json")


@router.get("/colonies")
async def get_kpi_colonies() -> dict[str, Any]:
    """KPIデータが存在するColony一覧を取得"""
    calc = _get_calculator()
    colonies = calc.store.list_colonies()
    return {"colonies": colonies, "count": len(colonies)}
