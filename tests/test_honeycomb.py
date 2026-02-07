"""Honeycomb テスト

Episode, HoneycombStore, EpisodeRecorder, KPICalculator のテスト。
M3-1 完了条件:
- Run/Task完了時にEpisodeがHoneycombに自動記録される
- 失敗時にFailureClassが分類される
- 5つのKPIが算出可能
"""

from __future__ import annotations

import pytest

from hiveforge.core import AkashicRecord, generate_event_id
from hiveforge.core.events import (
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)
from hiveforge.core.honeycomb.kpi import KPICalculator
from hiveforge.core.honeycomb.models import (
    Episode,
    FailureClass,
    KPIScores,
    Outcome,
)
from hiveforge.core.honeycomb.recorder import EpisodeRecorder
from hiveforge.core.honeycomb.store import HoneycombStore

# =========================================================================
# Episode モデルのテスト
# =========================================================================


class TestEpisodeModel:
    """Episodeデータモデルのテスト"""

    def test_create_success_episode(self):
        """成功エピソードが正しく作成される"""
        # Arrange & Act
        episode = Episode(
            episode_id="ep-001",
            run_id="run-001",
            colony_id="colony-001",
            outcome=Outcome.SUCCESS,
            duration_seconds=120.5,
            token_count=1500,
            goal="Hello World作成",
        )

        # Assert
        assert episode.outcome == Outcome.SUCCESS
        assert episode.duration_seconds == 120.5
        assert episode.token_count == 1500
        assert episode.failure_class is None
        assert episode.template_used == "balanced"

    def test_create_failure_episode(self):
        """失敗エピソードにFailureClassが設定される"""
        # Arrange & Act
        episode = Episode(
            episode_id="ep-002",
            run_id="run-002",
            colony_id="colony-001",
            outcome=Outcome.FAILURE,
            failure_class=FailureClass.IMPLEMENTATION_ERROR,
            goal="バグ修正",
        )

        # Assert
        assert episode.outcome == Outcome.FAILURE
        assert episode.failure_class == FailureClass.IMPLEMENTATION_ERROR

    def test_episode_is_frozen(self):
        """Episodeはイミュータブル（frozen）"""
        # Arrange
        episode = Episode(
            episode_id="ep-003",
            run_id="run-003",
            colony_id="colony-001",
            outcome=Outcome.SUCCESS,
        )

        # Act & Assert: 変更を試みるとエラー
        with pytest.raises(Exception):  # ValidationError for frozen
            episode.outcome = Outcome.FAILURE  # type: ignore

    def test_episode_with_kpi_scores(self):
        """KPIScoresが正しく設定される"""
        # Arrange & Act
        scores = KPIScores(
            correctness=0.85,
            lead_time_seconds=300.0,
        )
        episode = Episode(
            episode_id="ep-004",
            run_id="run-004",
            colony_id="colony-001",
            outcome=Outcome.SUCCESS,
            kpi_scores=scores,
        )

        # Assert
        assert episode.kpi_scores.correctness == 0.85
        assert episode.kpi_scores.lead_time_seconds == 300.0
        assert episode.kpi_scores.repeatability is None

    def test_episode_with_parent_links(self):
        """因果リンク（親Episode）が設定できる"""
        # Arrange & Act
        episode = Episode(
            episode_id="ep-005",
            run_id="run-005",
            colony_id="colony-001",
            outcome=Outcome.SUCCESS,
            parent_episode_ids=["ep-002", "ep-003"],
        )

        # Assert
        assert len(episode.parent_episode_ids) == 2
        assert "ep-002" in episode.parent_episode_ids

    def test_episode_serialization(self):
        """EpisodeのJSON変換が正しく動作する"""
        # Arrange
        episode = Episode(
            episode_id="ep-006",
            run_id="run-006",
            colony_id="colony-001",
            outcome=Outcome.FAILURE,
            failure_class=FailureClass.TIMEOUT,
            kpi_scores=KPIScores(correctness=0.5),
        )

        # Act
        data = episode.model_dump(mode="json")

        # Assert
        assert data["outcome"] == "failure"
        assert data["failure_class"] == "timeout"
        assert data["kpi_scores"]["correctness"] == 0.5

    def test_episode_deserialization(self):
        """JSONからEpisodeが復元できる"""
        # Arrange: JSON文字列（実際のJSONLストアと同じ形式）
        import json

        data = {
            "episode_id": "ep-007",
            "run_id": "run-007",
            "colony_id": "colony-001",
            "outcome": "success",
            "template_used": "speed",
            "duration_seconds": 60.0,
            "token_count": 500,
        }
        json_str = json.dumps(data)

        # Act: model_validate_jsonで復元（strictモードでもJSONデシリアライズは正常動作）
        episode = Episode.model_validate_json(json_str)

        # Assert
        assert episode.outcome == Outcome.SUCCESS
        assert episode.template_used == "speed"


class TestKPIScores:
    """KPIScoresモデルのテスト"""

    def test_default_scores(self):
        """デフォルトは全てNone"""
        # Act
        scores = KPIScores()

        # Assert
        assert scores.correctness is None
        assert scores.repeatability is None
        assert scores.lead_time_seconds is None
        assert scores.incident_rate is None
        assert scores.recurrence_rate is None

    def test_correctness_validation(self):
        """correctnessは0.0〜1.0の範囲"""
        # Act & Assert: 有効な範囲
        KPIScores(correctness=0.0)
        KPIScores(correctness=1.0)
        KPIScores(correctness=0.5)

        # Act & Assert: 範囲外はエラー
        with pytest.raises(Exception):
            KPIScores(correctness=1.5)
        with pytest.raises(Exception):
            KPIScores(correctness=-0.1)

    def test_kpi_scores_frozen(self):
        """KPIScoresはイミュータブル"""
        # Arrange
        scores = KPIScores(correctness=0.8)

        # Act & Assert
        with pytest.raises(Exception):
            scores.correctness = 0.9  # type: ignore


class TestFailureClass:
    """FailureClass列挙型のテスト"""

    def test_all_failure_classes_defined(self):
        """6つのFailureClassが定義されている"""
        # Assert
        assert len(FailureClass) == 6
        assert FailureClass.SPECIFICATION_ERROR.value == "specification_error"
        assert FailureClass.DESIGN_ERROR.value == "design_error"
        assert FailureClass.IMPLEMENTATION_ERROR.value == "implementation_error"
        assert FailureClass.INTEGRATION_ERROR.value == "integration_error"
        assert FailureClass.ENVIRONMENT_ERROR.value == "environment_error"
        assert FailureClass.TIMEOUT.value == "timeout"


class TestOutcome:
    """Outcome列挙型のテスト"""

    def test_all_outcomes_defined(self):
        """3つのOutcomeが定義されている"""
        # Assert
        assert len(Outcome) == 3
        assert Outcome.SUCCESS.value == "success"
        assert Outcome.FAILURE.value == "failure"
        assert Outcome.PARTIAL.value == "partial"


# =========================================================================
# HoneycombStore のテスト
# =========================================================================


class TestHoneycombStore:
    """HoneycombStore永続化のテスト"""

    @pytest.fixture
    def store(self, tmp_path):
        """テスト用HoneycombStore"""
        return HoneycombStore(tmp_path)

    def _make_episode(
        self,
        episode_id: str = "ep-001",
        colony_id: str = "colony-1",
        outcome: Outcome = Outcome.SUCCESS,
        **kwargs,
    ) -> Episode:
        """テスト用Episode作成ヘルパー"""
        return Episode(
            episode_id=episode_id,
            run_id=kwargs.get("run_id", f"run-{episode_id}"),
            colony_id=colony_id,
            outcome=outcome,
            **{k: v for k, v in kwargs.items() if k != "run_id"},
        )

    def test_append_and_replay(self, store):
        """エピソードを追記してリプレイできる"""
        # Arrange
        episode = self._make_episode()

        # Act
        store.append(episode)
        replayed = store.replay_colony("colony-1")

        # Assert
        assert len(replayed) == 1
        assert replayed[0].episode_id == "ep-001"
        assert replayed[0].outcome == Outcome.SUCCESS

    def test_replay_all(self, store):
        """全エピソードがリプレイできる"""
        # Arrange
        store.append(self._make_episode("ep-1", "colony-1"))
        store.append(self._make_episode("ep-2", "colony-2"))

        # Act
        all_episodes = store.replay_all()

        # Assert
        assert len(all_episodes) == 2

    def test_replay_colony_isolation(self, store):
        """Colony単位でエピソードが分離されている"""
        # Arrange
        store.append(self._make_episode("ep-1", "colony-1"))
        store.append(self._make_episode("ep-2", "colony-2"))
        store.append(self._make_episode("ep-3", "colony-1"))

        # Act
        colony1 = store.replay_colony("colony-1")
        colony2 = store.replay_colony("colony-2")

        # Assert
        assert len(colony1) == 2
        assert len(colony2) == 1

    def test_replay_empty_colony(self, store):
        """存在しないColonyのリプレイは空リスト"""
        # Act
        result = store.replay_colony("nonexistent")

        # Assert
        assert result == []

    def test_list_colonies(self, store):
        """エピソードが存在するColony一覧を取得"""
        # Arrange
        store.append(self._make_episode("ep-1", "colony-a"))
        store.append(self._make_episode("ep-2", "colony-b"))

        # Act
        colonies = store.list_colonies()

        # Assert
        assert "colony-a" in colonies
        assert "colony-b" in colonies
        assert len(colonies) == 2

    def test_count_by_colony(self, store):
        """Colony別のエピソード数を取得"""
        # Arrange
        store.append(self._make_episode("ep-1", "colony-1"))
        store.append(self._make_episode("ep-2", "colony-1"))
        store.append(self._make_episode("ep-3", "colony-2"))

        # Act & Assert
        assert store.count("colony-1") == 2
        assert store.count("colony-2") == 1
        assert store.count() == 3

    def test_persistence_across_instances(self, tmp_path):
        """ストアの再インスタンス化後もデータが永続化されている"""
        # Arrange: 1つ目のインスタンスでエピソード追記
        store1 = HoneycombStore(tmp_path)
        store1.append(self._make_episode("ep-1", "colony-1"))

        # Act: 2つ目のインスタンスでリプレイ
        store2 = HoneycombStore(tmp_path)
        replayed = store2.replay_colony("colony-1")

        # Assert
        assert len(replayed) == 1
        assert replayed[0].episode_id == "ep-1"

    def test_failure_episode_roundtrip(self, store):
        """失敗エピソードのシリアライズ/デシリアライズが正しい"""
        # Arrange
        episode = self._make_episode(
            "ep-fail",
            "colony-1",
            outcome=Outcome.FAILURE,
            failure_class=FailureClass.TIMEOUT,
            duration_seconds=600.0,
        )

        # Act
        store.append(episode)
        replayed = store.replay_colony("colony-1")

        # Assert
        assert replayed[0].outcome == Outcome.FAILURE
        assert replayed[0].failure_class == FailureClass.TIMEOUT
        assert replayed[0].duration_seconds == 600.0


# =========================================================================
# EpisodeRecorder のテスト
# =========================================================================


class TestEpisodeRecorder:
    """EpisodeRecorder のテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        """テスト用Akashic Record"""
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        """テスト用HoneycombStore"""
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        """テスト用EpisodeRecorder"""
        return EpisodeRecorder(honeycomb_store=store, ar=ar)

    def _seed_success_run(self, ar, run_id: str):
        """成功Runのイベントをシード"""
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "テスト"},
            ),
            run_id,
        )
        ar.append(
            TaskCreatedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1", "goal": "テスト"},
            ),
            run_id,
        )
        ar.append(
            TaskCompletedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1"},
            ),
            run_id,
        )
        ar.append(
            RunCompletedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"tasks_completed": 1, "tasks_total": 1},
            ),
            run_id,
        )

    def _seed_failed_run(self, ar, run_id: str, reason: str = "error"):
        """失敗Runのイベントをシード"""
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "テスト"},
            ),
            run_id,
        )
        ar.append(
            TaskCreatedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1"},
            ),
            run_id,
        )
        ar.append(
            TaskFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1", "reason": reason},
            ),
            run_id,
        )
        ar.append(
            RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"reason": reason, "tasks_completed": 0, "tasks_total": 1},
            ),
            run_id,
        )

    def test_record_success_episode(self, recorder, ar, store):
        """成功Runからエピソードが記録される"""
        # Arrange
        run_id = "run-success-001"
        self._seed_success_run(ar, run_id)

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
            goal="テストタスク",
        )

        # Assert
        assert episode.outcome == Outcome.SUCCESS
        assert episode.colony_id == "colony-1"
        assert episode.goal == "テストタスク"
        assert episode.failure_class is None

        # Storeに記録されている
        assert store.count("colony-1") == 1

    def test_record_failure_episode(self, recorder, ar, store):
        """失敗Runからエピソードが記録される"""
        # Arrange
        run_id = "run-fail-001"
        self._seed_failed_run(ar, run_id, reason="timeout occurred")

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
            goal="タイムアウトタスク",
        )

        # Assert
        assert episode.outcome == Outcome.FAILURE
        assert episode.failure_class == FailureClass.TIMEOUT

    def test_classify_implementation_error(self, recorder, ar, store):
        """コンパイルエラーがIMPLEMENTATION_ERRORに分類される"""
        # Arrange
        run_id = "run-impl-001"
        self._seed_failed_run(ar, run_id, reason="compile error in module")

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.failure_class == FailureClass.IMPLEMENTATION_ERROR

    def test_classify_environment_error(self, recorder, ar, store):
        """接続エラーがENVIRONMENT_ERRORに分類される"""
        # Arrange
        run_id = "run-env-001"
        self._seed_failed_run(ar, run_id, reason="connection refused")

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.failure_class == FailureClass.ENVIRONMENT_ERROR

    def test_classify_integration_error(self, recorder, ar, store):
        """結合エラーがINTEGRATION_ERRORに分類される"""
        # Arrange
        run_id = "run-integ-001"
        self._seed_failed_run(ar, run_id, reason="merge conflict detected")

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.failure_class == FailureClass.INTEGRATION_ERROR

    def test_record_with_template(self, recorder, ar, store):
        """テンプレート指定でエピソードが記録される"""
        # Arrange
        run_id = "run-template-001"
        self._seed_success_run(ar, run_id)

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
            template_used="speed",
        )

        # Assert
        assert episode.template_used == "speed"

    def test_record_with_parent_links(self, recorder, ar, store):
        """親エピソードリンク付きで記録される"""
        # Arrange
        run_id = "run-parent-001"
        self._seed_success_run(ar, run_id)

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
            parent_episode_ids=["ep-prev-001"],
        )

        # Assert
        assert "ep-prev-001" in episode.parent_episode_ids


# =========================================================================
# KPICalculator のテスト
# =========================================================================


class TestKPICalculator:
    """KPICalculator のテスト"""

    @pytest.fixture
    def store(self, tmp_path):
        """テスト用HoneycombStore"""
        return HoneycombStore(tmp_path)

    @pytest.fixture
    def calc(self, store):
        """テスト用KPICalculator"""
        return KPICalculator(store)

    def _add_episode(
        self,
        store: HoneycombStore,
        episode_id: str,
        outcome: Outcome = Outcome.SUCCESS,
        colony_id: str = "colony-1",
        template: str = "balanced",
        failure_class: FailureClass | None = None,
        duration: float = 100.0,
    ) -> Episode:
        """テスト用エピソードを追加"""
        ep = Episode(
            episode_id=episode_id,
            run_id=f"run-{episode_id}",
            colony_id=colony_id,
            outcome=outcome,
            template_used=template,
            failure_class=failure_class,
            duration_seconds=duration,
        )
        store.append(ep)
        return ep

    def test_calculate_all_empty(self, calc):
        """エピソードがない場合は全てNone"""
        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.correctness is None
        assert scores.repeatability is None
        assert scores.lead_time_seconds is None

    def test_correctness_all_success(self, calc, store):
        """全て成功なら正確性 = 1.0"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.SUCCESS)
        self._add_episode(store, "ep-3", Outcome.SUCCESS)

        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.correctness == 1.0

    def test_correctness_mixed(self, calc, store):
        """成功2/失敗1 → 正確性 ≈ 0.667"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.SUCCESS)
        self._add_episode(store, "ep-3", Outcome.FAILURE)

        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.correctness is not None
        assert abs(scores.correctness - 2 / 3) < 0.01

    def test_lead_time_average(self, calc, store):
        """リードタイムは平均所要時間"""
        # Arrange
        self._add_episode(store, "ep-1", duration=100.0)
        self._add_episode(store, "ep-2", duration=200.0)
        self._add_episode(store, "ep-3", duration=300.0)

        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.lead_time_seconds == 200.0

    def test_incident_rate(self, calc, store):
        """インシデント率: 失敗+Partialの比率"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.FAILURE)
        self._add_episode(store, "ep-3", Outcome.PARTIAL)
        self._add_episode(store, "ep-4", Outcome.SUCCESS)

        # Act
        scores = calc.calculate_all()

        # Assert: 2/4 = 0.5
        assert scores.incident_rate == 0.5

    def test_recurrence_rate_no_failures(self, calc, store):
        """失敗がなければ再発率 = 0.0"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.SUCCESS)

        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.recurrence_rate == 0.0

    def test_recurrence_rate_with_recurrence(self, calc, store):
        """同一FailureClassの再発がある場合"""
        # Arrange: TIMEOUT が2回（初発 + 再発1回）
        self._add_episode(
            store,
            "ep-1",
            Outcome.FAILURE,
            failure_class=FailureClass.TIMEOUT,
        )
        self._add_episode(
            store,
            "ep-2",
            Outcome.FAILURE,
            failure_class=FailureClass.TIMEOUT,
        )
        self._add_episode(
            store,
            "ep-3",
            Outcome.FAILURE,
            failure_class=FailureClass.IMPLEMENTATION_ERROR,
        )

        # Act
        scores = calc.calculate_all()

        # Assert: 再発1回 / 全失敗3回 ≈ 0.333
        assert scores.recurrence_rate is not None
        assert abs(scores.recurrence_rate - 1 / 3) < 0.01

    def test_calculate_by_colony(self, calc, store):
        """Colony単位でKPIを算出"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, colony_id="colony-a")
        self._add_episode(store, "ep-2", Outcome.FAILURE, colony_id="colony-b")

        # Act
        scores_a = calc.calculate_all(colony_id="colony-a")
        scores_b = calc.calculate_all(colony_id="colony-b")

        # Assert
        assert scores_a.correctness == 1.0
        assert scores_b.correctness == 0.0

    def test_calculate_summary(self, calc, store):
        """サマリーdict形式で取得"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(
            store,
            "ep-2",
            Outcome.FAILURE,
            failure_class=FailureClass.TIMEOUT,
        )

        # Act
        summary = calc.calculate_summary()

        # Assert
        assert summary["total_episodes"] == 2
        assert summary["outcomes"]["success"] == 1
        assert summary["outcomes"]["failure"] == 1
        assert summary["failure_classes"]["timeout"] == 1
        assert "kpi" in summary

    def test_repeatability_single_template(self, calc, store):
        """テンプレートが1種の場合、再現性 = 0.0"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, template="balanced")
        self._add_episode(store, "ep-2", Outcome.SUCCESS, template="balanced")
        self._add_episode(store, "ep-3", Outcome.FAILURE, template="balanced")

        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.repeatability == 0.0

    def test_summary_empty(self, calc):
        """エピソードがない場合のサマリー"""
        # Act
        summary = calc.calculate_summary()

        # Assert
        assert summary["total_episodes"] == 0
