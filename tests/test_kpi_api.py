"""KPI API エンドポイントのテスト

M5-4: KPIダッシュボード用REST API のテスト。
基本KPI, 協調メトリクス, ゲート精度, 包括的評価サマリーの
各エンドポイントを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from colonyforge.api.helpers import clear_active_runs, set_ar
from colonyforge.api.server import app
from colonyforge.core.honeycomb import Episode, HoneycombStore, Outcome
from colonyforge.core.honeycomb.models import FailureClass


@pytest.fixture
def client(tmp_path):
    """テスト用クライアント（KPI APIテスト専用）"""
    set_ar(None)
    clear_active_runs()

    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("colonyforge.api.server.get_settings", return_value=mock_s),
        patch("colonyforge.api.helpers.get_settings", return_value=mock_s),
        patch("colonyforge.api.routes.kpi.get_settings", return_value=mock_s),
        TestClient(app) as c,
    ):
        yield c, tmp_path

    set_ar(None)
    clear_active_runs()


def _seed_episodes(vault_path, episodes_data: list[dict]) -> None:
    """テスト用エピソードをHoneycombStoreに投入"""
    store = HoneycombStore(vault_path / "Vault")
    for data in episodes_data:
        ep = Episode(
            episode_id=data.get("episode_id", "ep-1"),
            run_id=data.get("run_id", "run-1"),
            colony_id=data.get("colony_id", "colony-1"),
            outcome=data.get("outcome", Outcome.SUCCESS),
            duration_seconds=data.get("duration", 100.0),
            token_count=data.get("token_count", 500),
            failure_class=data.get("failure_class"),
            sentinel_intervention_count=data.get("sentinel_count", 0),
        )
        store.append(ep)


# =========================================================================
# GET /kpi/scores
# =========================================================================


class TestKPIScoresEndpoint:
    """GET /kpi/scores のテスト"""

    def test_scores_empty(self, client):
        """エピソードなしの場合、全KPIがnull"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/scores")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "kpi" in data
        assert data["kpi"]["correctness"] is None

    def test_scores_with_data(self, client):
        """エピソードがある場合、KPIが算出される"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "outcome": Outcome.SUCCESS},
                {
                    "episode_id": "ep-2",
                    "outcome": Outcome.FAILURE,
                    "failure_class": FailureClass.TIMEOUT,
                },
            ],
        )

        # Act
        response = c.get("/kpi/scores")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["kpi"]["correctness"] == 0.5

    def test_scores_by_colony(self, client):
        """Colony単位でKPIを取得"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "outcome": Outcome.SUCCESS, "colony_id": "col-a"},
                {"episode_id": "ep-2", "outcome": Outcome.FAILURE, "colony_id": "col-b"},
            ],
        )

        # Act
        response = c.get("/kpi/scores?colony_id=col-a")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["kpi"]["correctness"] == 1.0


# =========================================================================
# GET /kpi/summary
# =========================================================================


class TestKPISummaryEndpoint:
    """GET /kpi/summary のテスト"""

    def test_summary_empty(self, client):
        """エピソードなしの場合"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/summary")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_episodes"] == 0

    def test_summary_with_data(self, client):
        """エピソードがある場合、内訳を含む"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "outcome": Outcome.SUCCESS},
                {
                    "episode_id": "ep-2",
                    "outcome": Outcome.FAILURE,
                    "failure_class": FailureClass.TIMEOUT,
                },
            ],
        )

        # Act
        response = c.get("/kpi/summary")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_episodes"] == 2
        assert data["outcomes"]["success"] == 1
        assert data["failure_classes"]["timeout"] == 1


# =========================================================================
# GET /kpi/collaboration
# =========================================================================


class TestCollaborationEndpoint:
    """GET /kpi/collaboration のテスト"""

    def test_collaboration_basic(self, client):
        """協調メトリクスが算出される"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "token_count": 1000},
                {"episode_id": "ep-2", "token_count": 2000},
            ],
        )

        # Act
        response = c.get("/kpi/collaboration?guard_reject_count=1&guard_total_count=5")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "collaboration" in data
        assert abs(data["collaboration"]["rework_rate"] - 0.2) < 0.01
        assert abs(data["collaboration"]["cost_per_task_tokens"] - 1500.0) < 0.1

    def test_collaboration_empty(self, client):
        """カウンタ0の場合、rate系はnull"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/collaboration")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["collaboration"]["rework_rate"] is None


# =========================================================================
# GET /kpi/gate-accuracy
# =========================================================================


class TestGateAccuracyEndpoint:
    """GET /kpi/gate-accuracy のテスト"""

    def test_gate_accuracy_basic(self, client):
        """ゲート精度メトリクスが算出される"""
        # Arrange
        c, _ = client

        # Act
        response = c.get(
            "/kpi/gate-accuracy?"
            "guard_pass_count=7&guard_conditional_count=2&guard_fail_count=1"
            "&sentinel_alert_count=5&sentinel_false_alarm_count=1"
            "&total_monitoring_periods=100"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        gate = data["gate_accuracy"]
        assert abs(gate["guard_pass_rate"] - 0.7) < 0.01
        assert abs(gate["guard_conditional_pass_rate"] - 0.2) < 0.01
        assert abs(gate["guard_fail_rate"] - 0.1) < 0.01
        assert abs(gate["sentinel_detection_rate"] - 0.05) < 0.01
        assert abs(gate["sentinel_false_alarm_rate"] - 0.2) < 0.01

    def test_gate_accuracy_empty(self, client):
        """全カウンタ0の場合、全メトリクスnull"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/gate-accuracy")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["gate_accuracy"]["guard_pass_rate"] is None


# =========================================================================
# GET /kpi/evaluation
# =========================================================================


class TestEvaluationEndpoint:
    """GET /kpi/evaluation のテスト"""

    def test_evaluation_basic(self, client):
        """包括的評価サマリーが全セクションを含む"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "outcome": Outcome.SUCCESS, "colony_id": "a"},
                {
                    "episode_id": "ep-2",
                    "outcome": Outcome.FAILURE,
                    "colony_id": "b",
                    "failure_class": FailureClass.TIMEOUT,
                },
            ],
        )

        # Act
        response = c.get(
            "/kpi/evaluation?"
            "guard_pass_count=5&guard_conditional_count=2&guard_fail_count=1"
            "&guard_reject_count=1&guard_total_count=8"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_episodes"] == 2
        assert data["colony_count"] == 2
        assert "kpi" in data
        assert "collaboration" in data
        assert "gate_accuracy" in data
        assert data["outcomes"]["success"] == 1

    def test_evaluation_empty(self, client):
        """エピソードなしでも安全にレスポンス"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/evaluation")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_episodes"] == 0


# =========================================================================
# GET /kpi/colonies
# =========================================================================


class TestKPIColoniesEndpoint:
    """GET /kpi/colonies のテスト"""

    def test_colonies_empty(self, client):
        """エピソードなしの場合、空リスト"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/colonies")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["colonies"] == []
        assert data["count"] == 0

    def test_colonies_with_data(self, client):
        """エピソードがある場合、Colony IDリストを返す"""
        # Arrange
        c, tmp_path = client
        _seed_episodes(
            tmp_path,
            [
                {"episode_id": "ep-1", "colony_id": "col-a"},
                {"episode_id": "ep-2", "colony_id": "col-b"},
            ],
        )

        # Act
        response = c.get("/kpi/colonies")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert "col-a" in data["colonies"]
        assert "col-b" in data["colonies"]


# =========================================================================
# バリデーション
# =========================================================================


class TestKPIValidation:
    """クエリパラメータのバリデーションテスト"""

    def test_negative_count_rejected(self, client):
        """負のカウンタは422エラー"""
        # Arrange
        c, _ = client

        # Act
        response = c.get("/kpi/collaboration?guard_reject_count=-1")

        # Assert
        assert response.status_code == 422
