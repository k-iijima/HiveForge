"""
Direct Intervention API テスト

ユーザー直接介入、Queen直訴、BeekeeperフィードバックのAPIテスト。
"""

import pytest
from fastapi.testclient import TestClient

from hiveforge.api.server import app


@pytest.fixture
def client():
    """テスト用クライアント"""
    return TestClient(app)


class TestUserInterventionAPI:
    """ユーザー直接介入APIのテスト"""

    def test_create_intervention(self, client: TestClient):
        """介入を作成できる

        Arrange: 有効なリクエスト
        Act: POST /interventions/user
        Assert: 201と介入情報
        """
        # Arrange
        data = {
            "colony_id": "col-001",
            "instruction": "このアプローチで進めて",
            "reason": "Beekeeperの指示が不明確",
        }

        # Act
        response = client.post("/interventions/user", json=data)

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "event_id" in result
        assert result["type"] == "user_intervention"
        assert result["colony_id"] == "col-001"

    def test_list_interventions(self, client: TestClient):
        """介入一覧を取得できる

        Arrange: 介入を作成
        Act: GET /interventions/interventions
        Assert: 一覧が返る
        """
        # Arrange
        client.post(
            "/interventions/user",
            json={"colony_id": "col-list", "instruction": "テスト"},
        )

        # Act
        response = client.get("/interventions/interventions")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "interventions" in result
        assert "count" in result

    def test_list_interventions_by_colony(self, client: TestClient):
        """Colony IDでフィルタできる

        Arrange: 異なるColonyの介入
        Act: GET /interventions/interventions?colony_id=...
        Assert: 指定Colonyのみ
        """
        # Arrange
        client.post(
            "/interventions/user",
            json={"colony_id": "col-filter-1", "instruction": "A"},
        )
        client.post(
            "/interventions/user",
            json={"colony_id": "col-filter-2", "instruction": "B"},
        )

        # Act
        response = client.get("/interventions/interventions?colony_id=col-filter-1")

        # Assert
        assert response.status_code == 200
        result = response.json()
        interventions = [i for i in result["interventions"] if i["colony_id"] == "col-filter-1"]
        assert len(interventions) >= 1


class TestQueenEscalationAPI:
    """Queen直訴APIのテスト"""

    def test_create_escalation(self, client: TestClient):
        """エスカレーションを作成できる

        Arrange: 有効なリクエスト
        Act: POST /interventions/escalation
        Assert: 200とエスカレーション情報
        """
        # Arrange
        data = {
            "colony_id": "col-esc-001",
            "escalation_type": "beekeeper_conflict",
            "summary": "設計方針の見解相違",
            "details": "詳細な説明",
            "suggested_actions": ["案A", "案B"],
        }

        # Act
        response = client.post("/interventions/escalation", json=data)

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "event_id" in result
        assert result["type"] == "queen_escalation"
        assert result["colony_id"] == "col-esc-001"

    def test_invalid_escalation_type(self, client: TestClient):
        """無効なエスカレーションタイプはエラー

        Arrange: 無効なタイプ
        Act: POST /interventions/escalation
        Assert: 400エラー
        """
        # Arrange
        data = {
            "colony_id": "col-001",
            "escalation_type": "invalid_type",
            "summary": "テスト",
        }

        # Act
        response = client.post("/interventions/escalation", json=data)

        # Assert
        assert response.status_code == 400

    def test_list_escalations(self, client: TestClient):
        """エスカレーション一覧を取得できる

        Arrange: エスカレーションを作成
        Act: GET /interventions/escalations
        Assert: 一覧が返る
        """
        # Arrange
        client.post(
            "/interventions/escalation",
            json={
                "colony_id": "col-list-esc",
                "escalation_type": "technical_blocker",
                "summary": "テスト問題",
            },
        )

        # Act
        response = client.get("/interventions/escalations")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "escalations" in result
        assert "count" in result

    def test_get_escalation(self, client: TestClient):
        """エスカレーション詳細を取得できる

        Arrange: エスカレーションを作成
        Act: GET /interventions/escalations/{id}
        Assert: 詳細が返る
        """
        # Arrange
        create_response = client.post(
            "/interventions/escalation",
            json={
                "colony_id": "col-get-esc",
                "escalation_type": "resource_shortage",
                "summary": "リソース不足",
            },
        )
        event_id = create_response.json()["event_id"]

        # Act
        response = client.get(f"/interventions/escalations/{event_id}")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["event_id"] == event_id

    def test_get_escalation_not_found(self, client: TestClient):
        """存在しないエスカレーションは404

        Arrange: 存在しないID
        Act: GET /interventions/escalations/{id}
        Assert: 404エラー
        """
        # Act
        response = client.get("/interventions/escalations/nonexistent")

        # Assert
        assert response.status_code == 404


class TestBeekeeperFeedbackAPI:
    """BeekeeperフィードバックAPIのテスト"""

    def test_create_feedback(self, client: TestClient):
        """フィードバックを作成できる

        Arrange: エスカレーションを作成後
        Act: POST /interventions/feedback
        Assert: 200とフィードバック情報
        """
        # Arrange
        esc_response = client.post(
            "/interventions/escalation",
            json={
                "colony_id": "col-fb-001",
                "escalation_type": "beekeeper_conflict",
                "summary": "テスト問題",
            },
        )
        escalation_id = esc_response.json()["event_id"]

        # Act
        response = client.post(
            "/interventions/feedback",
            json={
                "escalation_id": escalation_id,
                "resolution": "案Aで解決",
                "beekeeper_adjustment": {"priority": "high"},
                "lesson_learned": "早期確認が重要",
            },
        )

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert "event_id" in result
        assert result["type"] == "beekeeper_feedback"

    def test_feedback_not_found_escalation(self, client: TestClient):
        """存在しないエスカレーションへのフィードバックは404

        Arrange: 存在しないID
        Act: POST /interventions/feedback
        Assert: 404エラー
        """
        # Act
        response = client.post(
            "/interventions/feedback",
            json={
                "escalation_id": "nonexistent",
                "resolution": "テスト",
            },
        )

        # Assert
        assert response.status_code == 404

    def test_feedback_resolves_escalation(self, client: TestClient):
        """フィードバックでエスカレーションが解決済みになる

        Arrange: エスカレーション作成
        Act: フィードバック作成後にエスカレーション取得
        Assert: statusがresolved
        """
        # Arrange
        esc_response = client.post(
            "/interventions/escalation",
            json={
                "colony_id": "col-resolve",
                "escalation_type": "scope_clarification",
                "summary": "スコープ確認",
            },
        )
        escalation_id = esc_response.json()["event_id"]

        # Act
        client.post(
            "/interventions/feedback",
            json={
                "escalation_id": escalation_id,
                "resolution": "スコープ確定",
            },
        )
        get_response = client.get(f"/interventions/escalations/{escalation_id}")

        # Assert
        assert get_response.json()["status"] == "resolved"
