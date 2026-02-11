"""Colony進捗自動更新のテスト

GitHub Issue #15: P1-14: Colony進捗自動更新

Colony配下のRun/Task完了時に Colony の進捗を自動更新する。
"""

from colonyforge.core.events import (
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
)


class TestColonyProgressTracker:
    """ColonyProgressTrackerのテスト"""

    def test_tracker_class_exists(self):
        """ColonyProgressTrackerクラスが存在する"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        assert ColonyProgressTracker is not None

    def test_track_run_started(self):
        """RunStartedEventでRunを追跡開始する"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        event = RunStartedEvent(run_id="run-001", colony_id="colony-001")

        tracker.apply(event)

        assert "colony-001" in tracker.colonies
        assert "run-001" in tracker.colonies["colony-001"]["runs"]

    def test_track_multiple_runs(self):
        """複数のRunを追跡できる"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-003", colony_id="colony-002"))

        assert len(tracker.colonies["colony-001"]["runs"]) == 2
        assert len(tracker.colonies["colony-002"]["runs"]) == 1

    def test_run_completed_updates_status(self):
        """RunCompletedEventでRunのステータスを更新する"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunCompletedEvent(run_id="run-001"))

        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "completed"

    def test_run_failed_updates_status(self):
        """RunFailedEventでRunのステータスを更新する"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunFailedEvent(run_id="run-001"))

        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "failed"


class TestColonyAutoCompletion:
    """Colony自動完了のテスト"""

    def test_all_runs_completed_triggers_colony_completed(self):
        """全Runが完了したらColonyがcompleted状態になる"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        tracker.apply(RunCompletedEvent(run_id="run-001"))
        assert tracker.get_colony_status("colony-001") == "running"

        tracker.apply(RunCompletedEvent(run_id="run-002"))
        assert tracker.get_colony_status("colony-001") == "completed"

    def test_any_run_failed_triggers_colony_failed(self):
        """いずれかのRunが失敗したらColonyがfailed状態になる"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        tracker.apply(RunFailedEvent(run_id="run-001"))

        assert tracker.get_colony_status("colony-001") == "failed"

    def test_colony_status_running_with_pending_runs(self):
        """未完了Runがある場合はrunning状態"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))
        tracker.apply(RunCompletedEvent(run_id="run-001"))

        assert tracker.get_colony_status("colony-001") == "running"


class TestColonyShouldEmitEvents:
    """Colonyがイベントを発行すべきか判定するテスト"""

    def test_should_emit_completed_event(self):
        """全Run完了時にColonyCompletedイベントを発行すべき"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        event = RunCompletedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result == "colony.completed"

    def test_should_emit_failed_event(self):
        """Run失敗時にColonyFailedイベントを発行すべき"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        event = RunFailedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result == "colony.failed"

    def test_should_not_emit_when_runs_pending(self):
        """未完了Runがある場合はイベントを発行しない"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))
        tracker.apply(RunStartedEvent(run_id="run-002", colony_id="colony-001"))

        event = RunCompletedEvent(run_id="run-001")
        result = tracker.should_emit_colony_event(event)

        assert result is None


class TestColonyProgressNullHandling:
    """Null値ハンドリングのテスト"""

    def test_run_started_with_none_run_id_ignored(self):
        """run_id=Noneのrun.startedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        # run_id=Noneのイベント
        event = RunStartedEvent(run_id=None, colony_id="colony-001")  # type: ignore

        # Act
        tracker.apply(event)

        # Assert: Colonyは追加されない
        assert tracker.get_colony_status("colony-001") == "unknown"

    def test_run_started_with_none_colony_id_ignored(self):
        """colony_id=Noneのrun.startedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        event = RunStartedEvent(run_id="run-001", colony_id=None)  # type: ignore

        # Act
        tracker.apply(event)

        # Assert: run_to_colonyマッピングがない
        assert "run-001" not in tracker._run_to_colony

    def test_run_completed_with_none_run_id_ignored(self):
        """run_id=Noneのrun.completedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        # Act: run_id=Noneで完了
        event = RunCompletedEvent(run_id=None)  # type: ignore
        tracker.apply(event)

        # Assert: run-001はまだrunning
        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "running"

    def test_run_completed_unknown_run_id_ignored(self):
        """未知のrun_idのrun.completedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()

        # Act: 未知のrun_idで完了
        event = RunCompletedEvent(run_id="unknown-run")
        tracker.apply(event)

        # Assert: エラーなし（無視される）
        assert len(tracker.colonies) == 0

    def test_run_failed_with_none_run_id_ignored(self):
        """run_id=Noneのrun.failedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()
        tracker.apply(RunStartedEvent(run_id="run-001", colony_id="colony-001"))

        # Act
        event = RunFailedEvent(run_id=None)  # type: ignore
        tracker.apply(event)

        # Assert
        assert tracker.colonies["colony-001"]["runs"]["run-001"] == "running"

    def test_run_failed_unknown_run_id_ignored(self):
        """未知のrun_idのrun.failedは無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()

        # Act
        event = RunFailedEvent(run_id="unknown-run")
        tracker.apply(event)

        # Assert
        assert len(tracker.colonies) == 0

    def test_update_colony_status_unknown_colony_ignored(self):
        """未知のcolony_idの更新は無視される"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()

        # Act: 存在しないColonyを更新
        tracker._update_colony_status("unknown-colony")

        # Assert: エラーなし
        assert len(tracker.colonies) == 0

    def test_should_emit_with_unknown_run_returns_none(self):
        """未知のrun_idでshould_emitはNoneを返す"""
        from colonyforge.core.state.colony_progress import ColonyProgressTracker

        tracker = ColonyProgressTracker()

        # Act
        event = RunCompletedEvent(run_id="unknown-run")
        result = tracker.should_emit_colony_event(event)

        # Assert
        assert result is None
