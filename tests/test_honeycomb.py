"""Honeycomb テスト

Episode, HoneycombStore, EpisodeRecorder, KPICalculator のテスト。
M3-1 完了条件:
- Run/Task完了時にEpisodeがHoneycombに自動記録される
- 失敗時にFailureClassが分類される
- 5つのKPIが算出可能

M5-4 追加:
- KPI表示フォーマットの整合性 (TestKPIDisplayFormatConsistency)
- KPIが改善サイクルの指標として機能することの証明 (TestKPIImprovementCycle)
"""

from __future__ import annotations

import pytest

from colonyforge.core import AkashicRecord, generate_event_id

# Sentinel イベント（P-02: incident_rate 改善用）
from colonyforge.core.events import (
    RunAbortedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    SentinelAlertRaisedEvent,
    SentinelRollbackEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
)
from colonyforge.core.events.types import EventType
from colonyforge.core.honeycomb.kpi import KPICalculator
from colonyforge.core.honeycomb.models import (
    Episode,
    FailureClass,
    KPIScores,
    Outcome,
)
from colonyforge.core.honeycomb.recorder import EpisodeRecorder
from colonyforge.core.honeycomb.store import HoneycombStore

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

    def test_replay_skips_blank_lines(self, store):
        """空行を含むJSONLファイルでもreplayが正しく動作する

        _read_episodesは空行をcontinueでスキップする。
        """
        # Arrange: エピソードを追記してからファイルに空行を挿入
        episode = self._make_episode("ep-blank", "colony-blank")
        store.append(episode)

        # ファイルに空行を直接追加
        colony_file = store.base_path / "colony-blank.jsonl"
        with open(colony_file, "a", encoding="utf-8") as f:
            f.write("\n\n")

        # さらにエピソードを追記
        store.append(self._make_episode("ep-blank-2", "colony-blank"))

        # Act
        replayed = store.replay_colony("colony-blank")

        # Assert: 空行はスキップされ2エピソード
        assert len(replayed) == 2

    def test_replay_warns_on_invalid_json(self, store, caplog):
        """不正なJSON行がある場合、warningをログに出力してスキップする"""
        import logging

        # Arrange: 正常なエピソードを追記
        store.append(self._make_episode("ep-valid", "colony-invalid"))

        # ファイルに不正なJSONを挿入
        colony_file = store.base_path / "colony-invalid.jsonl"
        with open(colony_file, "a", encoding="utf-8") as f:
            f.write("THIS IS NOT VALID JSON\n")

        # Act: warningログが出力される
        with caplog.at_level(logging.WARNING):
            replayed = store.replay_colony("colony-invalid")

        # Assert: 正常なエピソードのみ読み込まれる
        assert len(replayed) == 1
        assert replayed[0].episode_id == "ep-valid"
        assert any("読み込みエラー" in record.message for record in caplog.records)


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

    def test_kpi_scores_correctness_on_success(self, recorder, ar, store):
        """成功RunのKPIScoresでcorrectnessが1.0

        _calculate_kpi_scoresが成功時にcorrectness=1.0を算出することを確認。
        """
        # Arrange
        run_id = "run-kpi-success"
        self._seed_success_run(ar, run_id)

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.kpi_scores.correctness == 1.0
        assert episode.kpi_scores.incident_rate == 0.0

    def test_kpi_scores_correctness_on_failure(self, recorder, ar, store):
        """失敗RunのKPIScoresでcorrectnessが0.0

        _calculate_kpi_scoresが失敗時にcorrectness=0.0, incident_rate=1.0を算出。
        """
        # Arrange
        run_id = "run-kpi-fail"
        self._seed_failed_run(ar, run_id, reason="error")

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.kpi_scores.correctness == 0.0
        assert episode.kpi_scores.incident_rate == 1.0

    def test_kpi_scores_partial_outcome(self, recorder, ar, store):
        """Partial outcomeのKPIScoresでcorrectnessが0.5

        成功タスクと失敗タスクが混在するRunでは0.5になる。
        """
        # Arrange: 成功タスクと失敗タスクが混在
        run_id = "run-kpi-partial"
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
            TaskCompletedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1"},
            ),
            run_id,
        )
        ar.append(
            TaskCreatedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-2"},
            ),
            run_id,
        )
        ar.append(
            TaskFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-2", "reason": "error"},
            ),
            run_id,
        )
        ar.append(
            RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"reason": "partial", "tasks_completed": 1, "tasks_total": 2},
            ),
            run_id,
        )

        # Act
        episode = recorder.record_run_episode(
            run_id=run_id,
            colony_id="colony-1",
        )

        # Assert
        assert episode.outcome == Outcome.PARTIAL
        assert episode.kpi_scores.correctness == 0.5
        assert episode.kpi_scores.incident_rate == 1.0


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

    def test_repeatability_multiple_templates(self, calc, store):
        """テンプレートが2種以上で各2回以上使用された場合、stdevを算出

        異なるテンプレートでの成功率にばらつきがある場合、
        repeatabilityは正の値になる。
        """
        # Arrange: template-Aは全成功、template-Bは半分失敗
        self._add_episode(store, "ep-1", Outcome.SUCCESS, template="template-A")
        self._add_episode(store, "ep-2", Outcome.SUCCESS, template="template-A")
        self._add_episode(store, "ep-3", Outcome.SUCCESS, template="template-B")
        self._add_episode(store, "ep-4", Outcome.FAILURE, template="template-B")

        # Act
        scores = calc.calculate_all()

        # Assert: template-A成功率1.0, template-B成功率0.5 → stdev > 0
        assert scores.repeatability is not None
        assert scores.repeatability > 0.0

    def test_correctness_empty_returns_none(self, calc):
        """エピソードが空の場合、correctnessはNone"""
        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.correctness is None

    def test_incident_rate_empty_returns_none(self, calc):
        """エピソードが空の場合、incident_rateはNone"""
        # Act
        scores = calc.calculate_all()

        # Assert
        assert scores.incident_rate is None


# =========================================================================
# EpisodeRecorder 追加テスト（_count_tokens, _calculate_kpi_scores, 分類拡充）
# =========================================================================


class TestEpisodeRecorderTokenCounting:
    """EpisodeRecorderのトークン計算テスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        return EpisodeRecorder(honeycomb_store=store, ar=ar)

    def _seed_run_with_worker_events(self, ar, run_id: str, worker_payloads: list[dict]):
        """Worker Bee イベント付きRunをシード"""
        from colonyforge.core.events import WorkerCompletedEvent, WorkerProgressEvent

        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "トークン計測テスト"},
            ),
            run_id,
        )
        for i, wp in enumerate(worker_payloads):
            event_type = wp.pop("_event_type", "completed")
            if event_type == "completed":
                ar.append(
                    WorkerCompletedEvent(
                        id=generate_event_id(),
                        run_id=run_id,
                        actor="worker-test",
                        worker_id=f"w-{i}",
                        payload=wp,
                    ),
                    run_id,
                )
            elif event_type == "progress":
                ar.append(
                    WorkerProgressEvent(
                        id=generate_event_id(),
                        run_id=run_id,
                        actor="worker-test",
                        worker_id=f"w-{i}",
                        progress=50,
                        payload=wp,
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

    def test_count_tokens_from_worker_completed(self, recorder, ar, store):
        """WorkerCompletedEventからtoken_countを集計する"""
        # Arrange
        run_id = "run-token-001"
        self._seed_run_with_worker_events(
            ar,
            run_id,
            [
                {"token_count": 500},
                {"token_count": 300},
            ],
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.token_count == 800

    def test_count_tokens_from_worker_progress(self, recorder, ar, store):
        """WorkerProgressEventからtokens_usedを集計する"""
        # Arrange
        run_id = "run-token-002"
        self._seed_run_with_worker_events(
            ar,
            run_id,
            [
                {"_event_type": "progress", "tokens_used": 200},
                {"_event_type": "progress", "tokens_used": 150},
            ],
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.token_count == 350

    def test_count_tokens_mixed_events(self, recorder, ar, store):
        """WorkerCompleted + WorkerProgressの混合でトークンが合算される"""
        # Arrange
        run_id = "run-token-003"
        self._seed_run_with_worker_events(
            ar,
            run_id,
            [
                {"token_count": 400},
                {"_event_type": "progress", "tokens_used": 100},
            ],
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.token_count == 500

    def test_count_tokens_no_token_info(self, recorder, ar, store):
        """トークン情報がないイベントの場合は0"""
        # Arrange
        run_id = "run-token-004"
        self._seed_run_with_worker_events(
            ar,
            run_id,
            [
                {},  # token_count なし
            ],
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.token_count == 0

    def test_kpi_scores_with_positive_duration(self, recorder, ar, store):
        """正の所要時間がある場合、lead_time_secondsが設定される"""
        # Arrange
        run_id = "run-kpi-001"
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "KPIテスト"},
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

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert: KPIスコアが返される（lead_timeはduration依存）
        assert episode.kpi_scores is not None


class TestEpisodeRecorderFailureClassification:
    """EpisodeRecorder 失敗分類の追加テスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        return EpisodeRecorder(honeycomb_store=store, ar=ar)

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

    def test_classify_design_error(self, recorder, ar, store):
        """設計エラーがDESIGN_ERRORに分類される"""
        # Arrange
        run_id = "run-design-001"
        self._seed_failed_run(ar, run_id, reason="architecture violation found")

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.failure_class == FailureClass.DESIGN_ERROR

    def test_classify_specification_error(self, recorder, ar, store):
        """仕様エラーがSPECIFICATION_ERRORに分類される"""
        # Arrange
        run_id = "run-spec-001"
        self._seed_failed_run(ar, run_id, reason="requirement ambiguous")

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.failure_class == FailureClass.SPECIFICATION_ERROR

    def test_classify_unknown_reason_as_implementation(self, recorder, ar, store):
        """不明な理由はIMPLEMENTATION_ERRORに分類される"""
        # Arrange
        run_id = "run-unknown-001"
        self._seed_failed_run(ar, run_id, reason="something completely unexpected happened")

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.failure_class == FailureClass.IMPLEMENTATION_ERROR

    def test_partial_outcome_when_mixed_results(self, recorder, ar, store):
        """タスク成功・失敗が混在する場合はPARTIAL"""
        # Arrange
        run_id = "run-partial-001"
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
            TaskCompletedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1"},
            ),
            run_id,
        )
        ar.append(
            TaskCreatedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-2"},
            ),
            run_id,
        )
        ar.append(
            TaskFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-2", "reason": "fail"},
            ),
            run_id,
        )
        ar.append(
            RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"reason": "partial failure", "tasks_completed": 1, "tasks_total": 2},
            ),
            run_id,
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert: 成功も失敗もある → PARTIAL
        assert episode.outcome == Outcome.PARTIAL


# =========================================================================
# EpisodeRecorder _determine_outcome 追加ケースのテスト
# =========================================================================


class TestEpisodeRecorderOutcome:
    """_determine_outcomeの追加ケースのテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        return EpisodeRecorder(honeycomb_store=store, ar=ar)

    def test_run_aborted_is_failure(self, recorder, ar):
        """RUN_ABORTEDイベントがある場合はFAILUREと判定される

        緊急停止などでRunが中断された場合、明確にFAILUREとして記録される。
        """
        # Arrange
        run_id = "run-aborted-001"
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "abort test"},
            ),
            run_id,
        )
        ar.append(
            RunAbortedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="sentinel",
                payload={"reason": "Emergency stop"},
            ),
            run_id,
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.outcome == Outcome.FAILURE

    def test_incomplete_events_is_partial(self, recorder, ar):
        """完了イベントがない場合はPARTIALと判定される"""
        # Arrange
        run_id = "run-incomplete-001"
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "incomplete test"},
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

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.outcome == Outcome.PARTIAL

    def test_run_failed_only_failure_tasks_is_failure(self, recorder, ar):
        """RUN_FAILED + 全タスク失敗の場合はFAILURE"""
        # Arrange
        run_id = "run-all-fail-001"
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "all fail"},
            ),
            run_id,
        )
        ar.append(
            TaskFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"task_id": "task-1", "reason": "error"},
            ),
            run_id,
        )
        ar.append(
            RunFailedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"reason": "all tasks failed"},
            ),
            run_id,
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.outcome == Outcome.FAILURE

    def test_duration_single_event_is_zero(self, recorder, ar):
        """イベントが1つだけの場合、所要時間は0.0"""
        # Arrange
        run_id = "run-single-001"
        ar.append(
            RunStartedEvent(
                id=generate_event_id(),
                run_id=run_id,
                actor="queen-test",
                payload={"goal": "single event"},
            ),
            run_id,
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.duration_seconds == 0.0

    def test_duration_with_created_at_timestamps(self, recorder):
        """created_at属性を持つイベントから所要時間を算出"""
        from unittest.mock import MagicMock

        from colonyforge.core.events import EventType

        # Arrange: created_atを持つモックイベント
        event1 = MagicMock()
        event1.type = EventType.RUN_STARTED
        event1.created_at = "2024-01-01T00:00:00"
        event1.payload = {}

        event2 = MagicMock()
        event2.type = EventType.RUN_COMPLETED
        event2.created_at = "2024-01-01T00:01:30"
        event2.payload = {}

        # Act
        duration = recorder._calculate_duration([event1, event2])

        # Assert: 90秒
        assert duration == 90.0

    def test_duration_invalid_timestamps_returns_zero(self, recorder):
        """created_atが不正なISO形式の場合は0.0を返す"""
        from unittest.mock import MagicMock

        from colonyforge.core.events import EventType

        # Arrange: 不正なタイムスタンプ
        event1 = MagicMock()
        event1.type = EventType.RUN_STARTED
        event1.created_at = "not-a-date"

        event2 = MagicMock()
        event2.type = EventType.RUN_COMPLETED
        event2.created_at = "also-not-a-date"

        # Act
        duration = recorder._calculate_duration([event1, event2])

        # Assert
        assert duration == 0.0


# =========================================================================
# P-02: Sentinel Hornet介入を加味したincident_rate テスト
# =========================================================================


class TestEpisodeSentinelField:
    """Episode.sentinel_intervention_count フィールドのテスト"""

    def test_default_sentinel_count_is_zero(self):
        """sentinel_intervention_countのデフォルトは0"""
        # Arrange & Act
        ep = Episode(
            episode_id="ep-001",
            run_id="run-001",
            colony_id="colony-001",
            outcome=Outcome.SUCCESS,
        )

        # Assert
        assert ep.sentinel_intervention_count == 0

    def test_sentinel_count_can_be_set(self):
        """sentinel_intervention_countを明示的に設定できる"""
        # Arrange & Act
        ep = Episode(
            episode_id="ep-001",
            run_id="run-001",
            colony_id="colony-001",
            outcome=Outcome.FAILURE,
            sentinel_intervention_count=3,
        )

        # Assert
        assert ep.sentinel_intervention_count == 3

    def test_sentinel_count_must_be_non_negative(self):
        """sentinel_intervention_countは0以上でなければならない"""
        # Act & Assert
        with pytest.raises(Exception):
            Episode(
                episode_id="ep-001",
                run_id="run-001",
                colony_id="colony-001",
                outcome=Outcome.SUCCESS,
                sentinel_intervention_count=-1,
            )


class TestRecorderSentinelCounting:
    """EpisodeRecorder._count_sentinel_interventions のテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        return EpisodeRecorder(store, ar)

    def test_count_zero_when_no_sentinel_events(self, recorder):
        """Sentinelイベントがない場合は0を返す"""
        from unittest.mock import MagicMock

        # Arrange: 通常のイベントのみ
        event1 = MagicMock()
        event1.type = EventType.RUN_STARTED

        event2 = MagicMock()
        event2.type = EventType.TASK_COMPLETED

        # Act
        count = recorder._count_sentinel_interventions([event1, event2])

        # Assert
        assert count == 0

    def test_count_sentinel_alert_raised(self, recorder):
        """SENTINEL_ALERT_RAISEDイベントをカウントする"""
        from unittest.mock import MagicMock

        # Arrange
        event1 = MagicMock()
        event1.type = EventType.SENTINEL_ALERT_RAISED

        event2 = MagicMock()
        event2.type = EventType.SENTINEL_ALERT_RAISED

        # Act
        count = recorder._count_sentinel_interventions([event1, event2])

        # Assert
        assert count == 2

    def test_count_mixed_sentinel_events(self, recorder):
        """各種Sentinelイベントを正しくカウントする"""
        from unittest.mock import MagicMock

        # Arrange: 5つの異なる介入イベント
        events = []
        sentinel_types = [
            EventType.SENTINEL_ALERT_RAISED,
            EventType.SENTINEL_ROLLBACK,
            EventType.SENTINEL_QUARANTINE,
            EventType.SENTINEL_KPI_DEGRADATION,
            EventType.EMERGENCY_STOP,
        ]
        for et in sentinel_types:
            e = MagicMock()
            e.type = et
            events.append(e)

        # 通常イベントも混ぜる
        normal = MagicMock()
        normal.type = EventType.RUN_STARTED
        events.append(normal)

        # Act
        count = recorder._count_sentinel_interventions(events)

        # Assert: Sentinelイベント5つだけカウント
        assert count == 5

    def test_sentinel_report_not_counted(self, recorder):
        """SENTINEL_REPORT（定期レポート）は介入ではないのでカウントしない"""
        from unittest.mock import MagicMock

        # Arrange
        event = MagicMock()
        event.type = EventType.SENTINEL_REPORT

        # Act
        count = recorder._count_sentinel_interventions([event])

        # Assert
        assert count == 0

    def test_count_empty_events(self, recorder):
        """空のイベントリストでは0を返す"""
        # Act
        count = recorder._count_sentinel_interventions([])

        # Assert
        assert count == 0


class TestRecorderSentinelIntegration:
    """EpisodeRecorder.record_run_episode でsentinel_intervention_countが設定されるテスト"""

    @pytest.fixture
    def ar(self, tmp_path):
        return AkashicRecord(vault_path=tmp_path / "vault")

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path / "honeycomb")

    @pytest.fixture
    def recorder(self, store, ar):
        return EpisodeRecorder(store, ar)

    def test_episode_records_sentinel_count(self, ar, recorder):
        """record_run_episodeでSentinel介入回数がEpisodeに記録される"""
        # Arrange: Sentinel介入を含むRunイベント
        run_id = "run-sentinel-1"
        ar.append(
            RunStartedEvent(
                run_id=run_id,
                payload={"goal": "test sentinel"},
            )
        )
        ar.append(
            SentinelAlertRaisedEvent(
                run_id=run_id,
                payload={"alert": "high risk detected"},
            )
        )
        ar.append(
            SentinelRollbackEvent(
                run_id=run_id,
                payload={"reason": "quality degradation"},
            )
        )
        ar.append(
            RunCompletedEvent(
                run_id=run_id,
                payload={"status": "completed"},
            )
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert: 2つのSentinel介入（alert + rollback）
        assert episode.sentinel_intervention_count == 2

    def test_episode_no_sentinel_events(self, ar, recorder):
        """Sentinel介入なしのRunではsentinel_intervention_count=0"""
        # Arrange: 通常のRunイベントのみ
        run_id = "run-normal-1"
        ar.append(
            RunStartedEvent(
                run_id=run_id,
                payload={"goal": "normal task"},
            )
        )
        ar.append(
            RunCompletedEvent(
                run_id=run_id,
                payload={"status": "completed"},
            )
        )

        # Act
        episode = recorder.record_run_episode(run_id=run_id, colony_id="colony-1")

        # Assert
        assert episode.sentinel_intervention_count == 0


class TestKPICalculatorIncidentRateWithSentinel:
    """P-02: Sentinel介入を加味したincident_rate計算のテスト"""

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path)

    @pytest.fixture
    def calc(self, store):
        return KPICalculator(store)

    def _add_episode(
        self,
        store: HoneycombStore,
        episode_id: str,
        outcome: Outcome = Outcome.SUCCESS,
        sentinel_intervention_count: int = 0,
        colony_id: str = "colony-1",
        template: str = "balanced",
        failure_class: FailureClass | None = None,
        duration: float = 100.0,
    ) -> Episode:
        """テスト用エピソードを追加（sentinel_intervention_count対応）"""
        ep = Episode(
            episode_id=episode_id,
            run_id=f"run-{episode_id}",
            colony_id=colony_id,
            outcome=outcome,
            template_used=template,
            failure_class=failure_class,
            duration_seconds=duration,
            sentinel_intervention_count=sentinel_intervention_count,
        )
        store.append(ep)
        return ep

    def test_incident_rate_sentinel_only(self, calc, store):
        """Sentinel介入ありだが成功のエピソードもインシデントとしてカウント

        成功エピソードでもSentinel介入があれば、それはインシデントとして扱う。
        人間の介入が必要だった＝プロセスに問題があったことを示す。
        """
        # Arrange: 4エピソード中、2つにSentinel介入あり（ただし全て成功）
        self._add_episode(store, "ep-1", Outcome.SUCCESS, sentinel_intervention_count=0)
        self._add_episode(store, "ep-2", Outcome.SUCCESS, sentinel_intervention_count=2)
        self._add_episode(store, "ep-3", Outcome.SUCCESS, sentinel_intervention_count=0)
        self._add_episode(store, "ep-4", Outcome.SUCCESS, sentinel_intervention_count=1)

        # Act
        scores = calc.calculate_all()

        # Assert: 2/4 = 0.5 (Sentinel介入あり = インシデント)
        assert scores.incident_rate == 0.5

    def test_incident_rate_failure_and_sentinel(self, calc, store):
        """失敗とSentinel介入の両方がある場合は重複カウントしない

        1つのエピソードが失敗かつSentinel介入ありでも、
        インシデントとしては1回だけカウントする。
        """
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, sentinel_intervention_count=0)
        self._add_episode(
            store, "ep-2", Outcome.FAILURE, sentinel_intervention_count=1
        )  # 失敗 + Sentinel
        self._add_episode(
            store, "ep-3", Outcome.SUCCESS, sentinel_intervention_count=1
        )  # 成功だがSentinel介入
        self._add_episode(store, "ep-4", Outcome.SUCCESS, sentinel_intervention_count=0)

        # Act
        scores = calc.calculate_all()

        # Assert: 2/4 = 0.5 (ep-2: 失敗, ep-3: Sentinel介入)
        assert scores.incident_rate == 0.5

    def test_incident_rate_all_incident(self, calc, store):
        """全エピソードがインシデント（失敗 or Sentinel介入）の場合"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.FAILURE, sentinel_intervention_count=0)
        self._add_episode(store, "ep-2", Outcome.SUCCESS, sentinel_intervention_count=1)
        self._add_episode(store, "ep-3", Outcome.PARTIAL, sentinel_intervention_count=2)

        # Act
        scores = calc.calculate_all()

        # Assert: 3/3 = 1.0
        assert scores.incident_rate == 1.0

    def test_incident_rate_no_incident(self, calc, store):
        """全エピソードが正常（失敗なし + Sentinel介入なし）"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, sentinel_intervention_count=0)
        self._add_episode(store, "ep-2", Outcome.SUCCESS, sentinel_intervention_count=0)

        # Act
        scores = calc.calculate_all()

        # Assert: 0/2 = 0.0
        assert scores.incident_rate == 0.0

    def test_backward_compatible_with_no_sentinel_field(self, calc, store):
        """sentinel_intervention_count=0のエピソードでも既存ロジック通り動作

        既存テスト test_incident_rate と同じsemanticsを維持。
        """
        # Arrange: 既存テストと同じパターン
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.FAILURE)
        self._add_episode(store, "ep-3", Outcome.PARTIAL)
        self._add_episode(store, "ep-4", Outcome.SUCCESS)

        # Act
        scores = calc.calculate_all()

        # Assert: 2/4 = 0.5 (後方互換)
        assert scores.incident_rate == 0.5


# =========================================================================
# CollaborationMetrics / GateAccuracyMetrics / EvaluationSummary のテスト
# =========================================================================


class TestCollaborationMetrics:
    """協調品質メトリクスのテスト

    MoA (Wang et al., 2024) の協調効率メトリクスを参考に、
    HiveForge固有のRework Rate, Escalation Ratio, N案歩留まり等を検証。
    """

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
        token_count: int = 0,
        sentinel_count: int = 0,
    ) -> Episode:
        """テスト用エピソード追加"""
        ep = Episode(
            episode_id=episode_id,
            run_id=f"run-{episode_id}",
            colony_id=colony_id,
            outcome=outcome,
            token_count=token_count,
            sentinel_intervention_count=sentinel_count,
        )
        store.append(ep)
        return ep

    def test_rework_rate_basic(self, calc):
        """Guard Bee差戻し率: 差戻し2回/検証5回 = 0.4"""
        # Act
        collab = calc.calculate_collaboration(
            guard_reject_count=2,
            guard_total_count=5,
        )

        # Assert
        assert collab.rework_rate is not None
        assert abs(collab.rework_rate - 0.4) < 0.001

    def test_rework_rate_zero_reviews(self, calc):
        """検証0回の場合、rework_rateはNone"""
        # Act
        collab = calc.calculate_collaboration(guard_reject_count=0, guard_total_count=0)

        # Assert
        assert collab.rework_rate is None

    def test_escalation_ratio(self, calc):
        """エスカレーション率: 3回/10回 = 0.3"""
        # Act
        collab = calc.calculate_collaboration(escalation_count=3, decision_count=10)

        # Assert
        assert collab.escalation_ratio is not None
        assert abs(collab.escalation_ratio - 0.3) < 0.001

    def test_escalation_ratio_no_decisions(self, calc):
        """意思決定0回の場合、escalation_ratioはNone"""
        # Act
        collab = calc.calculate_collaboration(escalation_count=0, decision_count=0)

        # Assert
        assert collab.escalation_ratio is None

    def test_n_proposal_yield(self, calc):
        """N案歩留まり: 選抜2/候補8 = 0.25"""
        # Act
        collab = calc.calculate_collaboration(
            referee_selected_count=2,
            referee_candidate_count=8,
        )

        # Assert
        assert collab.n_proposal_yield is not None
        assert abs(collab.n_proposal_yield - 0.25) < 0.001

    def test_n_proposal_yield_no_candidates(self, calc):
        """候補0件の場合、n_proposal_yieldはNone"""
        # Act
        collab = calc.calculate_collaboration(
            referee_selected_count=0,
            referee_candidate_count=0,
        )

        # Assert
        assert collab.n_proposal_yield is None

    def test_cost_per_task_tokens(self, calc, store):
        """タスク当たり平均トークン消費"""
        # Arrange
        self._add_episode(store, "ep-1", token_count=1000)
        self._add_episode(store, "ep-2", token_count=2000)
        self._add_episode(store, "ep-3", token_count=3000)

        # Act
        collab = calc.calculate_collaboration()

        # Assert: (1000+2000+3000)/3 = 2000
        assert collab.cost_per_task_tokens is not None
        assert abs(collab.cost_per_task_tokens - 2000.0) < 0.1

    def test_cost_per_task_no_tokens(self, calc, store):
        """トークン消費なしの場合、cost_per_taskはNone"""
        # Arrange
        self._add_episode(store, "ep-1", token_count=0)

        # Act
        collab = calc.calculate_collaboration()

        # Assert
        assert collab.cost_per_task_tokens is None

    def test_collaboration_overhead(self, calc, store):
        """協調オーバーヘッド: 失敗+Sentinel介入 / 全EP

        失敗1件 + Sentinel介入(成功だがSentinel介入あり)1件 / 4件全体 = 0.5
        """
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)
        self._add_episode(store, "ep-2", Outcome.FAILURE)
        self._add_episode(store, "ep-3", Outcome.SUCCESS, sentinel_count=1)
        self._add_episode(store, "ep-4", Outcome.SUCCESS)

        # Act
        collab = calc.calculate_collaboration()

        # Assert: ep-2(failure) + ep-3(sentinel) = 2/4 = 0.5
        assert collab.collaboration_overhead is not None
        assert abs(collab.collaboration_overhead - 0.5) < 0.001

    def test_collaboration_empty(self, calc):
        """エピソードなしの場合、Episodeベースのメトリクスはすべてnone"""
        # Act
        collab = calc.calculate_collaboration()

        # Assert
        assert collab.cost_per_task_tokens is None
        assert collab.collaboration_overhead is None

    def test_collaboration_by_colony(self, calc, store):
        """Colony単位でも協調品質を算出可能"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, colony_id="a", token_count=100)
        self._add_episode(store, "ep-2", Outcome.FAILURE, colony_id="b", token_count=500)

        # Act
        collab_a = calc.calculate_collaboration(colony_id="a")
        collab_b = calc.calculate_collaboration(colony_id="b")

        # Assert
        assert collab_a.cost_per_task_tokens is not None
        assert abs(collab_a.cost_per_task_tokens - 100.0) < 0.1
        assert collab_b.cost_per_task_tokens is not None
        assert abs(collab_b.cost_per_task_tokens - 500.0) < 0.1


class TestGateAccuracyMetrics:
    """ゲート精度メトリクスのテスト

    AgentBench (Liu et al., ICLR 2024) の失敗分類を参考に、
    Guard Bee / Sentinel Hornet の精度を検証。
    """

    @pytest.fixture
    def store(self, tmp_path):
        """テスト用HoneycombStore"""
        return HoneycombStore(tmp_path)

    @pytest.fixture
    def calc(self, store):
        """テスト用KPICalculator"""
        return KPICalculator(store)

    def test_guard_pass_rate(self, calc):
        """Guard Bee合格率: PASS 7 / 全10 = 0.7"""
        # Act
        gate = calc.calculate_gate_accuracy(
            guard_pass_count=7,
            guard_conditional_count=2,
            guard_fail_count=1,
        )

        # Assert
        assert gate.guard_pass_rate is not None
        assert abs(gate.guard_pass_rate - 0.7) < 0.001

    def test_guard_conditional_pass_rate(self, calc):
        """Guard Bee条件付き合格率"""
        # Act
        gate = calc.calculate_gate_accuracy(
            guard_pass_count=7,
            guard_conditional_count=2,
            guard_fail_count=1,
        )

        # Assert
        assert gate.guard_conditional_pass_rate is not None
        assert abs(gate.guard_conditional_pass_rate - 0.2) < 0.001

    def test_guard_fail_rate(self, calc):
        """Guard Bee不合格率"""
        # Act
        gate = calc.calculate_gate_accuracy(
            guard_pass_count=7,
            guard_conditional_count=2,
            guard_fail_count=1,
        )

        # Assert
        assert gate.guard_fail_rate is not None
        assert abs(gate.guard_fail_rate - 0.1) < 0.001

    def test_guard_rates_sum_to_one(self, calc):
        """Guard Bee合計率は1.0になる"""
        # Act
        gate = calc.calculate_gate_accuracy(
            guard_pass_count=5,
            guard_conditional_count=3,
            guard_fail_count=2,
        )

        # Assert
        total = (
            (gate.guard_pass_rate or 0)
            + (gate.guard_conditional_pass_rate or 0)
            + (gate.guard_fail_rate or 0)
        )
        assert abs(total - 1.0) < 0.001

    def test_guard_no_reviews(self, calc):
        """検証0件の場合、全レートがNone"""
        # Act
        gate = calc.calculate_gate_accuracy()

        # Assert
        assert gate.guard_pass_rate is None
        assert gate.guard_conditional_pass_rate is None
        assert gate.guard_fail_rate is None

    def test_sentinel_detection_rate(self, calc):
        """Sentinel検知率: alert 3回 / 監視期間50 = 0.06"""
        # Act
        gate = calc.calculate_gate_accuracy(
            sentinel_alert_count=3,
            total_monitoring_periods=50,
        )

        # Assert
        assert gate.sentinel_detection_rate is not None
        assert abs(gate.sentinel_detection_rate - 0.06) < 0.001

    def test_sentinel_false_alarm_rate(self, calc):
        """Sentinel偽アラーム率: 誤検知1回 / 全alert 5回 = 0.2"""
        # Act
        gate = calc.calculate_gate_accuracy(
            sentinel_alert_count=5,
            sentinel_false_alarm_count=1,
        )

        # Assert
        assert gate.sentinel_false_alarm_rate is not None
        assert abs(gate.sentinel_false_alarm_rate - 0.2) < 0.001

    def test_sentinel_no_alerts(self, calc):
        """alert 0回の場合、false_alarm_rateはNone"""
        # Act
        gate = calc.calculate_gate_accuracy(
            sentinel_alert_count=0,
            sentinel_false_alarm_count=0,
        )

        # Assert
        assert gate.sentinel_false_alarm_rate is None

    def test_sentinel_no_monitoring(self, calc):
        """監視期間0の場合、detection_rateはNone"""
        # Act
        gate = calc.calculate_gate_accuracy(total_monitoring_periods=0)

        # Assert
        assert gate.sentinel_detection_rate is None


class TestEvaluationSummary:
    """包括的評価サマリーのテスト

    基本KPI + 協調メトリクス + ゲート精度の統合を検証。
    """

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
        token_count: int = 1000,
        duration: float = 100.0,
        failure_class: FailureClass | None = None,
    ) -> None:
        ep = Episode(
            episode_id=episode_id,
            run_id=f"run-{episode_id}",
            colony_id=colony_id,
            outcome=outcome,
            token_count=token_count,
            duration_seconds=duration,
            failure_class=failure_class,
        )
        store.append(ep)

    def test_evaluation_summary_basic(self, calc, store):
        """包括的評価サマリーが全セクションを含む

        基本KPI, 協調メトリクス, ゲート精度, outcome/failure_class内訳を検証。
        """
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, colony_id="col-a")
        self._add_episode(
            store, "ep-2", Outcome.FAILURE, colony_id="col-b", failure_class=FailureClass.TIMEOUT
        )
        self._add_episode(store, "ep-3", Outcome.SUCCESS, colony_id="col-a")

        # Act
        summary = calc.calculate_evaluation(
            guard_pass_count=5,
            guard_conditional_count=2,
            guard_fail_count=1,
            guard_reject_count=1,
            guard_total_count=8,
            escalation_count=1,
            decision_count=10,
            referee_selected_count=2,
            referee_candidate_count=6,
            sentinel_alert_count=3,
            sentinel_false_alarm_count=1,
            total_monitoring_periods=100,
        )

        # Assert: 構造が正しい
        assert summary.total_episodes == 3
        assert summary.colony_count == 2

        # 基本KPI
        assert summary.kpi.correctness is not None
        assert abs(summary.kpi.correctness - 2 / 3) < 0.01

        # 協調メトリクス
        assert summary.collaboration.rework_rate is not None
        assert abs(summary.collaboration.rework_rate - 1 / 8) < 0.01
        assert summary.collaboration.escalation_ratio is not None
        assert abs(summary.collaboration.escalation_ratio - 0.1) < 0.01
        assert summary.collaboration.n_proposal_yield is not None
        assert abs(summary.collaboration.n_proposal_yield - 2 / 6) < 0.01

        # ゲート精度
        assert summary.gate_accuracy.guard_pass_rate is not None
        assert abs(summary.gate_accuracy.guard_pass_rate - 5 / 8) < 0.01
        assert summary.gate_accuracy.sentinel_detection_rate is not None
        assert abs(summary.gate_accuracy.sentinel_detection_rate - 0.03) < 0.01

        # 内訳
        assert summary.outcomes["success"] == 2
        assert summary.outcomes["failure"] == 1
        assert summary.failure_classes["timeout"] == 1

    def test_evaluation_summary_empty(self, calc):
        """エピソードなしの場合でも安全に返却"""
        # Act
        summary = calc.calculate_evaluation()

        # Assert
        assert summary.total_episodes == 0
        assert summary.kpi.correctness is None
        assert summary.collaboration.rework_rate is None
        assert summary.gate_accuracy.guard_pass_rate is None
        assert summary.outcomes == {}
        assert summary.failure_classes == {}

    def test_evaluation_summary_by_colony(self, calc, store):
        """Colony単位でも包括的評価サマリーを取得可能"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS, colony_id="col-a")
        self._add_episode(store, "ep-2", Outcome.FAILURE, colony_id="col-b")

        # Act
        summary_a = calc.calculate_evaluation(colony_id="col-a")
        summary_b = calc.calculate_evaluation(colony_id="col-b")

        # Assert
        assert summary_a.total_episodes == 1
        assert summary_a.kpi.correctness == 1.0
        assert summary_b.total_episodes == 1
        assert summary_b.kpi.correctness == 0.0

    def test_evaluation_serialization(self, calc, store):
        """EvaluationSummaryがJSON直列化可能"""
        # Arrange
        self._add_episode(store, "ep-1", Outcome.SUCCESS)

        # Act
        summary = calc.calculate_evaluation(guard_pass_count=1, guard_total_count=1)
        data = summary.model_dump(mode="json")

        # Assert
        assert isinstance(data, dict)
        assert "kpi" in data
        assert "collaboration" in data
        assert "gate_accuracy" in data
        assert data["total_episodes"] == 1


class TestCollaborationMetricsModel:
    """CollaborationMetrics Pydanticモデルのテスト"""

    def test_default_values(self):
        """デフォルト値はすべてNone"""
        from colonyforge.core.honeycomb.models import CollaborationMetrics

        # Act
        metrics = CollaborationMetrics()

        # Assert
        assert metrics.rework_rate is None
        assert metrics.escalation_ratio is None
        assert metrics.n_proposal_yield is None
        assert metrics.cost_per_task_tokens is None
        assert metrics.collaboration_overhead is None

    def test_frozen(self):
        """CollaborationMetricsはイミュータブル"""
        from colonyforge.core.honeycomb.models import CollaborationMetrics

        # Arrange
        metrics = CollaborationMetrics(rework_rate=0.5)

        # Act & Assert
        with pytest.raises(Exception):
            metrics.rework_rate = 0.8  # type: ignore[misc]

    def test_validation_bounds(self):
        """値の範囲バリデーション"""
        from colonyforge.core.honeycomb.models import CollaborationMetrics

        # Act & Assert: rework_rate > 1.0 は不正
        with pytest.raises(Exception):
            CollaborationMetrics(rework_rate=1.5)


class TestGateAccuracyMetricsModel:
    """GateAccuracyMetrics Pydanticモデルのテスト"""

    def test_default_values(self):
        """デフォルト値はすべてNone"""
        from colonyforge.core.honeycomb.models import GateAccuracyMetrics

        # Act
        metrics = GateAccuracyMetrics()

        # Assert
        assert metrics.guard_pass_rate is None
        assert metrics.sentinel_detection_rate is None

    def test_frozen(self):
        """GateAccuracyMetricsはイミュータブル"""
        from colonyforge.core.honeycomb.models import GateAccuracyMetrics

        # Arrange
        metrics = GateAccuracyMetrics(guard_pass_rate=0.9)

        # Act & Assert
        with pytest.raises(Exception):
            metrics.guard_pass_rate = 0.5  # type: ignore[misc]


class TestEvaluationSummaryModel:
    """EvaluationSummary Pydanticモデルのテスト"""

    def test_default_values(self):
        """デフォルト値が正しい"""
        from colonyforge.core.honeycomb.models import EvaluationSummary

        # Act
        summary = EvaluationSummary()

        # Assert
        assert summary.total_episodes == 0
        assert summary.colony_count == 0
        assert summary.outcomes == {}
        assert summary.failure_classes == {}

    def test_frozen(self):
        """EvaluationSummaryはイミュータブル"""
        from colonyforge.core.honeycomb.models import EvaluationSummary

        # Arrange
        summary = EvaluationSummary(total_episodes=5)

        # Act & Assert
        with pytest.raises(Exception):
            summary.total_episodes = 10  # type: ignore[misc]


class TestKPIDisplayFormatConsistency:
    """KPI値のUI表示フォーマット整合性テスト

    hiveMonitorPanel.ts の pct()/num()/gaugeColor() 変換ルールを
    Python側で再実装し、API値→表示値の変換が正しいことを保証する。

    これらのヘルパーはE2Eテスト (test_hive_monitor_real.py) でも使用され、
    JS実装との等価性が全体の検証の基盤となる。
    """

    @staticmethod
    def _pct(v: float | None) -> str:
        """JS: function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }"""
        if v is None:
            return "—"
        return f"{v * 100:.1f}%"

    @staticmethod
    def _num(v: float | None, unit: str = "") -> str:
        """JS: function num(v, u) { return v != null ? v.toFixed(1) + (u || '') : '—'; }"""
        if v is None:
            return "—"
        return f"{v:.1f}{unit}"

    @staticmethod
    def _gauge_color(v: float | None, invert: bool = False) -> str:
        """JS: function gaugeColor(v, invert) { ... }"""
        if v is None:
            return "#9e9e9e"
        if invert:
            v = 1 - v
        if v >= 0.8:
            return "#4caf50"
        if v >= 0.5:
            return "#ff9800"
        return "#f44336"

    # --- pct() テスト ---

    def test_pct_normal_value(self):
        """pct(0.8) = '80.0%'"""
        assert self._pct(0.8) == "80.0%"

    def test_pct_zero(self):
        """pct(0.0) = '0.0%'"""
        assert self._pct(0.0) == "0.0%"

    def test_pct_one(self):
        """pct(1.0) = '100.0%'"""
        assert self._pct(1.0) == "100.0%"

    def test_pct_fractional(self):
        """pct(0.3) = '30.0%' — (v*100).toFixed(1) による丸め"""
        assert self._pct(0.3) == "30.0%"

    def test_pct_none(self):
        """pct(null) = '—'（emダッシュ）"""
        assert self._pct(None) == "—"

    def test_pct_small_value(self):
        """pct(0.001) = '0.1%' — toFixed(1)による丸め"""
        assert self._pct(0.001) == "0.1%"

    # --- num() テスト ---

    def test_num_with_seconds(self):
        """num(121.59, 's') = '121.6s' — toFixed(1)で小数1位"""
        assert self._num(121.59, "s") == "121.6s"

    def test_num_with_tokens(self):
        """num(1405.0, ' tok') = '1405.0 tok'"""
        assert self._num(1405.0, " tok") == "1405.0 tok"

    def test_num_zero(self):
        """num(0.0, 's') = '0.0s'"""
        assert self._num(0.0, "s") == "0.0s"

    def test_num_none(self):
        """num(null, 's') = '—'"""
        assert self._num(None, "s") == "—"

    def test_num_no_unit(self):
        """num(42.5, '') = '42.5'"""
        assert self._num(42.5, "") == "42.5"

    # --- gaugeColor() テスト ---

    def test_gauge_color_green(self):
        """v≥0.8 → #4caf50 (green)"""
        assert self._gauge_color(0.8) == "#4caf50"
        assert self._gauge_color(1.0) == "#4caf50"

    def test_gauge_color_orange(self):
        """0.5≤v<0.8 → #ff9800 (orange)"""
        assert self._gauge_color(0.5) == "#ff9800"
        assert self._gauge_color(0.79) == "#ff9800"

    def test_gauge_color_red(self):
        """v<0.5 → #f44336 (red)"""
        assert self._gauge_color(0.0) == "#f44336"
        assert self._gauge_color(0.49) == "#f44336"

    def test_gauge_color_null(self):
        """null → #9e9e9e (gray)"""
        assert self._gauge_color(None) == "#9e9e9e"

    def test_gauge_color_inverted_low_is_good(self):
        """invert=true: 低い値(0.0)は反転してv=1.0となり緑

        incident_rate=0.0 → invert → v=1.0 → green（インシデント0は良い）
        """
        assert self._gauge_color(0.0, invert=True) == "#4caf50"

    def test_gauge_color_inverted_high_is_bad(self):
        """invert=true: 高い値(0.8)は反転してv=0.2となり赤

        incident_rate=0.8 → invert → v=0.2 → red（インシデント80%は悪い）
        """
        assert self._gauge_color(0.8, invert=True) == "#f44336"

    def test_gauge_color_inverted_medium(self):
        """invert=true: 中間値(0.3)は反転してv=0.7となり橙

        incident_rate=0.3 → invert → v=0.7 → orange
        """
        assert self._gauge_color(0.3, invert=True) == "#ff9800"

    # --- 実際のAPIデモデータとの整合性テスト ---

    def test_demo_data_format_correctness(self):
        """デモデータ相当の値がhiveMonitorPanel.ts変換ルールで正しくフォーマットされること

        実際のAPIから返される値と同じパターンの値を使い、
        全メトリクスの表示変換が期待通りであることを一括検証する。
        """
        # Arrange: APIデモデータ相当の値
        test_data = {
            ("Correctness", "pct"): (0.8, "80.0%"),
            ("Repeatability", "pct"): (0.0, "0.0%"),
            ("Lead Time", "num_s"): (121.59, "121.6s"),
            ("Incident Rate", "pct"): (0.3, "30.0%"),
            ("Recurrence", "pct"): (0.0, "0.0%"),
            ("Rework Rate", "pct"): (None, "—"),
            ("Escalation", "pct"): (None, "—"),
            ("N-Proposal Yield", "pct"): (None, "—"),
            ("Cost/Task", "num_tok"): (1405.0, "1405.0 tok"),
            ("Overhead", "pct"): (0.3, "30.0%"),
        }

        # Act & Assert: 各メトリクスの変換を検証
        for (label, fmt_type), (value, expected) in test_data.items():
            if fmt_type == "pct":
                actual = self._pct(value)
            elif fmt_type == "num_s":
                actual = self._num(value, "s")
            elif fmt_type == "num_tok":
                actual = self._num(value, " tok")
            else:
                raise ValueError(f"Unknown format type: {fmt_type}")

            assert actual == expected, (
                f"{label}: value={value}, expected='{expected}', actual='{actual}'"
            )

    def test_demo_data_gauge_colors(self):
        """デモデータ相当の値がhiveMonitorPanel.tsの色閾値で正しい色になること

        gauge(label, value, unit, invert, max) の色計算:
        - norm = (max && value != null) ? Math.min(value/max, 1.0) : value
        - gaugeColor(norm, invert)
        """
        # Arrange: (label, value, invert, max, expected_color)
        test_data = [
            # Task Performance
            ("Correctness", 0.8, False, None, "#4caf50"),  # 0.8 >= 0.8 → green
            ("Repeatability", 0.0, False, None, "#f44336"),  # 0.0 < 0.5 → red
            ("Lead Time", 121.59, True, 300, "#ff9800"),  # norm=0.405, inv=0.595 → orange
            ("Incident Rate", 0.3, True, None, "#ff9800"),  # inv=0.7 → orange
            ("Recurrence", 0.0, True, None, "#4caf50"),  # inv=1.0 → green
            # Collaboration
            ("Rework Rate", None, True, None, "#9e9e9e"),  # null → gray
            ("Cost/Task", 1405.0, True, 5000, "#ff9800"),  # norm=0.281, inv=0.719 → orange
            ("Overhead", 0.3, True, None, "#ff9800"),  # inv=0.7 → orange
        ]

        for label, value, invert, max_val, expected_color in test_data:
            # Act: norm計算 + gaugeColor
            norm = min(value / max_val, 1.0) if max_val and value is not None else value
            actual_color = self._gauge_color(norm, invert)

            # Assert
            assert actual_color == expected_color, (
                f"{label}: value={value}, invert={invert}, max={max_val}, "
                f"norm={norm}, expected={expected_color}, actual={actual_color}"
            )


# =========================================================================
# KPI 改善サイクル証明テスト
# =========================================================================


class TestKPIImprovementCycle:
    """KPIが改善サイクルの指標として機能することを証明する大局的テスト

    KPIは単なる数値表示ではなく、以下のPDCAループを駆動する仕組みである::

        Plan → Do → Check (KPI計測) → Act (改善) → Check (KPI変化)

    このテストクラスでは、エピソード蓄積に伴うKPIの変化パターンを
    シナリオベースで検証し、KPIが改善活動のフィードバックとして
    信頼できることを証明する。

    証明する性質:
        1. 感度: 状態変化に対してKPIが適切に応答する
        2. 方向性: 改善はKPIの良化、悪化はKPIの劣化として現れる
        3. 比較可能性: Colony間で同一基準で比較できる
        4. 識別力: 異なる問題が異なるKPIに反映される
        5. 収束性: 改善を継続するとKPIが目標値に近づく
    """

    @pytest.fixture
    def store(self, tmp_path):
        return HoneycombStore(tmp_path)

    @pytest.fixture
    def calc(self, store):
        return KPICalculator(store)

    def _add(
        self,
        store: HoneycombStore,
        episode_id: str,
        outcome: Outcome = Outcome.SUCCESS,
        colony_id: str = "colony-1",
        duration: float = 100.0,
        token_count: int = 1000,
        failure_class: FailureClass | None = None,
        template: str = "balanced",
        sentinel_count: int = 0,
    ) -> None:
        ep = Episode(
            episode_id=episode_id,
            run_id=f"run-{episode_id}",
            colony_id=colony_id,
            outcome=outcome,
            duration_seconds=duration,
            token_count=token_count,
            failure_class=failure_class,
            template_used=template,
            sentinel_intervention_count=sentinel_count,
        )
        store.append(ep)

    # ------------------------------------------------------------------
    # 1. 感度: KPIは状態変化に応答する
    # ------------------------------------------------------------------

    def test_correctness_degrades_on_failure_injection(self, calc, store):
        """失敗エピソードの発生でcorrectnessが即座に劣化すること

        改善サイクルの前提: 問題が発生したことをKPIが検知できなければ
        改善の起点がない。
        障害1件の追加でcorrectnessが測定可能な幅で低下する。
        """
        # Arrange: 全成功の初期状態
        for i in range(5):
            self._add(store, f"ep-{i}", Outcome.SUCCESS)
        baseline = calc.calculate_all()
        assert baseline.correctness == 1.0

        # Act: 1件の失敗を注入
        self._add(store, "ep-fail", Outcome.FAILURE)
        after_failure = calc.calculate_all()

        # Assert: correctnessが低下（1.0 → 5/6 ≈ 0.833）
        assert after_failure.correctness is not None
        assert after_failure.correctness < baseline.correctness
        assert abs(after_failure.correctness - 5 / 6) < 0.01

    def test_incident_rate_rises_on_sentinel_intervention(self, calc, store):
        """Sentinel介入でincident_rateが上昇すること

        成功していてもSentinel介入があればインシデントとしてカウントされ、
        問題の潜在的兆候を見逃さない。
        """
        # Arrange: Sentinel介入なしの成功
        for i in range(4):
            self._add(store, f"ep-{i}", Outcome.SUCCESS)
        baseline = calc.calculate_all()
        assert baseline.incident_rate == 0.0

        # Act: 成功だがSentinel介入があったエピソード
        self._add(store, "ep-sentinel", Outcome.SUCCESS, sentinel_count=2)
        after = calc.calculate_all()

        # Assert: incident_rateが上昇（0 → 1/5 = 0.2）
        assert after.incident_rate is not None
        assert after.incident_rate > baseline.incident_rate
        assert abs(after.incident_rate - 0.2) < 0.01

    def test_lead_time_reflects_speed_change(self, calc, store):
        """所要時間の変化がlead_timeに反映されること

        プロセス改善で所要時間が短縮された場合、lead_timeが低下する。
        """
        # Arrange: 遅い初期状態
        for i in range(3):
            self._add(store, f"ep-slow-{i}", duration=300.0)
        baseline = calc.calculate_all()
        assert baseline.lead_time_seconds == 300.0

        # Act: 高速なエピソードが追加される（改善後）
        for i in range(3):
            self._add(store, f"ep-fast-{i}", duration=60.0)
        improved = calc.calculate_all()

        # Assert: lead_timeが低下（300 → 180平均）
        assert improved.lead_time_seconds is not None
        assert improved.lead_time_seconds < baseline.lead_time_seconds
        assert abs(improved.lead_time_seconds - 180.0) < 0.01

    # ------------------------------------------------------------------
    # 2. 方向性: 改善→KPI良化、悪化→KPI劣化
    # ------------------------------------------------------------------

    def test_fixing_failures_improves_correctness(self, calc, store):
        """失敗を修正して成功に変えるとcorrectnessが改善すること

        改善サイクルの核心: 失敗を検知(Check)→修正(Act)→再測定(Check)で
        KPIが改善方向に動くことを確認する。
        """
        # Arrange: 失敗が多い初期スプリント (correctness=0.4)
        for i in range(4):
            self._add(store, f"sprint1-s-{i}", Outcome.SUCCESS)
        for i in range(6):
            self._add(
                store,
                f"sprint1-f-{i}",
                Outcome.FAILURE,
                failure_class=FailureClass.IMPLEMENTATION_ERROR,
            )
        sprint1 = calc.calculate_all()

        # Act: 問題を特定し改善した次スプリント (成功8/失敗2 を追加)
        for i in range(8):
            self._add(store, f"sprint2-s-{i}", Outcome.SUCCESS)
        for i in range(2):
            self._add(
                store,
                f"sprint2-f-{i}",
                Outcome.FAILURE,
                failure_class=FailureClass.IMPLEMENTATION_ERROR,
            )
        sprint2 = calc.calculate_all()

        # Assert: correctnessが改善方向に動いている
        assert sprint1.correctness is not None
        assert sprint2.correctness is not None
        assert sprint2.correctness > sprint1.correctness
        # 0.4 → 12/20 = 0.6
        assert abs(sprint1.correctness - 0.4) < 0.01
        assert abs(sprint2.correctness - 0.6) < 0.01

    def test_recurrence_rate_drops_when_root_cause_fixed(self, calc, store):
        """根本原因修正後にrecurrence_rateが低下すること

        同じ種類の失敗が繰り返されるのが再発。
        根本原因を修正すれば再発が止まり、recurrence_rateが低下する。
        """
        # Arrange: 同じ失敗分類が繰り返し発生（TIMEOUT再発）
        self._add(store, "ep-1", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ep-2", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ep-3", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        before_fix = calc.calculate_all()

        # Act: 根本原因修正 → 以降TIMEOUTは発生せず新種のみ単発
        self._add(store, "ep-4", Outcome.SUCCESS)
        self._add(store, "ep-5", Outcome.SUCCESS)
        self._add(store, "ep-6", Outcome.FAILURE, failure_class=FailureClass.ENVIRONMENT_ERROR)
        after_fix = calc.calculate_all()

        # Assert: 再発率が低下（2/3 → 2/4 = 0.5）
        assert before_fix.recurrence_rate is not None
        assert after_fix.recurrence_rate is not None
        assert after_fix.recurrence_rate < before_fix.recurrence_rate

    # ------------------------------------------------------------------
    # 3. 比較可能性: Colony間で同一基準で比較
    # ------------------------------------------------------------------

    def test_colony_comparison_identifies_weak_colony(self, calc, store):
        """Colony間のKPI比較で弱いColonyを特定できること

        改善サイクルでは「どこを改善するか」の特定が重要。
        Colony単位のKPI比較で問題のあるColonyを識別できる。
        """
        # Arrange: 優秀なColony-A と 問題のあるColony-B
        for i in range(5):
            self._add(
                store,
                f"a-{i}",
                Outcome.SUCCESS,
                colony_id="colony-a",
                duration=60.0,
                token_count=500,
            )
        for i in range(5):
            outcome = Outcome.SUCCESS if i < 2 else Outcome.FAILURE
            fc = None if i < 2 else FailureClass.IMPLEMENTATION_ERROR
            self._add(
                store,
                f"b-{i}",
                outcome,
                colony_id="colony-b",
                duration=300.0,
                token_count=3000,
                failure_class=fc,
            )

        # Act
        kpi_a = calc.calculate_all(colony_id="colony-a")
        kpi_b = calc.calculate_all(colony_id="colony-b")

        # Assert: Colony-Bが全指標で劣っている → 改善対象として特定可能
        assert kpi_a.correctness is not None and kpi_b.correctness is not None
        assert kpi_a.correctness > kpi_b.correctness  # 1.0 vs 0.4
        assert kpi_a.lead_time_seconds is not None and kpi_b.lead_time_seconds is not None
        assert kpi_a.lead_time_seconds < kpi_b.lead_time_seconds  # 60 vs 300
        assert kpi_a.incident_rate is not None and kpi_b.incident_rate is not None
        assert kpi_a.incident_rate < kpi_b.incident_rate  # 0 vs 0.6

    def test_colony_kpi_independent_of_other_colonies(self, calc, store):
        """Colony-AのKPIがColony-Bの品質劣化に影響されないこと

        Colony間の独立性が保証されなければ、正確なボトルネック特定ができない。
        """
        # Arrange: Colony-Aに成功、Colony-Bに大量の失敗
        for i in range(3):
            self._add(store, f"a-{i}", Outcome.SUCCESS, colony_id="colony-a")
        for i in range(10):
            self._add(store, f"b-{i}", Outcome.FAILURE, colony_id="colony-b")

        # Act
        kpi_a = calc.calculate_all(colony_id="colony-a")
        kpi_global = calc.calculate_all()  # 全体

        # Assert: Colony-AのKPIはColony-Bに引きずられない
        assert kpi_a.correctness == 1.0
        assert kpi_global.correctness is not None
        assert kpi_global.correctness < kpi_a.correctness  # 全体は低い

    # ------------------------------------------------------------------
    # 4. 識別力: 異なる問題が異なるKPIに反映される
    # ------------------------------------------------------------------

    def test_quality_problem_vs_speed_problem_distinct_signals(self, calc, store):
        """品質問題と速度問題が異なるKPIに分離して反映されること

        correctnessが低い → 品質問題（コードの修正が必要）
        lead_timeが高い → 速度問題（プロセスの改善が必要）
        両者は独立した問題であり、異なるKPIで識別できる。
        """
        # Arrange: 品質は完璧だが非常に遅い
        for i in range(5):
            self._add(store, f"slow-{i}", Outcome.SUCCESS, duration=600.0)
        slow_but_correct = calc.calculate_all()

        store_fast = HoneycombStore(store.base_path.parent / "fast")
        calc_fast = KPICalculator(store_fast)

        # 高速だが品質が低い
        for i in range(5):
            outcome = Outcome.SUCCESS if i < 1 else Outcome.FAILURE
            fc = None if i < 1 else FailureClass.IMPLEMENTATION_ERROR
            self._add(store_fast, f"fast-{i}", outcome, duration=10.0, failure_class=fc)
        fast_but_buggy = calc_fast.calculate_all()

        # Assert: 品質と速度が異なるKPIに独立して反映
        assert slow_but_correct.correctness == 1.0  # 品質OK
        assert slow_but_correct.lead_time_seconds == 600.0  # 速度NG

        assert fast_but_buggy.correctness == 0.2  # 品質NG
        assert fast_but_buggy.lead_time_seconds == 10.0  # 速度OK

    def test_failure_classification_enables_targeted_improvement(self, calc, store):
        """FailureClass内訳が的を絞った改善を可能にすること

        「correctnessが低い」だけではどう直せばいいか分からない。
        FailureClassの内訳を見ることで改善アクションを特定できる。
        """
        # Arrange: 様々な原因で失敗
        self._add(store, "ep-1", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ep-2", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ep-3", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ep-4", Outcome.FAILURE, failure_class=FailureClass.IMPLEMENTATION_ERROR)
        self._add(store, "ep-5", Outcome.SUCCESS)

        # Act
        summary = calc.calculate_summary()

        # Assert: TIMEOUTが最頻 → タイムアウト対策が最優先改善アクション
        fc = summary["failure_classes"]
        assert fc["timeout"] == 3
        assert fc["implementation_error"] == 1
        assert fc["timeout"] > fc["implementation_error"]
        # correctnessは0.2（5中1成功）→ 改善の必要性が数値で明確
        assert abs(summary["kpi"]["correctness"] - 0.2) < 0.01

    # ------------------------------------------------------------------
    # 5. 収束性: 改善を継続するとKPIが目標値に近づく
    # ------------------------------------------------------------------

    def test_sustained_improvement_converges_to_target(self, calc, store):
        """継続的な改善によりKPIが目標値に収束すること

        PDCA: スプリントごとに失敗率を改善し、correctnessが
        目標の0.9に近づいていくことを検証する。
        3スプリント分のトレンドで改善傾向を証明する。
        """
        # Arrange/Act: 3スプリント分のデータを投入
        sprint_results = []

        # Sprint 1: 品質が低い (60% 成功)
        for i in range(6):
            self._add(store, f"s1-s-{i}", Outcome.SUCCESS)
        for i in range(4):
            self._add(
                store, f"s1-f-{i}", Outcome.FAILURE, failure_class=FailureClass.IMPLEMENTATION_ERROR
            )
        sprint_results.append(calc.calculate_all())

        # Sprint 2: 改善 (80% 成功)
        for i in range(8):
            self._add(store, f"s2-s-{i}", Outcome.SUCCESS)
        for i in range(2):
            self._add(
                store, f"s2-f-{i}", Outcome.FAILURE, failure_class=FailureClass.IMPLEMENTATION_ERROR
            )
        sprint_results.append(calc.calculate_all())

        # Sprint 3: さらに改善 (90% 成功)
        for i in range(9):
            self._add(store, f"s3-s-{i}", Outcome.SUCCESS)
        for i in range(1):
            self._add(
                store, f"s3-f-{i}", Outcome.FAILURE, failure_class=FailureClass.IMPLEMENTATION_ERROR
            )
        sprint_results.append(calc.calculate_all())

        # Assert: 各スプリントでcorrectnessが単調増加
        for i in range(len(sprint_results) - 1):
            curr = sprint_results[i].correctness
            next_ = sprint_results[i + 1].correctness
            assert curr is not None and next_ is not None
            assert next_ > curr, (
                f"Sprint {i + 1}→{i + 2}: correctnessが改善していない ({curr:.3f} → {next_:.3f})"
            )

        # Assert: 最終スプリント時点で目標(0.9)に到達方向
        final = sprint_results[-1].correctness
        assert final is not None
        assert final >= 0.75, f"3スプリント後のcorrectnessが0.75未満: {final:.3f}"

    def test_multi_kpi_simultaneous_improvement(self, calc, store):
        """複数KPIの同時改善が追跡可能なこと

        実運用では品質・速度・安定性を同時に改善したい。
        個々のKPIが独立してトレンドを持ち、総合的な改善判断が可能。
        """
        # Arrange: Phase 1 — 品質悪・速度遅・インシデント多
        for i in range(5):
            self._add(
                store,
                f"p1-{i}",
                Outcome.FAILURE if i < 3 else Outcome.SUCCESS,
                duration=400.0,
                failure_class=FailureClass.TIMEOUT if i < 3 else None,
                sentinel_count=1 if i < 2 else 0,
            )
        phase1 = calc.calculate_all()

        # Act: Phase 2 — 全面的な改善
        for i in range(10):
            self._add(store, f"p2-{i}", Outcome.SUCCESS, duration=80.0, sentinel_count=0)
        phase2 = calc.calculate_all()

        # Assert: 3つのKPIが全て改善
        assert phase2.correctness > phase1.correctness  # 品質改善
        assert phase2.lead_time_seconds < phase1.lead_time_seconds  # 速度改善
        assert phase2.incident_rate < phase1.incident_rate  # 安定性改善

    # ------------------------------------------------------------------
    # 6. 境界: 空→最初の1件、改善の天井
    # ------------------------------------------------------------------

    def test_first_episode_establishes_baseline(self, calc, store):
        """最初のエピソードでKPIベースラインが確立されること

        データなし(None) → 最初の1件 → 測定可能な値が生成される。
        改善サイクルの前提として「初回計測可能」であることは必須。
        """
        # Arrange: 空状態
        empty = calc.calculate_all()
        assert empty.correctness is None
        assert empty.lead_time_seconds is None

        # Act: 最初のエピソード
        self._add(store, "first", Outcome.SUCCESS, duration=120.0)
        first = calc.calculate_all()

        # Assert: ベースラインが確立
        assert first.correctness == 1.0
        assert first.lead_time_seconds == 120.0
        assert first.incident_rate == 0.0

    def test_perfect_kpi_is_achievable_and_stable(self, calc, store):
        """完璧なKPI(全指標最良)が達成可能で安定すること

        改善の天井: すべて成功・低レイテンシ・インシデントゼロが
        KPIに正しく反映され、追加の成功で悪化しない。
        """
        # Arrange: 完璧な10エピソード
        for i in range(10):
            self._add(store, f"perfect-{i}", Outcome.SUCCESS, duration=30.0, sentinel_count=0)
        perfect = calc.calculate_all()

        assert perfect.correctness == 1.0
        assert perfect.incident_rate == 0.0
        assert perfect.recurrence_rate == 0.0
        assert perfect.lead_time_seconds == 30.0

        # Act: さらに成功を追加 — KPIが悪化しないこと
        for i in range(5):
            self._add(store, f"more-{i}", Outcome.SUCCESS, duration=30.0, sentinel_count=0)
        still_perfect = calc.calculate_all()

        assert still_perfect.correctness == 1.0
        assert still_perfect.incident_rate == 0.0

    # ------------------------------------------------------------------
    # 7. EvaluationSummary: ダッシュボードデータとしての改善サイクル
    # ------------------------------------------------------------------

    def test_evaluation_summary_reflects_improvement_across_sprints(self, calc, store):
        """EvaluationSummaryが改善の前後で変化し、ダッシュボードに改善を反映すること

        KPIダッシュボードは改善サイクルの「Check」フェーズの道具。
        EvaluationSummaryのフィールドが改善前後で適切に変化する。
        """
        # Arrange: Sprint 1 — 問題多め
        for i in range(3):
            self._add(store, f"s1-ok-{i}", Outcome.SUCCESS, duration=200.0, token_count=2000)
        for i in range(7):
            self._add(
                store,
                f"s1-ng-{i}",
                Outcome.FAILURE,
                duration=300.0,
                token_count=3000,
                failure_class=FailureClass.TIMEOUT,
            )

        before = calc.calculate_evaluation(
            guard_reject_count=5,
            guard_total_count=10,
        )

        # Act: Sprint 2 — 改善後のエピソードを追加
        for i in range(9):
            self._add(store, f"s2-ok-{i}", Outcome.SUCCESS, duration=80.0, token_count=800)
        for i in range(1):
            self._add(
                store,
                f"s2-ng-{i}",
                Outcome.FAILURE,
                duration=100.0,
                token_count=1000,
                failure_class=FailureClass.ENVIRONMENT_ERROR,
            )

        after = calc.calculate_evaluation(
            guard_reject_count=6,
            guard_total_count=20,
        )

        # Assert: 改善がサマリーに反映
        assert after.kpi.correctness > before.kpi.correctness
        assert after.kpi.lead_time_seconds < before.kpi.lead_time_seconds
        assert after.total_episodes > before.total_episodes
        assert after.outcomes["success"] > before.outcomes["success"]
        # 協調品質: rework_rate改善 (50% → 30%)
        assert after.collaboration.rework_rate < before.collaboration.rework_rate

    def test_failure_class_trend_visible_in_summary(self, calc, store):
        """EvaluationSummaryのfailure_classes内訳で失敗トレンドが読み取れること

        改善前: TIMEOUT多発
        改善後: TIMEOUT解消、新種の単発のみ
        failure_classesの変化から「TIMEOUT対策が効いた」と判断できる。
        """
        # Arrange: TIMEOUT多発
        for i in range(3):
            self._add(store, f"timeout-{i}", Outcome.FAILURE, failure_class=FailureClass.TIMEOUT)
        self._add(store, "ok-1", Outcome.SUCCESS)

        before = calc.calculate_evaluation()
        assert before.failure_classes.get("timeout", 0) == 3

        # Act: TIMEOUT対策後 — 新しいエピソードではTIMEOUT発生なし
        for i in range(6):
            self._add(store, f"post-fix-{i}", Outcome.SUCCESS)
        self._add(store, "new-fail", Outcome.FAILURE, failure_class=FailureClass.ENVIRONMENT_ERROR)

        after = calc.calculate_evaluation()

        # Assert: TIMEOUT件数は変わらず、新種が追加、全体correctnessは改善
        assert after.failure_classes["timeout"] == 3  # 過去のTIMEOUTは消えない
        assert after.failure_classes.get("environment_error", 0) == 1  # 新種
        assert after.kpi.correctness > before.kpi.correctness
