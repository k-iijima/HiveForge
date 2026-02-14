"""イベントカウンター集計モジュール

ARイベントストアからGuard/Sentinel/Decision/Escalationの
カウンターを自動集計する。

M5-4: KPIダッシュボードのnull指標解消
"""

from __future__ import annotations

from datetime import datetime

from ..ar import AkashicRecord
from ..events.types import EventType

# カウンター初期値
_COUNTER_KEYS = [
    "guard_pass_count",
    "guard_conditional_count",
    "guard_fail_count",
    "guard_total_count",
    "guard_reject_count",
    "sentinel_alert_count",
    "sentinel_false_alarm_count",
    "total_monitoring_periods",
    "escalation_count",
    "decision_count",
    "referee_selected_count",
    "referee_candidate_count",
]


def count_events(
    ar: AkashicRecord,
    *,
    run_id: str | None = None,
    colony_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, int]:
    """ARイベントから品質ゲートカウンターを自動集計

    集計スコープ:
        1. run_id 指定時: 当該 Run のイベントのみ
        2. colony_id + 期間指定時: 当該 Colony の期間内イベント
        3. colony_id のみ: 当該 Colony の全期間
        4. 全未指定: ValueError（無制限走査を防止）

    重複対策: event_id ベースの一意性保証で二重カウントを防止。

    Args:
        ar: AkashicRecord インスタンス
        run_id: 集計対象のRun ID
        colony_id: 集計対象のColony ID
        from_ts: 集計開始日時 (inclusive)
        to_ts: 集計終了日時 (exclusive)

    Returns:
        カウンター辞書

    Raises:
        ValueError: run_id も colony_id も未指定の場合
    """
    if not run_id and not colony_id:
        raise ValueError(
            "Scope required: specify at least run_id or colony_id to prevent unbounded scanning."
        )

    counters: dict[str, int] = dict.fromkeys(_COUNTER_KEYS, 0)
    seen_ids: set[str] = set()

    # run_id 指定時はそのRunだけ、未指定時は全Runを走査
    run_ids = [run_id] if run_id else ar.list_runs()

    for rid in run_ids:
        for event in ar.replay(rid):
            # 期間フィルタ
            if from_ts and event.timestamp < from_ts:
                continue
            if to_ts and event.timestamp >= to_ts:
                continue

            # Colony フィルタ
            if colony_id and event.colony_id != colony_id:
                continue

            # 重複排除
            if event.id in seen_ids:
                continue
            seen_ids.add(event.id)

            # カウント
            _count_event(counters, event)

    return counters


def _count_event(counters: dict[str, int], event: object) -> None:
    """個別イベントのカウントロジック

    Args:
        counters: カウンター辞書（in-place更新）
        event: BaseEvent インスタンス
    """
    etype = str(event.type)  # type: ignore[attr-defined]

    if etype == EventType.GUARD_PASSED:
        counters["guard_pass_count"] += 1
        counters["guard_total_count"] += 1
    elif etype == EventType.GUARD_CONDITIONAL_PASSED:
        counters["guard_conditional_count"] += 1
        counters["guard_total_count"] += 1
    elif etype == EventType.GUARD_FAILED:
        counters["guard_fail_count"] += 1
        counters["guard_total_count"] += 1
        counters["guard_reject_count"] += 1
    elif etype == EventType.SENTINEL_ALERT_RAISED:
        counters["sentinel_alert_count"] += 1
        payload = getattr(event, "payload", {}) or {}
        if payload.get("false_alarm") is True:
            counters["sentinel_false_alarm_count"] += 1
    elif etype == EventType.SENTINEL_REPORT:
        counters["total_monitoring_periods"] += 1
    elif etype == EventType.QUEEN_ESCALATION:
        counters["escalation_count"] += 1
    elif etype == EventType.DECISION_RECORDED:
        counters["decision_count"] += 1
    elif etype == EventType.PROPOSAL_CREATED:
        counters["referee_candidate_count"] += 1
    elif etype == EventType.DECISION_APPLIED:
        counters["referee_selected_count"] += 1
