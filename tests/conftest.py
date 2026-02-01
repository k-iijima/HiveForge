"""HiveForge テスト設定"""

import shutil
import tempfile
from pathlib import Path

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

    settings = HiveForgeSettings(
        hive=HiveConfig(name="test-hive", vault_path=str(temp_vault))
    )

    def mock_get_settings():
        return settings

    monkeypatch.setattr("hiveforge.core.config.get_settings", mock_get_settings)
    return settings
