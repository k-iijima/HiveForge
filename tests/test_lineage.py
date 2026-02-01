"""Lineage 親イベント自動設定のテスト

GitHub Issue #16: P1-15: Lineage 親イベント自動設定

イベント作成時に自動的に親イベントを設定する機能のテスト。
"""


from hiveforge.core.events import (
    RunCompletedEvent,
    RunStartedEvent,
    TaskAssignedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskProgressedEvent,
)
from hiveforge.core.lineage import LineageResolver


class TestLineageResolverClass:
    """LineageResolver クラスのテスト"""

    def test_lineage_resolver_exists(self):
        """LineageResolverクラスが存在する"""
        assert LineageResolver is not None

    def test_create_lineage_resolver(self):
        """LineageResolverを作成できる"""
        # Arrange & Act
        resolver = LineageResolver()

        # Assert
        assert resolver is not None


class TestLineageResolverForRun:
    """Run関連イベントの親解決テスト"""

    def test_run_started_has_no_parents(self):
        """run.startedは親を持たない"""
        # Arrange
        resolver = LineageResolver()
        event = RunStartedEvent(
            actor="user",
            payload={"goal": "テスト"},
        )

        # Act
        parents = resolver.resolve_parents(event, [])

        # Assert
        assert parents == []

    def test_run_completed_parents_are_task_completed_events(self):
        """run.completedの親はtask.completedイベント群"""
        # Arrange
        resolver = LineageResolver()

        # 事前イベント
        run_started = RunStartedEvent(
            id="run-started-001",
            run_id="run-001",
            actor="user",
            payload={"goal": "テスト"},
        )
        task1_completed = TaskCompletedEvent(
            id="task1-completed",
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"result": "完了"},
        )
        task2_completed = TaskCompletedEvent(
            id="task2-completed",
            run_id="run-001",
            task_id="task-002",
            actor="copilot",
            payload={"result": "完了"},
        )
        existing_events = [run_started, task1_completed, task2_completed]

        # run.completedイベント
        run_completed = RunCompletedEvent(
            run_id="run-001",
            actor="system",
            payload={"summary": "完了"},
        )

        # Act
        parents = resolver.resolve_parents(run_completed, existing_events)

        # Assert
        assert "task1-completed" in parents
        assert "task2-completed" in parents


class TestLineageResolverForTask:
    """Task関連イベントの親解決テスト"""

    def test_task_created_parent_is_run_started(self):
        """task.createdの親はrun.started"""
        # Arrange
        resolver = LineageResolver()

        run_started = RunStartedEvent(
            id="run-started-001",
            run_id="run-001",
            actor="user",
            payload={"goal": "テスト"},
        )
        existing_events = [run_started]

        task_created = TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )

        # Act
        parents = resolver.resolve_parents(task_created, existing_events)

        # Assert
        assert parents == ["run-started-001"]

    def test_task_assigned_parent_is_task_created(self):
        """task.assignedの親はtask.created"""
        # Arrange
        resolver = LineageResolver()

        task_created = TaskCreatedEvent(
            id="task-created-001",
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )
        existing_events = [task_created]

        task_assigned = TaskAssignedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="queen:api-colony",
            payload={"assignee": "worker-001"},
        )

        # Act
        parents = resolver.resolve_parents(task_assigned, existing_events)

        # Assert
        assert parents == ["task-created-001"]

    def test_task_progressed_parent_is_task_created(self):
        """task.progressedの親はtask.created"""
        # Arrange
        resolver = LineageResolver()

        task_created = TaskCreatedEvent(
            id="task-created-001",
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )
        existing_events = [task_created]

        task_progressed = TaskProgressedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="worker-001",
            payload={"progress": 50, "message": "進行中"},
        )

        # Act
        parents = resolver.resolve_parents(task_progressed, existing_events)

        # Assert
        assert parents == ["task-created-001"]

    def test_task_completed_parent_is_task_created(self):
        """task.completedの親はtask.created"""
        # Arrange
        resolver = LineageResolver()

        task_created = TaskCreatedEvent(
            id="task-created-001",
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )
        existing_events = [task_created]

        task_completed = TaskCompletedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="worker-001",
            payload={"result": "完了"},
        )

        # Act
        parents = resolver.resolve_parents(task_completed, existing_events)

        # Assert
        assert parents == ["task-created-001"]


class TestLineageResolverWithExplicitParents:
    """明示的な親指定がある場合のテスト"""

    def test_explicit_parents_override_auto(self):
        """明示的に親が指定されている場合は自動設定しない"""
        # Arrange
        resolver = LineageResolver()

        run_started = RunStartedEvent(
            id="run-started-001",
            run_id="run-001",
            actor="user",
            payload={"goal": "テスト"},
        )
        existing_events = [run_started]

        # 明示的に親を指定
        task_created = TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
            parents=["explicit-parent-001"],  # 明示的な親
        )

        # Act
        parents = resolver.resolve_parents(task_created, existing_events)

        # Assert: 明示的な親が優先
        assert parents == ["explicit-parent-001"]


class TestLineageResolverEdgeCases:
    """エッジケースのテスト"""

    def test_no_matching_parent_returns_empty(self):
        """親が見つからない場合は空リスト"""
        # Arrange
        resolver = LineageResolver()

        # run.startedがない状態でtask.createdを作成
        task_created = TaskCreatedEvent(
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )

        # Act
        parents = resolver.resolve_parents(task_created, [])

        # Assert
        assert parents == []

    def test_task_in_different_run_not_matched(self):
        """異なるrun_idのイベントは親として選ばれない"""
        # Arrange
        resolver = LineageResolver()

        # 別のrunのrun.started
        run_started_other = RunStartedEvent(
            id="run-started-other",
            run_id="run-OTHER",
            actor="user",
            payload={"goal": "別のテスト"},
        )
        existing_events = [run_started_other]

        task_created = TaskCreatedEvent(
            run_id="run-001",  # 異なるrun_id
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )

        # Act
        parents = resolver.resolve_parents(task_created, existing_events)

        # Assert
        assert parents == []


class TestLineageResolverNullRunId:
    """run_idがNoneの場合のテスト"""

    def test_task_created_with_none_run_id_returns_empty(self):
        """run_idがNoneのtask.createdは空リストを返す"""
        # Arrange
        resolver = LineageResolver()
        run_started = RunStartedEvent(
            id="run-started-001",
            run_id="run-001",
            actor="user",
            payload={"goal": "テスト"},
        )
        existing_events = [run_started]

        # run_idをNoneに設定（通常はないが防御コード確認）
        task_created = TaskCreatedEvent(
            run_id=None,  # type: ignore
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )

        # Act
        parents = resolver.resolve_parents(task_created, existing_events)

        # Assert
        assert parents == []

    def test_task_completed_with_none_task_id_returns_empty(self):
        """task_idがNoneのtask.completedは空リストを返す"""
        # Arrange
        resolver = LineageResolver()
        task_created = TaskCreatedEvent(
            id="task-created-001",
            run_id="run-001",
            task_id="task-001",
            actor="copilot",
            payload={"title": "テストタスク"},
        )
        existing_events = [task_created]

        # task_idをNoneに設定
        task_completed = TaskCompletedEvent(
            run_id="run-001",
            task_id=None,  # type: ignore
            actor="worker-001",
            payload={"result": "完了"},
        )

        # Act
        parents = resolver.resolve_parents(task_completed, existing_events)

        # Assert
        assert parents == []

    def test_run_completed_with_none_run_id_returns_empty(self):
        """run_idがNoneのrun.completedは空リストを返す"""
        # Arrange
        resolver = LineageResolver()
        task_completed = TaskCompletedEvent(
            id="task-completed-001",
            run_id="run-001",
            task_id="task-001",
            actor="worker-001",
            payload={"result": "完了"},
        )
        existing_events = [task_completed]

        run_completed = RunCompletedEvent(
            run_id=None,  # type: ignore
            actor="system",
            payload={"summary": "完了"},
        )

        # Act
        parents = resolver.resolve_parents(run_completed, existing_events)

        # Assert
        assert parents == []
