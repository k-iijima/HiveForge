"""Colony進捗自動更新のテスト

GitHub Issue #15: P1-14: Colony進捗自動更新

Colony配下のRun/Task完了時に Colony の進捗を自動更新する。
"""


from hiveforge.core.events import (
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
)


class TestColonyProgressTracker:
    """ColonyProgressTrackerのテスト"""

    def test_tracker_class_exists(self):
        """ColonyProgressTrackerクラスが存在する"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        assert ColonyProgressTracker is not None

    def test_track_run_started(self):
        """RunStartedEventでRunを追跡開始する"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        event = RunStartedEvent(run_id="run-001", colony_id="colony-001")

        tracker.apply(event)

        assert "colony-001" in tracker.colonies
        assert "run-001" in tracker.colonies["colony-001"]["runs"]

    def test_track_multiple_runs(self):
        """複数のRunを追跡できる"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-003", colony_id="colony-002"))

        assert len(tracker.colonies["colony-001"]["runs"]) == 2
        assert len(tracker.colonies["colony-002"]["runs"]) == 1

    def test_run_completed_updates_status(self):
        """RunCompletedEventでRunのステータスを更新する"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunCompletedEvent(run_id="run-001"))

        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "completed"

    def test_run_failed_updates_status(self):
        """RunFailedEventでRunのステータスを更新する"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunFailedEvent(run_id="run-001"))

        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "failed"


class TestColonyAutoCompletion:
    """Colony自動完了のテスト"""

    def test_all_runs_completed_triggers_colony_completed(self):
        """全Runが完了したらColonyがcompleted状態になる"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        tracker.apply(RunCompletedEvent(run_id="run-001"))
        assert tracker.get_colony_status("colony-001") == "running"

        tracker.apply(RunCompletedEvent(run_id="run-002"))
        assert tracker.get_colony_status("colony-001") == "completed"

    def test_any_run_failed_triggers_colony_failed(self):
        """いずれかのRunが失敗したらColonyがfailed状態になる"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        tracker.apply(RunFailedEvent(run_id="run-001"))

        assert tracker.get_colony_status("colony-001") == "failed"

    def test_colony_status_running_with_pending_runs(self):
        """未完了Runがある場合はrunning状態"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))
        tracker.apply(RunCompletedEvent(run_id="run-001"))

        assert tracker.get_colony_status("colony-001") == "running"


class TestColonyShouldEmitEvents:
    """Colonyがイベントを発行すべきか判定するテスト"""

    def test_should_emit_completed_event(self):
        """全Run完了時にColonyCompletedイベントを発行すべき"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        event = RunCompletedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result == "colony.completed"

    def test_should_emit_failed_event(self):
        """Run失敗時にColonyFailedイベントを発行すべき"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        event = RunFailedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result == "colony.failed"

    def test_should_not_emit_when_runs_pending(self):
        """未完了Runがある場合はイベントを発行しない"""
        from hiveforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        event = RunCompletedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result is None
