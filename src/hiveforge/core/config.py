"""HiveForge 設定管理モジュール

Pydantic Settingsを使用した型安全な設定管理。
hiveforge.config.yaml と環境変数から設定を読み込む。
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GovernanceConfig(BaseModel):
    """ガバナンス設定"""

    max_retries: int = Field(default=3, ge=1, le=10, description="最大リトライ回数")
    max_oscillations: int = Field(default=5, ge=1, le=20, description="振動検知しきい値")
    max_concurrent_tasks: int = Field(default=10, ge=1, le=100, description="最大同時タスク数")
    task_timeout_seconds: int = Field(default=300, ge=30, description="タスクタイムアウト秒")
    heartbeat_interval_seconds: int = Field(default=30, ge=5, le=120, description="ハートビート間隔秒")
    approval_timeout_hours: int = Field(default=24, ge=1, description="承認タイムアウト時間")
    archive_after_days: int = Field(default=7, ge=1, description="アーカイブまでの日数")


class LLMConfig(BaseModel):
    """LLM設定"""

    provider: Literal["openai", "azure", "anthropic"] = Field(default="openai")
    model: str = Field(default="gpt-4o")
    api_key_env: str = Field(default="OPENAI_API_KEY", description="APIキーの環境変数名")
    max_tokens: int = Field(default=4096, ge=100)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class AuthConfig(BaseModel):
    """認証設定"""

    enabled: bool = Field(default=False)
    api_key_env: str = Field(default="HIVEFORGE_API_KEY")


class ServerConfig(BaseModel):
    """サーバー設定"""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    """ロギング設定"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    events_max_file_size_mb: int = Field(default=100, ge=1)


class HiveConfig(BaseModel):
    """Hive基本設定"""

    name: str = Field(default="default-hive")
    vault_path: str = Field(default="./Vault")


class HiveForgeSettings(BaseSettings):
    """HiveForge全体設定

    設定の優先順位:
    1. 環境変数
    2. hiveforge.config.yaml
    3. デフォルト値
    """

    model_config = SettingsConfigDict(
        env_prefix="HIVEFORGE_",
        env_nested_delimiter="__",
    )

    hive: HiveConfig = Field(default_factory=HiveConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, config_path: Path | str | None = None) -> "HiveForgeSettings":
        """YAMLファイルから設定を読み込む

        Args:
            config_path: 設定ファイルパス。Noneの場合はデフォルトパスを探索

        Returns:
            HiveForgeSettings インスタンス
        """
        if config_path is None:
            # デフォルトの設定ファイルパスを探索
            search_paths = [
                Path.cwd() / "hiveforge.config.yaml",
                Path.cwd() / "hiveforge.config.yml",
                Path.home() / ".hiveforge" / "config.yaml",
            ]
            for path in search_paths:
                if path.exists():
                    config_path = path
                    break

        if config_path and Path(config_path).exists():
            with open(config_path, encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f) or {}
            return cls.model_validate(yaml_config)

        return cls()

    def get_vault_path(self) -> Path:
        """Vaultパスを絶対パスで取得"""
        vault = Path(self.hive.vault_path)
        if not vault.is_absolute():
            vault = Path.cwd() / vault
        return vault.resolve()


# グローバル設定インスタンス（遅延初期化）
_settings: HiveForgeSettings | None = None


def get_settings() -> HiveForgeSettings:
    """設定シングルトンを取得"""
    global _settings
    if _settings is None:
        _settings = HiveForgeSettings.from_yaml()
    return _settings


def reload_settings(config_path: Path | str | None = None) -> HiveForgeSettings:
    """設定を再読み込み"""
    global _settings
    _settings = HiveForgeSettings.from_yaml(config_path)
    return _settings
