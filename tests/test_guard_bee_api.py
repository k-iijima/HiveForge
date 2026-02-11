"""Guard Bee APIエンドポイントのテスト

Guard Beeによる品質検証API:
- POST /guard-bee/verify: 検証実行
- GET /guard-bee/reports/{run_id}: Run配下の検証レポート一覧
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from colonyforge.api.helpers import clear_active_runs, set_ar
from colonyforge.api.server import app


@pytest.fixture
def client(tmp_path):
    """テスト用クライアント"""
    set_ar(None)
    clear_active_runs()

    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("colonyforge.api.server.get_settings", return_value=mock_s),
        patch("colonyforge.api.helpers.get_settings", return_value=mock_s),
        TestClient(app) as client,
    ):
        yield client

    set_ar(None)
    clear_active_runs()


class TestGuardBeeVerifyEndpoint:
    """POST /guard-bee/verify のテスト"""

    def test_verify_with_all_passing_evidence(self, client):
        """全証拠が合格する場合にPASSが返る

        差分あり + テスト全合格 + カバレッジ十分 + Lintクリーンの場合、
        verdict=pass を含むレポートが返される。
        """
        # Arrange: Runを開始
        run_resp = client.post("/runs", json={"goal": "Guard Bee テスト"})
        run_id = run_resp.json()["run_id"]

        # Act: 検証リクエスト送信
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-001",
                "task_id": "task-001",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "diff",
                        "source": "src/main.py",
                        "content": {"files_changed": 2, "added": 10, "removed": 2},
                    },
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 50, "passed": 50, "failed": 0, "errors": 0},
                    },
                    {
                        "evidence_type": "test_coverage",
                        "source": "coverage",
                        "content": {"coverage_percent": 95.0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "pass"
        assert data["colony_id"] == "colony-001"
        assert data["task_id"] == "task-001"
        assert data["run_id"] == run_id
        assert data["l1_passed"] is True
        assert data["evidence_count"] == 4

    def test_verify_with_failing_tests(self, client):
        """テスト失敗がある場合にFAILが返る

        テスト結果にfailed > 0がある場合、L1検証で失敗してFAILが返される。
        """
        # Arrange
        run_resp = client.post("/runs", json={"goal": "テスト失敗ケース"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-002",
                "task_id": "task-002",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "diff",
                        "source": "src/main.py",
                        "content": {"files_changed": 1, "added": 5, "removed": 1},
                    },
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 43, "passed": 40, "failed": 3, "errors": 0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "fail"
        assert data["l1_passed"] is False
        assert data["remand_reason"] is not None

    def test_verify_with_low_coverage(self, client):
        """カバレッジ不足の場合にFAILが返る

        カバレッジがデフォルト閾値(80%)未満の場合、L1検証で失敗する。
        """
        # Arrange
        run_resp = client.post("/runs", json={"goal": "カバレッジ不足ケース"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-003",
                "task_id": "task-003",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "diff",
                        "source": "src/main.py",
                        "content": {"files_changed": 1, "added": 10, "removed": 0},
                    },
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 20, "passed": 20, "failed": 0, "errors": 0},
                    },
                    {
                        "evidence_type": "test_coverage",
                        "source": "coverage",
                        "content": {"coverage_percent": 50.0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "fail"
        assert data["l1_passed"] is False

    def test_verify_with_no_diff(self, client):
        """差分がない場合にFAILが返る

        DiffExistsRuleにより差分なし = 成果物なしと判定される。
        """
        # Arrange
        run_resp = client.post("/runs", json={"goal": "差分なしケース"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-004",
                "task_id": "task-004",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 10, "passed": 10, "failed": 0, "errors": 0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "fail"

    def test_verify_with_empty_evidence(self, client):
        """証拠なしの場合にFAILが返る"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "証拠なしケース"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-005",
                "task_id": "task-005",
                "run_id": run_id,
                "evidence": [],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "fail"

    def test_verify_with_invalid_run_id(self, client):
        """存在しないRun IDの場合は404"""
        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-001",
                "task_id": "task-001",
                "run_id": "nonexistent-run",
                "evidence": [],
            },
        )

        # Assert
        assert response.status_code == 404

    def test_verify_request_missing_required_fields(self, client):
        """必須フィールドがない場合は422"""
        # Act
        response = client.post(
            "/guard-bee/verify",
            json={"colony_id": "colony-001"},
        )

        # Assert
        assert response.status_code == 422

    def test_verify_with_context(self, client):
        """追加コンテキスト付きの検証

        contextパラメータが正しくVerifierに渡されることを確認。
        """
        # Arrange
        run_resp = client.post("/runs", json={"goal": "コンテキスト付きテスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-006",
                "task_id": "task-006",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "diff",
                        "source": "src/main.py",
                        "content": {"files_changed": 1, "added": 10, "removed": 0},
                    },
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 30, "passed": 30, "failed": 0, "errors": 0},
                    },
                    {
                        "evidence_type": "test_coverage",
                        "source": "coverage",
                        "content": {"coverage_percent": 90.0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
                "context": {"design_intent": "リファクタリング"},
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data


class TestGuardBeeReportsEndpoint:
    """GET /guard-bee/reports/{run_id} のテスト"""

    def test_get_reports_after_verify(self, client):
        """検証実施後にレポートが取得できる

        検証を実行した後、同じrun_idでレポート一覧が返される。
        """
        # Arrange: 検証を実行
        run_resp = client.post("/runs", json={"goal": "レポート取得テスト"})
        run_id = run_resp.json()["run_id"]

        client.post(
            "/guard-bee/verify",
            json={
                "colony_id": "colony-rpt",
                "task_id": "task-rpt",
                "run_id": run_id,
                "evidence": [
                    {
                        "evidence_type": "diff",
                        "source": "src/main.py",
                        "content": {"files_changed": 1, "added": 5, "removed": 0},
                    },
                    {
                        "evidence_type": "test_result",
                        "source": "pytest",
                        "content": {"total": 20, "passed": 20, "failed": 0, "errors": 0},
                    },
                    {
                        "evidence_type": "test_coverage",
                        "source": "coverage",
                        "content": {"coverage_percent": 90.0},
                    },
                    {
                        "evidence_type": "lint_result",
                        "source": "ruff",
                        "content": {"errors": 0, "warnings": 0},
                    },
                ],
            },
        )

        # Act
        response = client.get(f"/guard-bee/reports/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        report = data[0]
        assert report["colony_id"] == "colony-rpt"
        assert report["verdict"] in ["pass", "conditional_pass", "fail"]

    def test_get_reports_empty(self, client):
        """検証未実施のRunでは空リストが返る"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "空レポートテスト"})
        run_id = run_resp.json()["run_id"]

        # Act
        response = client.get(f"/guard-bee/reports/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_get_reports_nonexistent_run(self, client):
        """存在しないRunのレポート取得は404"""
        # Act
        response = client.get("/guard-bee/reports/nonexistent-run")

        # Assert
        assert response.status_code == 404

    def test_get_reports_multiple_verifications(self, client):
        """複数回検証した場合に全レポートが返る"""
        # Arrange
        run_resp = client.post("/runs", json={"goal": "複数検証テスト"})
        run_id = run_resp.json()["run_id"]

        for i in range(3):
            client.post(
                "/guard-bee/verify",
                json={
                    "colony_id": f"colony-multi-{i}",
                    "task_id": f"task-multi-{i}",
                    "run_id": run_id,
                    "evidence": [
                        {
                            "evidence_type": "diff",
                            "source": f"src/file{i}.py",
                            "content": {"files_changed": 1, "added": 10 + i, "removed": 0},
                        },
                        {
                            "evidence_type": "test_result",
                            "source": "pytest",
                            "content": {"total": 20, "passed": 20, "failed": 0, "errors": 0},
                        },
                        {
                            "evidence_type": "test_coverage",
                            "source": "coverage",
                            "content": {"coverage_percent": 90.0},
                        },
                        {
                            "evidence_type": "lint_result",
                            "source": "ruff",
                            "content": {"errors": 0, "warnings": 0},
                        },
                    ],
                },
            )

        # Act
        response = client.get(f"/guard-bee/reports/{run_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
