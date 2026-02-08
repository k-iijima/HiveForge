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
    RunAbortedEvent,
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
        from hiveforge.core.events import WorkerCompletedEvent, WorkerProgressEvent

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

        from hiveforge.core.events import EventType

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

        from hiveforge.core.events import EventType

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
