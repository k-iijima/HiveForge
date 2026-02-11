"""Intervention Store のテスト

InterventionStoreの永続化・リプレイ・クエリの検証。
MCP/API双方で同一ストアを使う設計を保証する。
"""

import pytest

from colonyforge.core.intervention.models import (
    EscalationRecord,
    EscalationStatus,
    FeedbackRecord,
    InterventionRecord,
    InterventionType,
)
from colonyforge.core.intervention.store import InterventionStore


@pytest.fixture
def store(tmp_path):
    """テスト用InterventionStore"""
    return InterventionStore(base_path=tmp_path)


# =========================================================================
# モデルのテスト
# =========================================================================


class TestInterventionModels:
    """データモデルの基本テスト"""

    def test_intervention_record_creation(self):
        """InterventionRecordが正しく作成される"""
        # Arrange / Act
        record = InterventionRecord(
            event_id="evt-1",
            colony_id="colony-1",
            instruction="ファイルを修正",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Assert
        assert record.event_id == "evt-1"
        assert record.type == InterventionType.USER_INTERVENTION
        assert record.colony_id == "colony-1"
        assert record.instruction == "ファイルを修正"

    def test_escalation_record_default_status(self):
        """EscalationRecordのデフォルトステータスはPENDING"""
        # Arrange / Act
        record = EscalationRecord(
            event_id="evt-2",
            colony_id="colony-1",
            escalation_type="resource_conflict",
            summary="リソース競合",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Assert
        assert record.status == EscalationStatus.PENDING

    def test_feedback_record_creation(self):
        """FeedbackRecordが正しく作成される"""
        # Arrange / Act
        record = FeedbackRecord(
            event_id="evt-3",
            escalation_id="evt-2",
            resolution="手動でマージ解決",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Assert
        assert record.escalation_id == "evt-2"
        assert record.resolution == "手動でマージ解決"


# =========================================================================
# ストアの書き込み・読み取りテスト
# =========================================================================


class TestInterventionStoreBasic:
    """InterventionStoreの基本CRUD"""

    def test_add_and_get_intervention(self, store):
        """介入を追加して取得できる"""
        # Arrange
        record = InterventionRecord(
            event_id="int-1",
            colony_id="colony-1",
            instruction="テストを追加",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Act
        store.add_intervention(record)
        result = store.get_intervention("int-1")

        # Assert
        assert result is not None
        assert result.event_id == "int-1"
        assert result.instruction == "テストを追加"

    def test_add_and_get_escalation(self, store):
        """エスカレーションを追加して取得できる"""
        # Arrange
        record = EscalationRecord(
            event_id="esc-1",
            colony_id="colony-1",
            escalation_type="resource_conflict",
            summary="リソース競合",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Act
        store.add_escalation(record)
        result = store.get_escalation("esc-1")

        # Assert
        assert result is not None
        assert result.summary == "リソース競合"
        assert result.status == EscalationStatus.PENDING

    def test_add_and_get_feedback(self, store):
        """フィードバックを追加して取得できる"""
        # Arrange
        record = FeedbackRecord(
            event_id="fb-1",
            escalation_id="esc-1",
            resolution="解決済み",
            timestamp="2026-02-08T00:00:00Z",
        )

        # Act
        store.add_feedback(record)
        result = store.get_feedback("fb-1")

        # Assert
        assert result is not None
        assert result.resolution == "解決済み"

    def test_get_nonexistent_returns_none(self, store):
        """存在しないIDはNoneを返す"""
        # Act / Assert
        assert store.get_intervention("nonexistent") is None
        assert store.get_escalation("nonexistent") is None
        assert store.get_feedback("nonexistent") is None

    def test_get_target_finds_escalation(self, store):
        """get_targetでエスカレーションが見つかる"""
        # Arrange
        esc = EscalationRecord(
            event_id="esc-1",
            colony_id="colony-1",
            escalation_type="resource_conflict",
            summary="テスト",
            timestamp="2026-02-08T00:00:00Z",
        )
        store.add_escalation(esc)

        # Act
        target = store.get_target("esc-1")

        # Assert
        assert target is not None
        assert target.event_id == "esc-1"

    def test_get_target_finds_intervention(self, store):
        """get_targetで介入が見つかる"""
        # Arrange
        intv = InterventionRecord(
            event_id="int-1",
            colony_id="colony-1",
            instruction="修正",
            timestamp="2026-02-08T00:00:00Z",
        )
        store.add_intervention(intv)

        # Act
        target = store.get_target("int-1")

        # Assert
        assert target is not None
        assert target.event_id == "int-1"

    def test_get_target_not_found(self, store):
        """get_targetで見つからない場合None"""
        # Act / Assert
        assert store.get_target("nonexistent") is None


# =========================================================================
# エスカレーション状態更新テスト
# =========================================================================


class TestEscalationStatusUpdate:
    """エスカレーション状態更新のテスト"""

    def test_resolve_escalation(self, store):
        """エスカレーションをresolved状態に更新できる"""
        # Arrange
        esc = EscalationRecord(
            event_id="esc-1",
            colony_id="colony-1",
            escalation_type="resource_conflict",
            summary="テスト",
            timestamp="2026-02-08T00:00:00Z",
        )
        store.add_escalation(esc)

        # Act
        result = store.resolve_escalation("esc-1")

        # Assert
        assert result is True
        updated = store.get_escalation("esc-1")
        assert updated.status == EscalationStatus.RESOLVED

    def test_resolve_nonexistent_returns_false(self, store):
        """存在しないエスカレーションの解決はFalse"""
        # Act / Assert
        assert store.resolve_escalation("nonexistent") is False


# =========================================================================
# クエリテスト
# =========================================================================


class TestInterventionStoreQuery:
    """クエリ機能のテスト"""

    def _seed_escalations(self, store):
        """テスト用エスカレーションを複数追加"""
        store.add_escalation(
            EscalationRecord(
                event_id="esc-1",
                colony_id="colony-1",
                escalation_type="resource_conflict",
                summary="競合1",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        store.add_escalation(
            EscalationRecord(
                event_id="esc-2",
                colony_id="colony-2",
                escalation_type="quality_concern",
                summary="品質不安2",
                timestamp="2026-02-08T01:00:00Z",
            )
        )
        store.resolve_escalation("esc-2")

    def test_list_escalations_all(self, store):
        """全エスカレーション一覧"""
        # Arrange
        self._seed_escalations(store)

        # Act
        result = store.list_escalations()

        # Assert
        assert len(result) == 2

    def test_list_escalations_by_colony(self, store):
        """Colony IDでフィルタ"""
        # Arrange
        self._seed_escalations(store)

        # Act
        result = store.list_escalations(colony_id="colony-1")

        # Assert
        assert len(result) == 1
        assert result[0]["colony_id"] == "colony-1"

    def test_list_escalations_by_status(self, store):
        """ステータスでフィルタ"""
        # Arrange
        self._seed_escalations(store)

        # Act
        pending = store.list_escalations(status="pending")
        resolved = store.list_escalations(status="resolved")

        # Assert
        assert len(pending) == 1
        assert len(resolved) == 1

    def test_list_interventions_all(self, store):
        """全介入一覧"""
        # Arrange
        store.add_intervention(
            InterventionRecord(
                event_id="int-1",
                colony_id="colony-1",
                instruction="修正A",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        store.add_intervention(
            InterventionRecord(
                event_id="int-2",
                colony_id="colony-2",
                instruction="修正B",
                timestamp="2026-02-08T01:00:00Z",
            )
        )

        # Act
        result = store.list_interventions()

        # Assert
        assert len(result) == 2

    def test_list_interventions_by_colony(self, store):
        """Colony IDでフィルタ"""
        # Arrange
        store.add_intervention(
            InterventionRecord(
                event_id="int-1",
                colony_id="colony-1",
                instruction="修正A",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        store.add_intervention(
            InterventionRecord(
                event_id="int-2",
                colony_id="colony-2",
                instruction="修正B",
                timestamp="2026-02-08T01:00:00Z",
            )
        )

        # Act
        result = store.list_interventions(colony_id="colony-1")

        # Assert
        assert len(result) == 1
        assert result[0]["colony_id"] == "colony-1"


# =========================================================================
# 永続化・リプレイテスト（M-01/M-02の核心）
# =========================================================================


class TestInterventionStorePersistence:
    """JSONL永続化とリプレイのテスト"""

    def test_replay_restores_interventions(self, tmp_path):
        """プロセス再起動後に介入データが復元される"""
        # Arrange: 1つ目のストアでデータ書き込み
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_intervention(
            InterventionRecord(
                event_id="int-1",
                colony_id="colony-1",
                instruction="テスト指示",
                timestamp="2026-02-08T00:00:00Z",
            )
        )

        # Act: 2つ目のストアを同じパスで作成（再起動シミュレーション）
        store2 = InterventionStore(base_path=tmp_path)

        # Assert: データが復元されている
        result = store2.get_intervention("int-1")
        assert result is not None
        assert result.instruction == "テスト指示"

    def test_replay_restores_escalations(self, tmp_path):
        """プロセス再起動後にエスカレーションが復元される"""
        # Arrange
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_escalation(
            EscalationRecord(
                event_id="esc-1",
                colony_id="colony-1",
                escalation_type="resource_conflict",
                summary="テスト競合",
                timestamp="2026-02-08T00:00:00Z",
            )
        )

        # Act
        store2 = InterventionStore(base_path=tmp_path)

        # Assert
        result = store2.get_escalation("esc-1")
        assert result is not None
        assert result.summary == "テスト競合"

    def test_replay_restores_feedbacks(self, tmp_path):
        """プロセス再起動後にフィードバックが復元される"""
        # Arrange
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_feedback(
            FeedbackRecord(
                event_id="fb-1",
                escalation_id="esc-1",
                resolution="手動解決",
                timestamp="2026-02-08T00:00:00Z",
            )
        )

        # Act
        store2 = InterventionStore(base_path=tmp_path)

        # Assert
        result = store2.get_feedback("fb-1")
        assert result is not None
        assert result.resolution == "手動解決"

    def test_replay_restores_resolved_status(self, tmp_path):
        """resolve後のステータスが永続化・復元される"""
        # Arrange
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_escalation(
            EscalationRecord(
                event_id="esc-1",
                colony_id="colony-1",
                escalation_type="resource_conflict",
                summary="テスト",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        store1.resolve_escalation("esc-1")

        # Act
        store2 = InterventionStore(base_path=tmp_path)

        # Assert
        result = store2.get_escalation("esc-1")
        assert result.status == EscalationStatus.RESOLVED

    def test_replay_skips_blank_lines(self, tmp_path):
        """空行がJSONLに含まれてもスキップされる"""
        # Arrange
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_intervention(
            InterventionRecord(
                event_id="int-1",
                colony_id="colony-1",
                instruction="テスト",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        # 空行を手動追加
        path = store1._interventions_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n\n")

        # Act
        store2 = InterventionStore(base_path=tmp_path)

        # Assert
        result = store2.get_intervention("int-1")
        assert result is not None

    def test_replay_warns_on_invalid_json(self, tmp_path, caplog):
        """不正なJSONがあるとwarningを出してスキップ"""
        import logging

        # Arrange
        store1 = InterventionStore(base_path=tmp_path)
        store1.add_intervention(
            InterventionRecord(
                event_id="int-1",
                colony_id="colony-1",
                instruction="テスト",
                timestamp="2026-02-08T00:00:00Z",
            )
        )
        # 不正なJSONを手動追加
        path = store1._interventions_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write("THIS IS NOT JSON\n")

        # Act
        with caplog.at_level(logging.WARNING):
            store2 = InterventionStore(base_path=tmp_path)

        # Assert
        result = store2.get_intervention("int-1")
        assert result is not None
        assert any("読み込みエラー" in r.message for r in caplog.records)

    def test_empty_base_path(self, tmp_path):
        """空のディレクトリからストアを初期化できる"""
        # Act
        store = InterventionStore(base_path=tmp_path / "empty")

        # Assert
        assert store.list_escalations() == []
        assert store.list_interventions() == []
