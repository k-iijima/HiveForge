"""GET /kpi/event-counters エンドポイントのテスト

M5-4: ARイベントストアからGuard/Sentinel/Decision/Escalation
カウンターを自動集計するAPIのテスト。

テスト方針:
- イベント種別ごとのカウント正確性
- スコープ（run_id / colony_id / 期間）による絞り込み
- 重複イベントの排除
- KPI不変条件の検証
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from colonyforge.api.helpers import clear_active_runs, set_ar
from colonyforge.api.server import app
from colonyforge.core.ar import AkashicRecord
from colonyforge.core.events import BaseEvent
from colonyforge.core.events.types import EventType


@pytest.fixture()
def client(tmp_path):
    """テスト用クライアント（event-counters APIテスト専用）"""
    set_ar(None)
    clear_active_runs()

    vault_path = tmp_path / "Vault"
    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = vault_path
    mock_s.server.cors.enabled = False

    with (
        patch("colonyforge.api.server.get_settings", return_value=mock_s),
        patch("colonyforge.api.helpers.get_settings", return_value=mock_s),
        patch("colonyforge.api.routes.kpi.get_settings", return_value=mock_s),
        TestClient(app) as c,
    ):
        yield c, vault_path

    set_ar(None)
    clear_active_runs()


def _make_event(
    event_type: EventType | str,
    run_id: str = "run-1",
    colony_id: str = "colony-1",
    event_id: str | None = None,
    timestamp: datetime | None = None,
    payload: dict | None = None,
) -> BaseEvent:
    """テスト用イベントを生成"""
    from colonyforge.core.events.base import generate_event_id

    return BaseEvent(
        id=event_id or generate_event_id(),
        type=event_type,
        run_id=run_id,
        colony_id=colony_id,
        timestamp=timestamp or datetime.now(UTC),
        payload=payload or {},
    )


def _seed_events(vault_path, events: list[BaseEvent]) -> None:
    """テスト用イベントをAkashicRecordに投入"""
    ar = AkashicRecord(vault_path)
    for ev in events:
        ar.append(ev, run_id=ev.run_id)


# =========================================================================
# 基本: 各EventTypeのカウント正確性
# =========================================================================


class TestEventCountersBasic:
    """GET /kpi/event-counters の基本カウントテスト"""

    def test_empty_returns_all_zeros(self, client):
        """イベントなしの場合、全カウンターが0

        run_id指定で空のRunを対象にすると全カウンター0で返る。
        """
        # Arrange
        c, vault_path = client
        # 空のRunを作成（events.jsonlファイルのみ）
        (vault_path / "run-empty").mkdir(parents=True, exist_ok=True)
        (vault_path / "run-empty" / "events.jsonl").touch()

        # Act
        response = c.get("/kpi/event-counters?run_id=run-empty")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["guard_pass_count"] == 0
        assert data["guard_conditional_count"] == 0
        assert data["guard_fail_count"] == 0
        assert data["guard_total_count"] == 0
        assert data["guard_reject_count"] == 0
        assert data["sentinel_alert_count"] == 0
        assert data["sentinel_false_alarm_count"] == 0
        assert data["total_monitoring_periods"] == 0
        assert data["escalation_count"] == 0
        assert data["decision_count"] == 0
        assert data["referee_selected_count"] == 0
        assert data["referee_candidate_count"] == 0

    def test_guard_events_counted(self, client):
        """Guard Beeイベントが正しくカウントされる

        guard.passed → guard_pass_count + guard_total_count
        guard.conditional_passed → guard_conditional_count + guard_total_count
        guard.failed → guard_fail_count + guard_total_count + guard_reject_count
        """
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.GUARD_PASSED),
            _make_event(EventType.GUARD_PASSED),
            _make_event(EventType.GUARD_CONDITIONAL_PASSED),
            _make_event(EventType.GUARD_FAILED),
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["guard_pass_count"] == 2
        assert data["guard_conditional_count"] == 1
        assert data["guard_fail_count"] == 1
        assert data["guard_total_count"] == 4
        assert data["guard_reject_count"] == 1

    def test_sentinel_events_counted(self, client):
        """Sentinelイベントが正しくカウントされる

        sentinel.alert_raised → sentinel_alert_count
        sentinel.alert_raised + payload.false_alarm=true → sentinel_false_alarm_count
        sentinel.report → total_monitoring_periods
        """
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.SENTINEL_ALERT_RAISED),
            _make_event(EventType.SENTINEL_ALERT_RAISED),
            _make_event(
                EventType.SENTINEL_ALERT_RAISED,
                payload={"false_alarm": True},
            ),
            _make_event(EventType.SENTINEL_REPORT),
            _make_event(EventType.SENTINEL_REPORT),
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["sentinel_alert_count"] == 3
        assert data["sentinel_false_alarm_count"] == 1
        assert data["total_monitoring_periods"] == 2

    def test_intervention_events_counted(self, client):
        """介入イベントが正しくカウントされる

        intervention.queen_escalation → escalation_count
        """
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.QUEEN_ESCALATION),
            _make_event(EventType.QUEEN_ESCALATION),
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["escalation_count"] == 2

    def test_decision_events_counted(self, client):
        """Decision / Refereeイベントが正しくカウントされる

        decision.recorded → decision_count
        decision.proposal.created → referee_candidate_count
        decision.applied → referee_selected_count
        """
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.DECISION_RECORDED),
            _make_event(EventType.DECISION_RECORDED),
            _make_event(EventType.DECISION_RECORDED),
            _make_event(EventType.PROPOSAL_CREATED),
            _make_event(EventType.PROPOSAL_CREATED),
            _make_event(EventType.DECISION_APPLIED),
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["decision_count"] == 3
        assert data["referee_candidate_count"] == 2
        assert data["referee_selected_count"] == 1

    def test_unrelated_events_not_counted(self, client):
        """カウント対象外のイベントは無視される"""
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.TASK_CREATED),
            _make_event(EventType.LLM_REQUEST),
            _make_event(EventType.WORKER_COMPLETED),
            _make_event(EventType.HIVE_CREATED),
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["guard_total_count"] == 0
        assert data["sentinel_alert_count"] == 0
        assert data["escalation_count"] == 0
        assert data["decision_count"] == 0

    def test_mixed_events_counted_correctly(self, client):
        """複数種別の混在イベントが正しく集計される"""
        # Arrange
        c, vault_path = client
        events = [
            _make_event(EventType.GUARD_PASSED),
            _make_event(EventType.SENTINEL_ALERT_RAISED),
            _make_event(EventType.DECISION_RECORDED),
            _make_event(EventType.GUARD_FAILED),
            _make_event(EventType.QUEEN_ESCALATION),
            _make_event(EventType.SENTINEL_REPORT),
            _make_event(EventType.TASK_CREATED),  # 対象外
        ]
        _seed_events(vault_path, events)

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["guard_pass_count"] == 1
        assert data["guard_fail_count"] == 1
        assert data["guard_total_count"] == 2
        assert data["sentinel_alert_count"] == 1
        assert data["total_monitoring_periods"] == 1
        assert data["decision_count"] == 1
        assert data["escalation_count"] == 1


# =========================================================================
# スコープ: run_id / colony_id / 期間フィルタ
# =========================================================================


class TestEventCountersScope:
    """集計スコープのテスト"""

    def test_no_scope_returns_400(self, client):
        """run_id も colony_id も未指定なら 400 Bad Request

        無制限走査を防止するため、スコープの指定を必須とする。
        """
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/event-counters")

        # Assert
        assert response.status_code == 400
        assert "scope" in response.json()["detail"].lower()

    def test_run_id_isolates_events(self, client):
        """run_id指定時に他のRunのイベントが混ざらない"""
        # Arrange
        c, vault_path = client
        # Run-Aに2つのguard.passed
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, run_id="run-a"),
                _make_event(EventType.GUARD_PASSED, run_id="run-a"),
            ],
        )
        # Run-Bに3つのguard.passed
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, run_id="run-b"),
                _make_event(EventType.GUARD_PASSED, run_id="run-b"),
                _make_event(EventType.GUARD_PASSED, run_id="run-b"),
            ],
        )

        # Act
        response_a = c.get("/kpi/event-counters?run_id=run-a")
        response_b = c.get("/kpi/event-counters?run_id=run-b")

        # Assert
        assert response_a.json()["guard_pass_count"] == 2
        assert response_b.json()["guard_pass_count"] == 3

    def test_colony_id_filters(self, client):
        """colony_id指定時にそのColonyのイベントのみ集計"""
        # Arrange
        c, vault_path = client
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, run_id="run-1", colony_id="col-a"),
                _make_event(EventType.GUARD_PASSED, run_id="run-1", colony_id="col-b"),
                _make_event(EventType.GUARD_PASSED, run_id="run-1", colony_id="col-a"),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?colony_id=col-a&run_id=run-1")

        # Assert
        assert response.status_code == 200
        assert response.json()["guard_pass_count"] == 2

    def test_from_ts_inclusive(self, client):
        """from_ts は inclusive（その時刻を含む）"""
        # Arrange
        c, vault_path = client
        t1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
        t3 = datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC)
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, timestamp=t1),
                _make_event(EventType.GUARD_PASSED, timestamp=t2),
                _make_event(EventType.GUARD_PASSED, timestamp=t3),
            ],
        )

        # Act: from_ts=t2 → t2, t3 の2件
        response = c.get(
            "/kpi/event-counters",
            params={"run_id": "run-1", "from_ts": t2.isoformat()},
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["guard_pass_count"] == 2

    def test_to_ts_exclusive(self, client):
        """to_ts は exclusive（その時刻を含まない）"""
        # Arrange
        c, vault_path = client
        t1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
        t3 = datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC)
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, timestamp=t1),
                _make_event(EventType.GUARD_PASSED, timestamp=t2),
                _make_event(EventType.GUARD_PASSED, timestamp=t3),
            ],
        )

        # Act: to_ts=t3 → t1, t2 の2件
        response = c.get(
            "/kpi/event-counters",
            params={"run_id": "run-1", "to_ts": t3.isoformat()},
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["guard_pass_count"] == 2

    def test_from_ts_and_to_ts_range(self, client):
        """from_ts と to_ts の組み合わせで正確な範囲指定"""
        # Arrange
        c, vault_path = client
        base = datetime(2025, 6, 1, tzinfo=UTC)
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, timestamp=base + timedelta(hours=i))
                for i in range(5)
            ],
        )

        # Act: 1時間目から3時間目まで（2件: h1, h2）
        response = c.get(
            "/kpi/event-counters",
            params={
                "run_id": "run-1",
                "from_ts": (base + timedelta(hours=1)).isoformat(),
                "to_ts": (base + timedelta(hours=3)).isoformat(),
            },
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["guard_pass_count"] == 2


# =========================================================================
# 重複イベント対策（冪等性）
# =========================================================================


class TestEventCountersIdempotency:
    """重複イベントの集計安定性テスト"""

    def test_duplicate_event_id_counted_once(self, client):
        """同一event_idを持つイベントが重複投入されても1回だけカウント"""
        # Arrange
        c, vault_path = client
        fixed_id = "evt-fixed-001"
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED, event_id=fixed_id),
                _make_event(EventType.GUARD_PASSED, event_id=fixed_id),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")

        # Assert
        assert response.status_code == 200
        assert response.json()["guard_pass_count"] == 1
        assert response.json()["guard_total_count"] == 1


# =========================================================================
# KPI不変条件
# =========================================================================


class TestKPIInvariants:
    """KPIカウンターの不変条件を検証

    集計結果が論理的に矛盾しないことを保証する。
    """

    def test_guard_total_equals_sum(self, client):
        """guard_total_count == guard_pass + conditional + fail"""
        # Arrange
        c, vault_path = client
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_CONDITIONAL_PASSED),
                _make_event(EventType.GUARD_CONDITIONAL_PASSED),
                _make_event(EventType.GUARD_CONDITIONAL_PASSED),
                _make_event(EventType.GUARD_FAILED),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")
        data = response.json()

        # Assert
        assert data["guard_total_count"] == (
            data["guard_pass_count"] + data["guard_conditional_count"] + data["guard_fail_count"]
        )
        assert data["guard_total_count"] == 6

    def test_guard_reject_lte_fail(self, client):
        """guard_reject_count <= guard_fail_count"""
        # Arrange
        c, vault_path = client
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_FAILED),
                _make_event(EventType.GUARD_FAILED),
                _make_event(EventType.GUARD_PASSED),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")
        data = response.json()

        # Assert
        assert data["guard_reject_count"] <= data["guard_fail_count"]

    def test_sentinel_false_alarm_lte_alert(self, client):
        """sentinel_false_alarm_count <= sentinel_alert_count"""
        # Arrange
        c, vault_path = client
        _seed_events(
            vault_path,
            [
                _make_event(EventType.SENTINEL_ALERT_RAISED),
                _make_event(
                    EventType.SENTINEL_ALERT_RAISED,
                    payload={"false_alarm": True},
                ),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")
        data = response.json()

        # Assert
        assert data["sentinel_false_alarm_count"] <= data["sentinel_alert_count"]
        assert data["sentinel_alert_count"] == 2
        assert data["sentinel_false_alarm_count"] == 1

    def test_decision_gte_referee_selected(self, client):
        """decision_count >= referee_selected_count"""
        # Arrange
        c, vault_path = client
        _seed_events(
            vault_path,
            [
                _make_event(EventType.DECISION_RECORDED),
                _make_event(EventType.DECISION_RECORDED),
                _make_event(EventType.DECISION_APPLIED),
            ],
        )

        # Act
        response = c.get("/kpi/event-counters?run_id=run-1")
        data = response.json()

        # Assert
        assert data["decision_count"] >= data["referee_selected_count"]


# =========================================================================
# GET /kpi/evaluation — count_mode テスト
# =========================================================================


class TestEvaluationCountMode:
    """GET /kpi/evaluation の count_mode パラメータテスト"""

    def test_count_mode_auto(self, client):
        """count_mode=auto でARイベントから自動集計される

        手動パラメータが渡されても無視され、イベント集計値が使われる。
        """
        # Arrange
        c, vault_path = client
        # HoneycombStore にエピソードも必要（KPI scores 算出用）
        from colonyforge.core.honeycomb import Episode, HoneycombStore, Outcome

        store = HoneycombStore(vault_path)
        store.append(
            Episode(
                episode_id="ep-1",
                run_id="run-1",
                colony_id="colony-1",
                outcome=Outcome.SUCCESS,
                duration_seconds=100.0,
                token_count=500,
            )
        )
        # ARにGuardイベント投入
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_FAILED),
            ],
        )

        # Act
        response = c.get("/kpi/evaluation?run_id=run-1&count_mode=auto")

        # Assert
        assert response.status_code == 200
        data = response.json()
        gate = data["gate_accuracy"]
        # 3件中2件pass → pass_rate ≈ 0.667
        assert gate["guard_pass_rate"] is not None
        assert abs(gate["guard_pass_rate"] - 2 / 3) < 0.01

    def test_count_mode_manual(self, client):
        """count_mode=manual で入力値をそのまま使用

        ARにイベントがあっても無視され、クエリパラメータの値が使われる。
        """
        # Arrange
        c, vault_path = client
        from colonyforge.core.honeycomb import Episode, HoneycombStore, Outcome

        store = HoneycombStore(vault_path)
        store.append(
            Episode(
                episode_id="ep-1",
                run_id="run-1",
                colony_id="colony-1",
                outcome=Outcome.SUCCESS,
                duration_seconds=100.0,
                token_count=500,
            )
        )
        # ARイベントは3件あるが…
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_PASSED),
            ],
        )

        # Act: 手動で 10 pass, 0 fail を指定
        response = c.get(
            "/kpi/evaluation?count_mode=manual"
            "&guard_pass_count=10&guard_conditional_count=0&guard_fail_count=0"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        gate = data["gate_accuracy"]
        assert gate["guard_pass_rate"] == 1.0  # 10/10 = 100%

    def test_count_mode_mixed_prefers_manual(self, client):
        """count_mode=mixed で手動値を優先し、Noneの項目だけ自動補完"""
        # Arrange
        c, vault_path = client
        from colonyforge.core.honeycomb import Episode, HoneycombStore, Outcome

        store = HoneycombStore(vault_path)
        store.append(
            Episode(
                episode_id="ep-1",
                run_id="run-1",
                colony_id="colony-1",
                outcome=Outcome.SUCCESS,
                duration_seconds=100.0,
                token_count=500,
            )
        )
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.SENTINEL_ALERT_RAISED),
            ],
        )

        # Act: guard_pass_count=5 を手動指定、sentinel系は自動
        response = c.get("/kpi/evaluation?run_id=run-1&count_mode=mixed&guard_pass_count=5")

        # Assert
        assert response.status_code == 200
        data = response.json()
        gate = data["gate_accuracy"]
        # guard_pass は手動の5を使用 → guard_total=5+0+0=5
        # total_monitoring_periods はARから自動集計=0
        # sentinel_alert は自動集計の1を使用
        assert gate["sentinel_false_alarm_rate"] == 0.0
        # guard_pass_rate = 5 / (5+0+0) = 1.0
        assert gate["guard_pass_rate"] == 1.0

    def test_count_mode_default_is_auto(self, client):
        """count_mode未指定時のデフォルトはauto"""
        # Arrange
        c, vault_path = client
        from colonyforge.core.honeycomb import Episode, HoneycombStore, Outcome

        store = HoneycombStore(vault_path)
        store.append(
            Episode(
                episode_id="ep-1",
                run_id="run-1",
                colony_id="colony-1",
                outcome=Outcome.SUCCESS,
                duration_seconds=100.0,
                token_count=500,
            )
        )
        _seed_events(
            vault_path,
            [
                _make_event(EventType.GUARD_PASSED),
                _make_event(EventType.GUARD_PASSED),
            ],
        )

        # Act: count_mode 未指定
        response = c.get("/kpi/evaluation?run_id=run-1")

        # Assert: 自動集計で2件pass
        assert response.status_code == 200
        data = response.json()
        gate = data["gate_accuracy"]
        assert gate["guard_pass_rate"] == 1.0  # 2/2 = 100%
