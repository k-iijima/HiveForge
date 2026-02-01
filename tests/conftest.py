"""HiveForge テスト設定"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_vault():
    """テスト用の一時Vaultディレクトリ"""
    vault_path = Path(tempfile.mkdtemp())
    yield vault_path
    shutil.rmtree(vault_path, ignore_errors=True)


@pytest.fixture
def mock_settings(temp_vault, monkeypatch):
    """テスト用の設定"""
    from hiveforge.core.config import HiveConfig, HiveForgeSettings

    settings = HiveForgeSettings(hive=HiveConfig(name="test-hive", vault_path=str(temp_vault)))

    def mock_get_settings():
        return settings

    monkeypatch.setattr("hiveforge.core.config.get_settings", mock_get_settings)
    return settings


@pytest.fixture
def client(tmp_path):
    """テスト用FastAPIクライアント"""
    from fastapi.testclient import TestClient

    from hiveforge.api.helpers import clear_active_runs, set_ar
    from hiveforge.api.server import app

    # グローバル状態をクリア
    set_ar(None)
    clear_active_runs()

    # server.py と helpers.py の両方で使用される get_settings をモック
    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("hiveforge.api.server.get_settings", return_value=mock_s),
        patch("hiveforge.api.helpers.get_settings", return_value=mock_s),
        TestClient(app) as client,
    ):
        yield client

    # クリーンアップ
    set_ar(None)
    clear_active_runs()
