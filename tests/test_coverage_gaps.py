"""Swarming Engine / Orchestrator / Conference Store の未カバーパステスト

カバレッジギャップを埋める:
- swarming/engine.py: _explain_selection の QUALITY/RECOVERY/Balanced 分岐
- queen_bee/orchestrator.py: callback=None でのスキップ、例外時 callback=None、failed 結果
- core/state/conference.py: _replay JSON エラー、_dict_to_projection 無効日時、ended_at あり
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from colonyforge.core.state.conference import (
    ConferenceProjection,
    ConferenceState,
    ConferenceStore,
)
from colonyforge.core.swarming.engine import SwarmingEngine
from colonyforge.core.swarming.models import SwarmingFeatures, TemplateName
from colonyforge.queen_bee.orchestrator import ColonyOrchestrator
from colonyforge.queen_bee.planner import PlannedTask, TaskPlan

# =========================================================================
# Swarming Engine: _explain_selection
# =========================================================================


class TestExplainSelection:
    """_explain_selection メソッドの全ブランチテスト"""

    def _engine(self) -> SwarmingEngine:
        return SwarmingEngine()

    def test_explain_quality_high_complexity_and_risk(self):
        """QUALITY テンプレート: 高複雑性 + 高リスク → 両方の理由を含む

        complexity >= 4 かつ risk >= 4 の場合、理由に「高複雑性」と「高リスク」が両方含まれる。
        """
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=5, risk=5, urgency=2),
            TemplateName.QUALITY,
        )

        # Assert
        assert "高複雑性" in result
        assert "高リスク" in result

    def test_explain_quality_high_risk_only(self):
        """QUALITY テンプレート: 高リスクのみ → 「高リスク」だけが理由に含まれる

        complexity < 4 かつ risk >= 4 の場合。
        """
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=2, risk=5, urgency=2),
            TemplateName.QUALITY,
        )

        # Assert
        assert "高リスク" in result
        assert "高複雑性" not in result

    def test_explain_quality_high_complexity_only(self):
        """QUALITY テンプレート: 高複雑性のみ → 「高複雑性」だけが理由に含まれる"""
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=5, risk=2, urgency=2),
            TemplateName.QUALITY,
        )

        # Assert
        assert "高複雑性" in result
        assert "高リスク" not in result

    def test_explain_recovery(self):
        """RECOVERY テンプレート → 「障害復旧」を含む説明"""
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=3, risk=3, urgency=3),
            TemplateName.RECOVERY,
        )

        # Assert
        assert "障害復旧" in result
        assert "Recovery" in result

    def test_explain_balanced(self):
        """BALANCED テンプレート → 「中程度」「Balanced」を含む説明"""
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=3, risk=3, urgency=3),
            TemplateName.BALANCED,
        )

        # Assert
        assert "中程度" in result
        assert "Balanced" in result

    def test_explain_speed(self):
        """SPEED テンプレート → 「低複雑性」「Speed」を含む説明"""
        # Arrange
        engine = self._engine()

        # Act
        result = engine._explain_selection(
            SwarmingFeatures(complexity=1, risk=1, urgency=5),
            TemplateName.SPEED,
        )

        # Assert
        assert "低複雑性" in result
        assert "Speed" in result


# =========================================================================
# ColonyOrchestrator: 未カバーパス
# =========================================================================


class TestOrchestratorUncoveredPaths:
    """ColonyOrchestrator の未カバーブランチテスト"""

    def _make_plan(self, *tasks: PlannedTask) -> TaskPlan:
        return TaskPlan(tasks=list(tasks), reasoning="test")

    @pytest.mark.asyncio
    async def test_skipped_task_without_callback(self):
        """callback=None で先行タスク失敗時、on_task_skipped が呼ばれずスキップ結果のみ記録される

        callback が None の場合、通知なしでスキップ結果が TaskContext に追加される。
        """
        # Arrange
        orch = ColonyOrchestrator()
        plan = self._make_plan(
            PlannedTask(task_id="t1", goal="失敗タスク"),
            PlannedTask(task_id="t2", goal="依存タスク", depends_on=["t1"]),
        )

        async def execute_fn(task_id: str, goal: str, context: Any) -> dict[str, Any]:
            if task_id == "t1":
                raise RuntimeError("失敗")
            return {"status": "completed", "result": "ok"}

        # Act: callback=None
        ctx = await orch.execute_plan(
            plan=plan, execute_fn=execute_fn, original_goal="テスト", run_id="run-1"
        )

        # Assert: t2 はスキップされている（failed_tasks に入る）
        assert "t2" in ctx.failed_tasks
        assert ctx.failed_tasks["t2"].status == "skipped"

    @pytest.mark.asyncio
    async def test_execute_fn_exception_without_callback(self):
        """callback=None で execute_fn が例外を投げた場合、failed 結果のみ記録される"""
        # Arrange
        orch = ColonyOrchestrator()
        plan = self._make_plan(
            PlannedTask(task_id="t1", goal="例外タスク"),
        )

        async def execute_fn(task_id: str, goal: str, context: Any) -> dict[str, Any]:
            raise ValueError("テストエラー")

        # Act
        ctx = await orch.execute_plan(
            plan=plan, execute_fn=execute_fn, original_goal="テスト", run_id="run-1"
        )

        # Assert
        assert "t1" in ctx.failed_tasks
        t1_result = ctx.failed_tasks["t1"]
        assert t1_result.status == "failed"
        assert "テストエラー" in (t1_result.error or "")

    @pytest.mark.asyncio
    async def test_failed_status_result(self):
        """execute_fn が status=failed を返した場合、failed 結果が記録される"""
        # Arrange
        orch = ColonyOrchestrator()
        plan = self._make_plan(
            PlannedTask(task_id="t1", goal="失敗結果タスク"),
        )

        async def execute_fn(task_id: str, goal: str, context: Any) -> dict[str, Any]:
            return {"status": "failed", "reason": "テスト失敗理由"}

        # Act
        ctx = await orch.execute_plan(
            plan=plan, execute_fn=execute_fn, original_goal="テスト", run_id="run-1"
        )

        # Assert
        assert "t1" in ctx.failed_tasks
        t1_result = ctx.failed_tasks["t1"]
        assert t1_result.status == "failed"
        assert t1_result.error == "テスト失敗理由"

    @pytest.mark.asyncio
    async def test_task_without_depends_on_has_no_context(self):
        """depends_on が空のタスクは context=None で execute_fn が呼ばれる"""
        # Arrange
        orch = ColonyOrchestrator()
        plan = self._make_plan(
            PlannedTask(task_id="t1", goal="独立タスク"),
        )
        received_context = []

        async def execute_fn(task_id: str, goal: str, context: Any) -> dict[str, Any]:
            received_context.append(context)
            return {"status": "completed", "result": "ok"}

        # Act
        await orch.execute_plan(
            plan=plan, execute_fn=execute_fn, original_goal="テスト", run_id="run-1"
        )

        # Assert: context は None
        assert received_context[0] is None


# =========================================================================
# ConferenceStore: 未カバーパス
# =========================================================================


class TestConferenceStoreUncoveredPaths:
    """ConferenceStore の未カバーブランチテスト"""

    def test_replay_with_invalid_json_line(self, tmp_path: Path):
        """_replay で JSON パースエラーがある行は警告ログのみで継続する

        壊れたデータベースファイルが一部の行で JSON が不正でも、
        正常な行は正しくロードされる。
        """
        # Arrange: 1行目は有効、2行目は不正JSON
        conf_dir = tmp_path / "conferences"
        conf_dir.mkdir()
        conf_file = conf_dir / "conferences.jsonl"

        valid_conf = {
            "conference_id": "conf-1",
            "hive_id": "hive-1",
            "topic": "テスト会議",
            "participants": [],
            "initiated_by": "user",
            "state": "active",
            "started_at": None,
            "ended_at": None,
            "decisions_made": [],
            "summary": "",
            "duration_seconds": 0,
        }
        conf_file.write_text(
            json.dumps(valid_conf) + "\n" + "INVALID JSON LINE\n",
            encoding="utf-8",
        )

        # Act
        store = ConferenceStore(base_path=tmp_path)

        # Assert: 有効な1件だけロードされている
        assert store.get("conf-1") is not None

    def test_replay_with_empty_lines(self, tmp_path: Path):
        """_replay で空行は無視される"""
        # Arrange
        conf_dir = tmp_path / "conferences"
        conf_dir.mkdir()
        conf_file = conf_dir / "conferences.jsonl"

        valid_conf = {
            "conference_id": "conf-2",
            "hive_id": "hive-2",
            "topic": "空行テスト",
            "participants": [],
            "initiated_by": "user",
            "state": "active",
            "started_at": None,
            "ended_at": None,
            "decisions_made": [],
            "summary": "",
            "duration_seconds": 0,
        }
        conf_file.write_text(
            "\n\n" + json.dumps(valid_conf) + "\n\n",
            encoding="utf-8",
        )

        # Act
        store = ConferenceStore(base_path=tmp_path)

        # Assert
        assert store.get("conf-2") is not None

    def test_dict_to_projection_with_invalid_datetime(self):
        """_dict_to_projection で日時が不正な文字列の場合 None に変換される"""
        # Arrange
        data = {
            "conference_id": "conf-dt",
            "hive_id": "hive-1",
            "topic": "日時テスト",
            "participants": [],
            "initiated_by": "user",
            "state": "active",
            "started_at": "not-a-date",
            "ended_at": "also-invalid",
            "decisions_made": [],
            "summary": "",
            "duration_seconds": 0,
        }

        # Act
        projection = ConferenceStore._dict_to_projection(data)

        # Assert: 不正な日時は None に変換
        assert projection.started_at is None
        assert projection.ended_at is None

    def test_projection_to_dict_with_ended_at(self):
        """_projection_to_dict で ended_at がある場合、ISO形式で出力される"""
        # Arrange
        now = datetime.now(UTC)
        projection = ConferenceProjection(
            conference_id="conf-end",
            hive_id="hive-1",
            topic="終了テスト",
            participants=[],
            initiated_by="user",
            state=ConferenceState.ENDED,
            started_at=now,
            ended_at=now,
        )

        # Act
        data = ConferenceStore._projection_to_dict(projection)

        # Assert
        assert data["ended_at"] == now.isoformat()
        assert data["started_at"] == now.isoformat()
        assert data["state"] == "ended"
