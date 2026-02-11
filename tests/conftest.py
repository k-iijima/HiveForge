"""ColonyForge テスト設定"""

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
    from colonyforge.core.config import HiveConfig, ColonyForgeSettings

    settings = ColonyForgeSettings(hive=HiveConfig(name="test-hive", vault_path=str(temp_vault)))

    def mock_get_settings():
        return settings

    monkeypatch.setattr("colonyforge.core.config.get_settings", mock_get_settings)
    return settings


@pytest.fixture
def client(tmp_path):
    """テスト用FastAPIクライアント"""
    from fastapi.testclient import TestClient

    from colonyforge.api.dependencies import AppState
    from colonyforge.api.helpers import clear_active_runs, set_ar, set_hive_store
    from colonyforge.api.server import app
    from colonyforge.core.ar.hive_storage import HiveStore

    # グローバル状態をリセット
    AppState.reset()
    set_ar(None)
    clear_active_runs()

    # テスト用HiveStoreを設定（tmp_pathを使用）
    test_hive_store = HiveStore(tmp_path / "Vault")
    set_hive_store(test_hive_store)

    # server.py と helpers.py の両方で使用される get_settings をモック
    mock_s = MagicMock()
    mock_s.get_vault_path.return_value = tmp_path / "Vault"
    mock_s.server.cors.enabled = False

    with (
        patch("colonyforge.api.server.get_settings", return_value=mock_s),
        patch("colonyforge.api.helpers.get_settings", return_value=mock_s),
        TestClient(app) as client,
    ):
        yield client

    # クリーンアップ
    AppState.reset()
