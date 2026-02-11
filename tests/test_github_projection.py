"""GitHubProjection テスト

AR イベント → GitHub操作 の射影（Projection）テスト。
GitHubClient をモックして、イベントごとの正しいマッピングを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from colonyforge.core.config import GitHubConfig
from colonyforge.core.events.base import BaseEvent
from colonyforge.core.events.types import EventType
from colonyforge.core.github.projection import GitHubProjection, SyncState

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def github_config() -> GitHubConfig:
    """テスト用 GitHubConfig"""
    return GitHubConfig(
        enabled=True,
        owner="test-owner",
        repo="test-repo",
        project_number=1,
        label_prefix="colonyforge:",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """モック GitHubClient"""
    client = MagicMock()
    client.create_issue = AsyncMock(return_value={"number": 42, "id": 12345})
    client.update_issue = AsyncMock(return_value={"number": 42, "state": "open"})
    client.close_issue = AsyncMock(return_value={"number": 42, "state": "closed"})
    client.add_comment = AsyncMock(return_value={"id": 999, "body": "comment"})
    client.apply_labels = AsyncMock(return_value=[{"name": "colonyforge:run"}])
    return client


@pytest.fixture
def projection(github_config: GitHubConfig, mock_client: MagicMock) -> GitHubProjection:
    """テスト用 GitHubProjection"""
    return GitHubProjection(config=github_config, client=mock_client)


def _make_event(
    event_type: EventType | str,
    run_id: str = "01HTEST_RUN",
    payload: dict | None = None,
    **kwargs,
) -> BaseEvent:
    """テスト用イベント生成ヘルパー"""
    return BaseEvent(
        type=event_type,
        run_id=run_id,
        payload=payload or {},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# RunStarted → Issue 作成
# ---------------------------------------------------------------------------


class TestRunStartedProjection:
    """RunStarted イベントの射影テスト"""

    @pytest.mark.asyncio
    async def test_run_started_creates_issue(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """RunStarted イベントが Issue 作成にマッピングされること

        RunのgoalをIssueタイトルに含め、run_idをラベルで管理する。
        """
        # Arrange
        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "Implement feature X"},
        )

        # Act
        await projection.apply(event)

        # Assert
        mock_client.create_issue.assert_called_once()
        call_kwargs = mock_client.create_issue.call_args.kwargs
        assert "01HRUN123" in call_kwargs["title"]
        assert "Implement feature X" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_run_started_stores_mapping(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """RunStarted 後に run_id → issue_number のマッピングが保存されること

        後続イベント（Guard結果、Close等）が正しいIssueに紐づくために必要。
        """
        # Arrange
        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )

        # Act
        await projection.apply(event)

        # Assert: マッピングが保存されている
        assert projection.get_issue_number("01HRUN123") == 42

    @pytest.mark.asyncio
    async def test_run_started_idempotent(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """同じRunStartedを2回適用してもIssueは1つだけ作成されること

        冪等性: 再同期時にIssueが重複作成されないことを保証。
        """
        # Arrange
        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )

        # Act: 2回適用
        await projection.apply(event)
        await projection.apply(event)

        # Assert: create_issue は1回だけ呼ばれる
        assert mock_client.create_issue.call_count == 1


# ---------------------------------------------------------------------------
# RunCompleted → Issue クローズ
# ---------------------------------------------------------------------------


class TestRunCompletedProjection:
    """RunCompleted イベントの射影テスト"""

    @pytest.mark.asyncio
    async def test_run_completed_closes_issue(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """RunCompleted イベントが Issue クローズにマッピングされること"""
        # Arrange: まず Run を開始して Issue を作成
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        complete_event = _make_event(
            EventType.RUN_COMPLETED,
            run_id="01HRUN123",
            payload={"summary": "All tasks done"},
        )

        # Act
        await projection.apply(complete_event)

        # Assert
        mock_client.close_issue.assert_called_once_with(issue_number=42)

    @pytest.mark.asyncio
    async def test_run_completed_adds_summary_comment(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """RunCompleted 時にサマリーコメントが追加されること"""
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        complete_event = _make_event(
            EventType.RUN_COMPLETED,
            run_id="01HRUN123",
            payload={"summary": "All tasks done"},
        )

        # Act
        await projection.apply(complete_event)

        # Assert: コメントも追加される
        mock_client.add_comment.assert_called_once()
        call_kwargs = mock_client.add_comment.call_args.kwargs
        assert "All tasks done" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_run_completed_without_issue_is_noop(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """対応するIssueが無い場合、RunCompletedは何もしないこと

        RunStartedが未同期の状態でCompletedだけ来ても安全に無視。
        """
        # Arrange
        event = _make_event(
            EventType.RUN_COMPLETED,
            run_id="01HUNKNOWN",
            payload={"summary": "done"},
        )

        # Act
        await projection.apply(event)

        # Assert: 何も呼ばれない
        mock_client.close_issue.assert_not_called()
        mock_client.add_comment.assert_not_called()


# ---------------------------------------------------------------------------
# GuardResult → コメント
# ---------------------------------------------------------------------------


class TestGuardResultProjection:
    """GuardResult イベントの射影テスト"""

    @pytest.mark.asyncio
    async def test_guard_fail_adds_comment(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """Guard検証失敗時にIssueにコメントが追加されること

        Guard Beeの検証結果をGitHub Issueで可視化する。
        """
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        guard_event = _make_event(
            EventType.GUARD_FAILED,
            run_id="01HRUN123",
            payload={
                "verdict": "fail",
                "reason": "Test coverage 45% < 80%",
                "colony_id": "COL-001",
            },
        )

        # Act
        await projection.apply(guard_event)

        # Assert
        mock_client.add_comment.assert_called_once()
        call_kwargs = mock_client.add_comment.call_args.kwargs
        assert call_kwargs["issue_number"] == 42
        assert "fail" in call_kwargs["body"].lower()

    @pytest.mark.asyncio
    async def test_guard_pass_adds_comment(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """Guard検証成功時もコメントが追加されること"""
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        guard_event = _make_event(
            EventType.GUARD_PASSED,
            run_id="01HRUN123",
            payload={"verdict": "pass", "reason": "All checks passed"},
        )

        # Act
        await projection.apply(guard_event)

        # Assert
        mock_client.add_comment.assert_called_once()


# ---------------------------------------------------------------------------
# SentinelIntervention → ラベル
# ---------------------------------------------------------------------------


class TestSentinelInterventionProjection:
    """SentinelIntervention イベントの射影テスト"""

    @pytest.mark.asyncio
    async def test_sentinel_intervention_applies_label(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """Sentinel介入時にIssueにラベルが適用されること

        緊急停止や異常検出をGitHub上で即座に可視化する。
        """
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        sentinel_event = _make_event(
            EventType.SENTINEL_ALERT_RAISED,
            run_id="01HRUN123",
            payload={"severity": "critical", "message": "Token limit exceeded"},
        )

        # Act
        await projection.apply(sentinel_event)

        # Assert
        mock_client.apply_labels.assert_called_once()
        call_kwargs = mock_client.apply_labels.call_args.kwargs
        assert call_kwargs["issue_number"] == 42
        labels = call_kwargs["labels"]
        assert any("sentinel" in label for label in labels)

    @pytest.mark.asyncio
    async def test_sentinel_intervention_adds_comment(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """Sentinel介入時にコメントも追加されること"""
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        sentinel_event = _make_event(
            EventType.SENTINEL_ALERT_RAISED,
            run_id="01HRUN123",
            payload={"severity": "critical", "message": "Anomaly detected"},
        )

        # Act
        await projection.apply(sentinel_event)

        # Assert
        mock_client.add_comment.assert_called_once()


# ---------------------------------------------------------------------------
# TaskCompleted → コメント
# ---------------------------------------------------------------------------


class TestTaskCompletedProjection:
    """TaskCompleted イベントの射影テスト"""

    @pytest.mark.asyncio
    async def test_task_completed_adds_progress_comment(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """TaskCompleted 時に進捗コメントが追加されること"""
        # Arrange
        start_event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        await projection.apply(start_event)

        task_event = _make_event(
            EventType.TASK_COMPLETED,
            run_id="01HRUN123",
            task_id="TASK-001",
            payload={"result": "Implemented login feature"},
        )

        # Act
        await projection.apply(task_event)

        # Assert
        mock_client.add_comment.assert_called_once()
        call_kwargs = mock_client.add_comment.call_args.kwargs
        assert call_kwargs["issue_number"] == 42


# ---------------------------------------------------------------------------
# SyncState 管理
# ---------------------------------------------------------------------------


class TestSyncState:
    """同期状態管理テスト"""

    def test_sync_state_tracks_last_event_id(self, projection: GitHubProjection) -> None:
        """SyncState にデフォルト値が設定されること"""
        # Arrange & Act
        state = projection.sync_state

        # Assert
        assert isinstance(state, SyncState)
        assert state.last_synced_event_id is None
        assert state.run_issue_map == {}

    @pytest.mark.asyncio
    async def test_sync_state_updated_after_apply(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """イベント適用後にlast_synced_event_idが更新されること"""
        # Arrange
        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )

        # Act
        await projection.apply(event)

        # Assert
        assert projection.sync_state.last_synced_event_id == event.id

    @pytest.mark.asyncio
    async def test_already_synced_event_skipped(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """既に同期済みのイベントはスキップされること

        event_idベースの冪等性チェック。
        """
        # Arrange
        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )
        projection.sync_state.synced_event_ids.add(event.id)

        # Act
        await projection.apply(event)

        # Assert: create_issue は呼ばれない
        mock_client.create_issue.assert_not_called()


# ---------------------------------------------------------------------------
# 未対応イベント
# ---------------------------------------------------------------------------


class TestUnsupportedEvents:
    """未対応イベントタイプのテスト"""

    @pytest.mark.asyncio
    async def test_unsupported_event_is_noop(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """未対応のイベントタイプは無視されること

        すべてのイベントタイプに対してハンドラを定義する必要はない。
        未対応イベントは安全にスキップされるべき。
        """
        # Arrange
        event = _make_event(
            EventType.COLONY_STARTED,
            run_id="01HRUN123",
            payload={"colony_id": "COL-001"},
        )

        # Act
        await projection.apply(event)

        # Assert: 何も呼ばれない
        mock_client.create_issue.assert_not_called()
        mock_client.update_issue.assert_not_called()
        mock_client.close_issue.assert_not_called()
        mock_client.add_comment.assert_not_called()
        mock_client.apply_labels.assert_not_called()


# ---------------------------------------------------------------------------
# GitHubConfig disabled
# ---------------------------------------------------------------------------


class TestDisabledProjection:
    """Projection無効時のテスト"""

    @pytest.mark.asyncio
    async def test_disabled_projection_is_noop(self, mock_client: MagicMock) -> None:
        """enabled=False の場合、全イベントが無視されること"""
        # Arrange
        config = GitHubConfig(enabled=False, owner="x", repo="y")
        projection = GitHubProjection(config=config, client=mock_client)

        event = _make_event(
            EventType.RUN_STARTED,
            run_id="01HRUN123",
            payload={"goal": "test"},
        )

        # Act
        await projection.apply(event)

        # Assert
        mock_client.create_issue.assert_not_called()


# ---------------------------------------------------------------------------
# batch_apply
# ---------------------------------------------------------------------------


class TestBatchApply:
    """バッチ適用テスト"""

    @pytest.mark.asyncio
    async def test_batch_apply_processes_all_events(
        self, projection: GitHubProjection, mock_client: MagicMock
    ) -> None:
        """batch_apply が複数イベントを順番に処理すること

        AR replay 結果を一括でProjectionに渡す際に使用。
        """
        # Arrange
        events = [
            _make_event(
                EventType.RUN_STARTED,
                run_id="01HRUN123",
                payload={"goal": "test"},
            ),
            _make_event(
                EventType.TASK_COMPLETED,
                run_id="01HRUN123",
                task_id="TASK-001",
                payload={"result": "done"},
            ),
            _make_event(
                EventType.RUN_COMPLETED,
                run_id="01HRUN123",
                payload={"summary": "all done"},
            ),
        ]

        # Act
        await projection.batch_apply(events)

        # Assert: Issue作成 + コメント(task) + コメント(summary) + クローズ
        assert mock_client.create_issue.call_count == 1
        assert mock_client.close_issue.call_count == 1
        assert mock_client.add_comment.call_count >= 2  # task + summary
