"""Sentinel Hornet テスト

M2-0: Hive内監視エージェント
- 無限ループ検出
- 暴走検出（イベント発行レート閾値）
- コスト超過検出（トークン/APIコール累積監視）
- セキュリティ違反検出（ActionClass×TrustLevelポリシーチェック）
- Colony強制停止フロー
- 設定ベース閾値調整
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from colonyforge.core.events import BaseEvent, EventType

# ===========================================================================
# 前提条件テスト: ColonyState.SUSPENDED + colony.suspended イベント
# ===========================================================================


class TestColonyStateSuspended:
    """ColonyStateMachineにSUSPENDED状態が追加されていることを検証"""

    def test_colony_state_has_suspended(self):
        """ColonyState enumにSUSPENDED値が存在する"""
        # Arrange
        from colonyforge.core.ar.projections import ColonyState

        # Act & Assert
        assert hasattr(ColonyState, "SUSPENDED")
        assert ColonyState.SUSPENDED.value == "suspended"

    def test_event_type_has_colony_suspended(self):
        """EventType enumにCOLONY_SUSPENDED値が存在する"""
        # Act & Assert
        assert hasattr(EventType, "COLONY_SUSPENDED")
        assert EventType.COLONY_SUSPENDED.value == "colony.suspended"

    def test_colony_in_progress_to_suspended(self):
        """IN_PROGRESS -> SUSPENDED遷移

        Sentinel Hornetがアラートを発行した際にColonyがSUSPENDEDになる。
        """
        # Arrange
        from colonyforge.core.ar.projections import ColonyState
        from colonyforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.IN_PROGRESS

        event = BaseEvent(
            type=EventType.COLONY_SUSPENDED,
            payload={"colony_id": "colony-001", "reason": "Loop detected"},
        )

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == ColonyState.SUSPENDED

    def test_colony_suspended_to_in_progress(self):
        """SUSPENDED -> IN_PROGRESS遷移（再開）

        ユーザー承認後にColonyを再開できる。
        """
        # Arrange
        from colonyforge.core.ar.projections import ColonyState
        from colonyforge.core.events import ColonyStartedEvent
        from colonyforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.SUSPENDED

        event = ColonyStartedEvent(payload={"colony_id": "colony-001"})

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == ColonyState.IN_PROGRESS

    def test_colony_suspended_to_failed(self):
        """SUSPENDED -> FAILED遷移

        一時停止から失敗終了にできる。
        """
        # Arrange
        from colonyforge.core.ar.projections import ColonyState
        from colonyforge.core.events import ColonyFailedEvent
        from colonyforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.SUSPENDED

        event = ColonyFailedEvent(payload={"colony_id": "colony-001", "error": "User cancelled"})

        # Act
        new_state = sm.transition(event)

        # Assert
        assert new_state == ColonyState.FAILED

    def test_colony_suspended_valid_events(self):
        """SUSPENDED状態から遷移可能なイベント一覧"""
        # Arrange
        from colonyforge.core.ar.projections import ColonyState
        from colonyforge.core.state import ColonyStateMachine

        sm = ColonyStateMachine()
        sm.current_state = ColonyState.SUSPENDED

        # Act
        valid = sm.get_valid_events()

        # Assert: 再開(COLONY_STARTED)と失敗(COLONY_FAILED)のみ
        assert EventType.COLONY_STARTED in valid
        assert EventType.COLONY_FAILED in valid
        assert len(valid) == 2


class TestHiveAggregateColonySuspended:
    """HiveAggregate投影がcolony.suspendedを正しく処理する"""

    def test_apply_colony_suspended(self):
        """colony.suspendedイベントでColonyProjection.state=SUSPENDEDになる"""
        # Arrange
        from colonyforge.core.ar.hive_projections import HiveAggregate
        from colonyforge.core.ar.projections import ColonyState

        agg = HiveAggregate("hive-1")

        # Hive作成
        agg.apply(
            BaseEvent(
                type=EventType.HIVE_CREATED,
                payload={"name": "Test", "description": "Test"},
            )
        )
        # Colony作成
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_CREATED,
                payload={"colony_id": "c1", "name": "Frontend", "goal": "UI"},
            )
        )
        # Colony開始
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_STARTED,
                payload={"colony_id": "c1"},
            )
        )

        # Act: Colony一時停止
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_SUSPENDED,
                payload={"colony_id": "c1", "reason": "Loop detected"},
            )
        )

        # Assert
        assert agg.colonies["c1"].state == ColonyState.SUSPENDED

    def test_suspended_colony_not_in_active_colonies(self):
        """SUSPENDED Colonyはactive_coloniesに含まれない"""
        # Arrange
        from colonyforge.core.ar.hive_projections import HiveAggregate

        agg = HiveAggregate("hive-1")
        agg.apply(
            BaseEvent(
                type=EventType.HIVE_CREATED,
                payload={"name": "Test"},
            )
        )
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_CREATED,
                payload={"colony_id": "c1", "goal": "UI"},
            )
        )
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_STARTED,
                payload={"colony_id": "c1"},
            )
        )
        agg.apply(
            BaseEvent(
                type=EventType.COLONY_SUSPENDED,
                payload={"colony_id": "c1", "reason": "test"},
            )
        )

        # Act & Assert
        assert len(agg.active_colonies) == 0


# ===========================================================================
# Sentinel Hornetイベント型テスト
# ===========================================================================


class TestSentinelEventTypes:
    """Sentinelイベント型の存在確認"""

    def test_sentinel_alert_raised_event_type(self):
        """sentinel.alert_raisedイベント型が定義されている"""
        assert hasattr(EventType, "SENTINEL_ALERT_RAISED")
        assert EventType.SENTINEL_ALERT_RAISED.value == "sentinel.alert_raised"

    def test_sentinel_report_event_type(self):
        """sentinel.reportイベント型が定義されている"""
        assert hasattr(EventType, "SENTINEL_REPORT")
        assert EventType.SENTINEL_REPORT.value == "sentinel.report"


# ===========================================================================
# SentinelHornet コアモジュール テスト
# ===========================================================================


class TestSentinelHornetInit:
    """SentinelHornet初期化テスト"""

    def test_default_thresholds(self):
        """デフォルト閾値で初期化できる"""
        # Arrange & Act
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        # Assert
        assert sentinel.max_event_rate > 0
        assert sentinel.max_loop_count > 0
        assert sentinel.max_cost > 0

    def test_custom_thresholds(self):
        """カスタム閾値で初期化できる"""
        # Arrange & Act
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(
            max_event_rate=100,
            max_loop_count=3,
            max_cost=500.0,
        )

        # Assert
        assert sentinel.max_event_rate == 100
        assert sentinel.max_loop_count == 3
        assert sentinel.max_cost == 500.0

    def test_from_config(self):
        """設定ファイルから閾値を読み込める"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        config = {
            "max_event_rate": 200,
            "max_loop_count": 10,
            "max_cost": 1000.0,
            "cost_window_seconds": 600,
            "rate_window_seconds": 30,
        }

        # Act
        sentinel = SentinelHornet.from_config(config)

        # Assert
        assert sentinel.max_event_rate == 200
        assert sentinel.max_loop_count == 10
        assert sentinel.max_cost == 1000.0


# ===========================================================================
# 無限ループ検出 (M2-0-b)
# ===========================================================================


class TestLoopDetection:
    """無限ループ検出テスト"""

    def test_no_loop_normal_sequence(self):
        """正常なイベントシーケンスではループ検出しない"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_loop_count=3)

        events = [
            BaseEvent(type=EventType.TASK_CREATED, payload={"task_id": "t1"}),
            BaseEvent(type=EventType.TASK_ASSIGNED, payload={"task_id": "t1"}),
            BaseEvent(type=EventType.TASK_COMPLETED, payload={"task_id": "t1"}),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert: ループアラートなし
        loop_alerts = [a for a in alerts if a.alert_type == "loop_detected"]
        assert len(loop_alerts) == 0

    def test_detect_task_retry_loop(self):
        """タスクの作成→失敗→リトライの繰り返しを検出"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_loop_count=3)

        # タスクが3回以上 created→failed を繰り返す
        events = []
        for _ in range(4):
            events.append(BaseEvent(type=EventType.TASK_CREATED, payload={"task_id": "t1"}))
            events.append(BaseEvent(type=EventType.TASK_FAILED, payload={"task_id": "t1"}))

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert: ループ検出
        loop_alerts = [a for a in alerts if a.alert_type == "loop_detected"]
        assert len(loop_alerts) >= 1
        assert "t1" in loop_alerts[0].details.get("task_id", "")

    def test_detect_event_type_cycle(self):
        """同じイベント型パターンの周期的繰り返しを検出"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_loop_count=3)

        # A→B→A→B→A→B... パターン
        events = []
        for _ in range(4):
            events.append(BaseEvent(type=EventType.TASK_BLOCKED, payload={"task_id": "t1"}))
            events.append(BaseEvent(type=EventType.TASK_UNBLOCKED, payload={"task_id": "t1"}))

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert: 周期検出
        loop_alerts = [a for a in alerts if a.alert_type == "loop_detected"]
        assert len(loop_alerts) >= 1


# ===========================================================================
# 暴走検出 (M2-0-c)
# ===========================================================================


class TestRunawayDetection:
    """暴走検出テスト（イベント発行レート）"""

    def test_normal_rate_no_alert(self):
        """正常レートではアラートなし"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(
            max_event_rate=100,
            rate_window_seconds=60,
        )

        # 60秒間に10イベント — 正常
        now = datetime.now(UTC)
        events = [
            BaseEvent(
                type=EventType.TASK_PROGRESSED,
                payload={"task_id": "t1"},
                timestamp=now - timedelta(seconds=i * 6),
            )
            for i in range(10)
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        rate_alerts = [a for a in alerts if a.alert_type == "runaway_detected"]
        assert len(rate_alerts) == 0

    def test_high_rate_triggers_alert(self):
        """高レートでアラート発行"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(
            max_event_rate=10,
            rate_window_seconds=60,
        )

        # 60秒間に50イベント — 閾値超過
        now = datetime.now(UTC)
        events = [
            BaseEvent(
                type=EventType.TASK_PROGRESSED,
                payload={"task_id": "t1"},
                timestamp=now - timedelta(seconds=i),
            )
            for i in range(50)
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        rate_alerts = [a for a in alerts if a.alert_type == "runaway_detected"]
        assert len(rate_alerts) >= 1

    def test_old_events_outside_window_ignored(self):
        """ウィンドウ外の古いイベントはレート計算に含めない"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(
            max_event_rate=10,
            rate_window_seconds=60,
        )

        now = datetime.now(UTC)
        # 2分前の古いイベント100個 + 現在のイベント5個
        old_events = [
            BaseEvent(
                type=EventType.TASK_PROGRESSED,
                payload={"task_id": "t1"},
                timestamp=now - timedelta(seconds=120 + i),
            )
            for i in range(100)
        ]
        recent_events = [
            BaseEvent(
                type=EventType.TASK_PROGRESSED,
                payload={"task_id": "t1"},
                timestamp=now - timedelta(seconds=i),
            )
            for i in range(5)
        ]

        # Act
        alerts = sentinel.check_events(old_events + recent_events, colony_id="c1")

        # Assert: ウィンドウ内の5イベントのみ → 閾値10以下 → アラートなし
        rate_alerts = [a for a in alerts if a.alert_type == "runaway_detected"]
        assert len(rate_alerts) == 0


# ===========================================================================
# コスト超過検出 (M2-0-d)
# ===========================================================================


class TestCostDetection:
    """コスト超過検出テスト"""

    def test_normal_cost_no_alert(self):
        """正常コストではアラートなし"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_cost=1000.0)

        events = [
            BaseEvent(
                type=EventType.LLM_RESPONSE,
                payload={
                    "tokens_used": 100,
                    "cost": 0.01,
                },
            ),
            BaseEvent(
                type=EventType.LLM_RESPONSE,
                payload={
                    "tokens_used": 200,
                    "cost": 0.02,
                },
            ),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        cost_alerts = [a for a in alerts if a.alert_type == "cost_exceeded"]
        assert len(cost_alerts) == 0

    def test_cost_exceeded_triggers_alert(self):
        """コスト超過でアラート発行"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_cost=1.0)

        # 合計コスト: 500 * 0.01 = 5.0 > 1.0
        events = [
            BaseEvent(
                type=EventType.LLM_RESPONSE,
                payload={
                    "tokens_used": 1000,
                    "cost": 0.01,
                },
            )
            for _ in range(500)
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        cost_alerts = [a for a in alerts if a.alert_type == "cost_exceeded"]
        assert len(cost_alerts) >= 1
        assert cost_alerts[0].details["total_cost"] > 1.0

    def test_token_count_tracked(self):
        """トークン使用量が累積追跡される"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(max_cost=10000.0)

        events = [
            BaseEvent(
                type=EventType.LLM_RESPONSE,
                payload={"tokens_used": 500, "cost": 0.05},
            ),
            BaseEvent(
                type=EventType.LLM_RESPONSE,
                payload={"tokens_used": 300, "cost": 0.03},
            ),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert: アラートなしだが、トークン累積は追跡される
        cost_alerts = [a for a in alerts if a.alert_type == "cost_exceeded"]
        assert len(cost_alerts) == 0


# ===========================================================================
# セキュリティ違反検出 (M2-0-e)
# ===========================================================================


class TestSecurityViolationDetection:
    """セキュリティ違反検出テスト（ActionClass×TrustLevelチェック）"""

    def test_read_only_no_violation(self):
        """READ_ONLY操作はどのTrustLevelでも違反なし"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        events = [
            BaseEvent(
                type=EventType.WORKER_STARTED,
                payload={
                    "tool_name": "read_file",
                    "trust_level": 0,
                },
            ),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        sec_alerts = [a for a in alerts if a.alert_type == "security_violation"]
        assert len(sec_alerts) == 0

    def test_irreversible_at_low_trust_triggers_alert(self):
        """IRREVERSIBLE操作が低TrustLevelで実行されたら違反"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        events = [
            BaseEvent(
                type=EventType.WORKER_STARTED,
                payload={
                    "tool_name": "deploy",
                    "trust_level": 0,  # REPORT_ONLY
                    "action_class": "irreversible",
                    "confirmed": False,
                },
            ),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        sec_alerts = [a for a in alerts if a.alert_type == "security_violation"]
        assert len(sec_alerts) >= 1

    def test_irreversible_with_confirmation_no_violation(self):
        """IRREVERSIBLE操作でもconfirmed=Trueなら違反なし"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        events = [
            BaseEvent(
                type=EventType.WORKER_STARTED,
                payload={
                    "tool_name": "deploy",
                    "trust_level": 1,
                    "action_class": "irreversible",
                    "confirmed": True,
                },
            ),
        ]

        # Act
        alerts = sentinel.check_events(events, colony_id="c1")

        # Assert
        sec_alerts = [a for a in alerts if a.alert_type == "security_violation"]
        assert len(sec_alerts) == 0


# ===========================================================================
# Colony強制停止フロー (M2-0-f)
# ===========================================================================


class TestColonySuspensionFlow:
    """Colony強制停止フロー テスト"""

    def test_generate_alert_event(self):
        """アラートからsentinel.alert_raisedイベントを生成"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="loop_detected",
            colony_id="c1",
            severity="critical",
            details={"task_id": "t1", "loop_count": 5},
            message="Loop detected in task t1",
        )

        # Act
        event = sentinel.create_alert_event(alert)

        # Assert
        assert event.type == EventType.SENTINEL_ALERT_RAISED
        assert event.payload["alert_type"] == "loop_detected"
        assert event.payload["colony_id"] == "c1"
        assert event.payload["severity"] == "critical"

    def test_generate_suspension_event(self):
        """アラートからcolony.suspendedイベントを生成"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="runaway_detected",
            colony_id="c1",
            severity="critical",
            details={"event_rate": 200},
            message="Event rate exceeded threshold",
        )

        # Act
        event = sentinel.create_suspension_event(alert)

        # Assert
        assert event.type == EventType.COLONY_SUSPENDED
        assert event.payload["colony_id"] == "c1"
        assert event.payload["reason"] == "Event rate exceeded threshold"

    def test_generate_report_event(self):
        """監視レポートイベントを生成"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        # Act
        event = sentinel.create_report_event(
            colony_id="c1",
            summary="All checks passed",
            alerts_count=0,
        )

        # Assert
        assert event.type == EventType.SENTINEL_REPORT
        assert event.payload["colony_id"] == "c1"
        assert event.payload["alerts_count"] == 0


# ===========================================================================
# 設定ベース閾値調整 (M2-0-h)
# ===========================================================================


class TestSentinelConfig:
    """設定ファイルからの閾値読み込みテスト"""

    def test_default_config_values(self):
        """SentinelHornetのデフォルト値が妥当"""
        # Arrange & Act
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        # Assert: 合理的なデフォルト値
        assert sentinel.max_event_rate == 50  # 1分あたり50イベント
        assert sentinel.rate_window_seconds == 60
        assert sentinel.max_loop_count == 5
        assert sentinel.max_cost == 100.0  # $100

    def test_from_config_partial(self):
        """一部の設定のみ上書き、残りはデフォルト"""
        # Arrange
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        config = {"max_event_rate": 200}

        # Act
        sentinel = SentinelHornet.from_config(config)

        # Assert
        assert sentinel.max_event_rate == 200
        assert sentinel.max_loop_count == 5  # デフォルト維持
        assert sentinel.max_cost == 100.0  # デフォルト維持


# ===========================================================================
# M3-6: Sentinel Hornet拡張
# ===========================================================================


class TestSentinelExtendedEventTypes:
    """M3-6で追加されたイベントタイプのテスト"""

    def test_rollback_event_type(self):
        """SENTINEL_ROLLBACK イベントタイプが存在する"""
        assert hasattr(EventType, "SENTINEL_ROLLBACK")
        assert EventType.SENTINEL_ROLLBACK.value == "sentinel.rollback"

    def test_quarantine_event_type(self):
        """SENTINEL_QUARANTINE イベントタイプが存在する"""
        assert hasattr(EventType, "SENTINEL_QUARANTINE")
        assert EventType.SENTINEL_QUARANTINE.value == "sentinel.quarantine"

    def test_kpi_degradation_event_type(self):
        """SENTINEL_KPI_DEGRADATION イベントタイプが存在する"""
        assert hasattr(EventType, "SENTINEL_KPI_DEGRADATION")
        assert EventType.SENTINEL_KPI_DEGRADATION.value == "sentinel.kpi_degradation"


class TestKPIDegradationDetection:
    """M3-6-a: KPI劣化検出（Honeycomb連携）"""

    def test_detect_correctness_drop(self):
        """Correctness KPIの急低下をアラートとして検出"""
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        # Arrange: 前回KPI=0.9, 現在KPI=0.3 → 60%以上低下
        prev_kpi = {"correctness": 0.9, "incident_rate": 0.1}
        curr_kpi = {"correctness": 0.3, "incident_rate": 0.1}

        # Act
        alerts = sentinel.check_kpi_degradation(
            colony_id="colony-001",
            previous_kpi=prev_kpi,
            current_kpi=curr_kpi,
        )

        # Assert
        assert len(alerts) >= 1
        assert any(a.alert_type == "kpi_degradation" for a in alerts)

    def test_no_alert_stable_kpi(self):
        """KPIが安定している場合はアラートなし"""
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        prev_kpi = {"correctness": 0.9, "incident_rate": 0.1}
        curr_kpi = {"correctness": 0.88, "incident_rate": 0.12}

        alerts = sentinel.check_kpi_degradation(
            colony_id="colony-001",
            previous_kpi=prev_kpi,
            current_kpi=curr_kpi,
        )

        assert len(alerts) == 0

    def test_detect_incident_rate_spike(self):
        """Incident Rateの急上昇を検出"""
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        prev_kpi = {"correctness": 0.9, "incident_rate": 0.1}
        curr_kpi = {"correctness": 0.9, "incident_rate": 0.8}

        alerts = sentinel.check_kpi_degradation(
            colony_id="colony-001",
            previous_kpi=prev_kpi,
            current_kpi=curr_kpi,
        )

        assert len(alerts) >= 1

    def test_kpi_degradation_empty_kpi(self):
        """KPIが空の場合はアラートなし"""
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet()

        alerts = sentinel.check_kpi_degradation(
            colony_id="colony-001",
            previous_kpi={},
            current_kpi={},
        )

        assert len(alerts) == 0

    def test_kpi_degradation_threshold_configurable(self):
        """KPI劣化閾値を設定可能"""
        from colonyforge.sentinel_hornet.monitor import SentinelHornet

        sentinel = SentinelHornet(kpi_drop_threshold=0.5)

        # 40%低下 → 閾値50%未満なのでアラートなし
        prev_kpi = {"correctness": 1.0}
        curr_kpi = {"correctness": 0.6}

        alerts = sentinel.check_kpi_degradation(
            colony_id="colony-001",
            previous_kpi=prev_kpi,
            current_kpi=curr_kpi,
        )

        assert len(alerts) == 0


class TestRollbackAction:
    """M3-6-b: ロールバックアクション"""

    def test_create_rollback_event(self):
        """ロールバックイベントを生成できる"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="kpi_degradation",
            colony_id="colony-001",
            severity="critical",
            message="Correctness dropped from 0.9 to 0.3",
        )

        # Act
        event = sentinel.create_rollback_event(
            alert=alert,
            rollback_to="run-previous",
        )

        # Assert
        assert event.type == EventType.SENTINEL_ROLLBACK
        assert event.payload["colony_id"] == "colony-001"
        assert event.payload["rollback_to"] == "run-previous"
        assert event.payload["reason"] == alert.message

    def test_rollback_event_payload(self):
        """ロールバックイベントのペイロードに必要情報が含まれる"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="cost_exceeded",
            colony_id="colony-002",
            severity="critical",
            message="Cost exceeded",
            details={"total_cost": 200.0},
        )

        event = sentinel.create_rollback_event(
            alert=alert,
            rollback_to="run-001",
        )

        assert "alert_type" in event.payload
        assert event.payload["alert_type"] == "cost_exceeded"


class TestQuarantineAction:
    """M3-6-c: 隔離アクション"""

    def test_create_quarantine_event(self):
        """隔離イベントを生成できる"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="security_violation",
            colony_id="colony-001",
            severity="critical",
            message="Unconfirmed irreversible action",
        )

        # Act
        event = sentinel.create_quarantine_event(
            alert=alert,
            quarantine_scope="colony",
        )

        # Assert
        assert event.type == EventType.SENTINEL_QUARANTINE
        assert event.payload["colony_id"] == "colony-001"
        assert event.payload["scope"] == "colony"
        assert event.payload["reason"] == alert.message

    def test_quarantine_task_scope(self):
        """タスクスコープの隔離"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="loop_detected",
            colony_id="colony-001",
            severity="critical",
            message="Task task-001 looping",
            details={"task_id": "task-001"},
        )

        event = sentinel.create_quarantine_event(
            alert=alert,
            quarantine_scope="task",
            target_id="task-001",
        )

        assert event.payload["scope"] == "task"
        assert event.payload["target_id"] == "task-001"

    def test_kpi_degradation_event(self):
        """KPI劣化イベントを生成できる"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="kpi_degradation",
            colony_id="colony-001",
            severity="warning",
            message="Correctness dropped",
            details={"metric": "correctness", "previous": 0.9, "current": 0.3},
        )

        event = sentinel.create_kpi_degradation_event(alert)

        assert event.type == EventType.SENTINEL_KPI_DEGRADATION
        assert event.payload["colony_id"] == "colony-001"
        assert event.payload["details"]["metric"] == "correctness"


class TestExecutionActions:
    """3つの執行アクション（停止/ロールバック/隔離）の統合テスト"""

    def test_all_three_actions_available(self):
        """3つの執行アクションが全て利用可能"""
        from colonyforge.sentinel_hornet.monitor import SentinelAlert, SentinelHornet

        sentinel = SentinelHornet()
        alert = SentinelAlert(
            alert_type="test",
            colony_id="colony-001",
            severity="critical",
            message="test alert",
        )

        # 停止（既存）
        suspension = sentinel.create_suspension_event(alert)
        assert suspension.type == EventType.COLONY_SUSPENDED

        # ロールバック（M3-6-b新規）
        rollback = sentinel.create_rollback_event(alert, rollback_to="run-001")
        assert rollback.type == EventType.SENTINEL_ROLLBACK

        # 隔離（M3-6-c新規）
        quarantine = sentinel.create_quarantine_event(alert, quarantine_scope="colony")
        assert quarantine.type == EventType.SENTINEL_QUARANTINE
