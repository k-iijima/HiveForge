"""KPI エンドポイント

KPIダッシュボード用のREST API。
Honeycomb KPICalculator を通じて基本KPI、協調メトリクス、
ゲート精度メトリクスを提供する。

M5-4: KPIダッシュボード（Hive Monitor統合）
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ...core import get_settings
from ...core.ar import AkashicRecord
from ...core.honeycomb import HoneycombStore, KPICalculator
from ...core.honeycomb.event_counters import count_events

router = APIRouter(prefix="/kpi", tags=["KPI"])


class CountMode(StrEnum):
    """カウンタ集計モード"""

    AUTO = "auto"  # ARイベントからのみ集計（手動カウンタ無視）
    MANUAL = "manual"  # 入力値をそのまま使用
    MIXED = "mixed"  # 手動値を優先し、Noneの項目だけ自動補完


def _get_calculator() -> KPICalculator:
    """KPICalculator を取得"""
    settings = get_settings()
    store = HoneycombStore(settings.get_vault_path())
    return KPICalculator(store)


def _get_ar() -> AkashicRecord:
    """AkashicRecord を取得"""
    settings = get_settings()
    return AkashicRecord(settings.get_vault_path())


@router.get("/event-counters")
async def get_event_counters(
    run_id: str | None = Query(default=None, description="Run ID"),
    colony_id: str | None = Query(default=None, description="Colony ID"),
    from_ts: datetime | None = Query(default=None, description="集計開始日時 (inclusive)"),
    to_ts: datetime | None = Query(default=None, description="集計終了日時 (exclusive)"),
) -> dict[str, int]:
    """ARイベントから品質ゲートカウンターを自動集計

    集計スコープ:
        1. run_id 指定時: 当該 Run のイベントのみ
        2. colony_id + 期間: 当該 Colony の期間内
        3. colony_id のみ: 全期間
        4. 全未指定: 400 Bad Request
    """
    if not run_id and not colony_id:
        raise HTTPException(
            status_code=400,
            detail="Scope required: specify at least run_id or colony_id.",
        )
    ar = _get_ar()
    return count_events(ar, run_id=run_id, colony_id=colony_id, from_ts=from_ts, to_ts=to_ts)


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
    run_id: str | None = Query(default=None, description="Run ID（自動集計のスコープ用）"),
    count_mode: CountMode = Query(default=CountMode.AUTO, description="カウンタ集計モード"),
    guard_pass_count: int | None = Query(default=None, ge=0),
    guard_conditional_count: int | None = Query(default=None, ge=0),
    guard_fail_count: int | None = Query(default=None, ge=0),
    guard_reject_count: int | None = Query(default=None, ge=0),
    guard_total_count: int | None = Query(default=None, ge=0),
    escalation_count: int | None = Query(default=None, ge=0),
    decision_count: int | None = Query(default=None, ge=0),
    referee_selected_count: int | None = Query(default=None, ge=0),
    referee_candidate_count: int | None = Query(default=None, ge=0),
    sentinel_alert_count: int | None = Query(default=None, ge=0),
    sentinel_false_alarm_count: int | None = Query(default=None, ge=0),
    total_monitoring_periods: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """包括的評価サマリーを取得

    基本KPI + 協調品質 + ゲート精度を統合した
    KPIダッシュボード用データ。

    count_mode:
        auto (default): ARイベントから自動集計。手動パラメータ無視。
        manual: 入力値をそのまま使用。Noneは0扱い。
        mixed: 手動値を優先し、Noneの項目だけ自動補完。
    """
    # カウンタ名 → ローカル変数のマッピング
    manual_counters = {
        "guard_pass_count": guard_pass_count,
        "guard_conditional_count": guard_conditional_count,
        "guard_fail_count": guard_fail_count,
        "guard_reject_count": guard_reject_count,
        "guard_total_count": guard_total_count,
        "escalation_count": escalation_count,
        "decision_count": decision_count,
        "referee_selected_count": referee_selected_count,
        "referee_candidate_count": referee_candidate_count,
        "sentinel_alert_count": sentinel_alert_count,
        "sentinel_false_alarm_count": sentinel_false_alarm_count,
        "total_monitoring_periods": total_monitoring_periods,
    }

    if count_mode in (CountMode.AUTO, CountMode.MIXED) and not run_id and not colony_id:
        raise HTTPException(
            status_code=400,
            detail="Scope required: specify run_id or colony_id for auto/mixed counting.",
        )

    resolved: dict[str, int] = {}

    if count_mode == CountMode.AUTO:
        # ARイベントから完全自動集計
        ar = _get_ar()
        resolved = count_events(ar, run_id=run_id, colony_id=colony_id)
    elif count_mode == CountMode.MIXED:
        # 手動値を優先し、Noneの項目だけ自動補完
        ar = _get_ar()
        auto = count_events(ar, run_id=run_id, colony_id=colony_id)
        for k in auto:
            mv = manual_counters[k]
            resolved[k] = mv if mv is not None else auto[k]
    else:
        # MANUAL: 入力値をそのまま使用。Noneは0扱い
        resolved = {k: (v if v is not None else 0) for k, v in manual_counters.items()}

    calc = _get_calculator()
    summary = calc.calculate_evaluation(
        colony_id=colony_id,
        guard_pass_count=resolved["guard_pass_count"],
        guard_conditional_count=resolved["guard_conditional_count"],
        guard_fail_count=resolved["guard_fail_count"],
        guard_reject_count=resolved["guard_reject_count"],
        guard_total_count=resolved["guard_total_count"],
        escalation_count=resolved["escalation_count"],
        decision_count=resolved["decision_count"],
        referee_selected_count=resolved["referee_selected_count"],
        referee_candidate_count=resolved["referee_candidate_count"],
        sentinel_alert_count=resolved["sentinel_alert_count"],
        sentinel_false_alarm_count=resolved["sentinel_false_alarm_count"],
        total_monitoring_periods=resolved["total_monitoring_periods"],
    )
    return summary.model_dump(mode="json")


@router.get("/colonies")
async def get_kpi_colonies() -> dict[str, Any]:
    """KPIデータが存在するColony一覧を取得"""
    calc = _get_calculator()
    colonies = calc.store.list_colonies()
    return {"colonies": colonies, "count": len(colonies)}
