"""ChangeTracker ユニットテスト — §11.3 要件変更追跡.

ChangeTracker が doorstop 要件の変更を検知し、
構造化された RA_REQ_CHANGED イベントを正しく発行することを検証する。
"""

from __future__ import annotations

import pytest

from colonyforge.core.events.types import EventType
from colonyforge.requirement_analysis.change_tracker import ChangeTracker
from colonyforge.requirement_analysis.models import ChangeReason


class TestTrackChange:
    """track_change メソッドのテスト群."""

    def test_track_change_happy_path(self) -> None:
        """最小限の必須フィールドで RA_REQ_CHANGED イベントを生成できる."""
        # Arrange
        tracker = ChangeTracker()

        # Act
        event = tracker.track_change(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.USER_EDIT,
            diff_summary="タイトルを変更",
        )

        # Assert
        assert event.type == EventType.RA_REQ_CHANGED
        assert event.payload["doorstop_id"] == "REQ001"
        assert event.payload["prev_version"] == 1
        assert event.payload["new_version"] == 2
        assert event.payload["reason"] == ChangeReason.USER_EDIT
        assert event.payload["diff_summary"] == "タイトルを変更"

    def test_track_change_with_all_fields(self) -> None:
        """全てのオプションフィールドを指定した場合もイベントが正しく生成される."""
        # Arrange
        tracker = ChangeTracker()
        diff_lines = ["-old line", "+new line"]
        affected = ["REQ002", "REQ003"]

        # Act
        event = tracker.track_change(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.CLARIFICATION,
            diff_summary="説明文を修正",
            diff_lines=diff_lines,
            affected_links=affected,
            cause_event_id="evt-abc-123",
            prev_hash="sha256-prev",
        )

        # Assert
        assert event.payload["diff_lines"] == diff_lines
        assert event.payload["affected_links"] == affected
        assert event.payload["cause_event_id"] == "evt-abc-123"
        assert event.prev_hash == "sha256-prev"

    def test_track_change_version_order_validation(self) -> None:
        """new_version <= prev_version の場合 ValueError が発生する."""
        # Arrange
        tracker = ChangeTracker()

        # Act & Assert: new_version == prev_version
        with pytest.raises(ValueError, match="new_version.*must be > prev_version"):
            tracker.track_change(
                doorstop_id="REQ001",
                prev_version=2,
                new_version=2,
                reason=ChangeReason.USER_EDIT,
                diff_summary="no change",
            )

        # Act & Assert: new_version < prev_version
        with pytest.raises(ValueError, match="new_version.*must be > prev_version"):
            tracker.track_change(
                doorstop_id="REQ001",
                prev_version=3,
                new_version=1,
                reason=ChangeReason.USER_EDIT,
                diff_summary="rollback",
            )

    @pytest.mark.parametrize(
        "reason",
        list(ChangeReason),
        ids=[r.value for r in ChangeReason],
    )
    def test_track_change_all_reasons(self, reason: ChangeReason) -> None:
        """全6種の ChangeReason でイベント生成が成功する."""
        # Arrange
        tracker = ChangeTracker()

        # Act
        event = tracker.track_change(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=reason,
            diff_summary=f"変更理由: {reason.value}",
        )

        # Assert
        assert event.payload["reason"] == reason

    def test_track_change_prev_hash_propagated(self) -> None:
        """prev_hash がイベントに正しく伝搬される."""
        # Arrange
        tracker = ChangeTracker()
        expected_hash = "abc123def456"

        # Act
        event = tracker.track_change(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.USER_EDIT,
            diff_summary="ハッシュ伝搬テスト",
            prev_hash=expected_hash,
        )

        # Assert
        assert event.prev_hash == expected_hash

    def test_event_payload_contains_all_fields(self) -> None:
        """RequirementChangedPayload の全フィールドがイベント payload に含まれる."""
        # Arrange
        tracker = ChangeTracker()

        # Act
        event = tracker.track_change(
            doorstop_id="REQ042",
            prev_version=3,
            new_version=4,
            reason=ChangeReason.DEPENDENCY_UPDATE,
            diff_summary="依存更新",
            diff_lines=["+added"],
            affected_links=["REQ099"],
            cause_event_id="evt-cause",
        )

        # Assert: 全フィールドが存在する
        expected_keys = {
            "doorstop_id",
            "prev_version",
            "new_version",
            "reason",
            "cause_event_id",
            "diff_summary",
            "diff_lines",
            "affected_links",
        }
        assert expected_keys <= set(event.payload.keys())

        # Assert: 値が正しい
        assert event.payload["doorstop_id"] == "REQ042"
        assert event.payload["prev_version"] == 3
        assert event.payload["new_version"] == 4
        assert event.payload["reason"] == ChangeReason.DEPENDENCY_UPDATE
        assert event.payload["cause_event_id"] == "evt-cause"
        assert event.payload["diff_summary"] == "依存更新"
        assert event.payload["diff_lines"] == ["+added"]
        assert event.payload["affected_links"] == ["REQ099"]

    def test_track_change_without_ar_store(self) -> None:
        """ar_store なしでもイベント生成が正常に動作する."""
        # Arrange
        tracker = ChangeTracker(ar_store=None)

        # Act
        event = tracker.track_change(
            doorstop_id="REQ001",
            prev_version=1,
            new_version=2,
            reason=ChangeReason.FEEDBACK_LOOP,
            diff_summary="ar_store なしテスト",
        )

        # Assert
        assert event.type == EventType.RA_REQ_CHANGED
        assert event.payload["doorstop_id"] == "REQ001"


class TestComputeDiff:
    """compute_diff メソッドのテスト群."""

    def test_compute_diff_basic(self) -> None:
        """異なる内容間で unified diff が生成される."""
        # Arrange
        tracker = ChangeTracker()
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"

        # Act
        diff = tracker.compute_diff(old, new)

        # Assert: diff が空でなく、変更行を含む
        assert len(diff) > 0
        assert any("-line2" in line for line in diff)
        assert any("+modified" in line for line in diff)

    def test_compute_diff_no_changes(self) -> None:
        """同一内容の場合、差分は空リストになる."""
        # Arrange
        tracker = ChangeTracker()
        content = "unchanged\ncontent\n"

        # Act
        diff = tracker.compute_diff(content, content)

        # Assert
        assert diff == []
