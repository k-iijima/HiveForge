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
    heartbeat_interval_seconds: int = Field(
        default=30, ge=5, le=120, description="ハートビート間隔秒"
    )
    approval_timeout_hours: int = Field(default=24, ge=1, description="承認タイムアウト時間")
    archive_after_days: int = Field(default=7, ge=1, description="アーカイブまでの日数")


class RateLimitConfig(BaseModel):
    """レートリミット設定"""

    requests_per_minute: int = Field(default=60, ge=1, description="1分あたりの最大リクエスト数")
    requests_per_day: int = Field(
        default=0, ge=0, description="1日あたりの最大リクエスト数（0=無制限）"
    )
    tokens_per_minute: int = Field(
        default=90000, ge=1000, description="1分あたりの最大LLMトークン数"
    )
    max_concurrent: int = Field(default=10, ge=1, le=100, description="最大同時リクエスト数")
    burst_limit: int = Field(default=10, ge=1, le=100, description="バースト許容数")
    retry_after_429: int = Field(default=60, ge=1, description="429エラー時の待機秒数")


class LLMConfig(BaseModel):
    """LLM設定"""

    provider: Literal["openai", "azure", "anthropic"] = Field(default="openai")
    model: str = Field(default="gpt-4o")
    api_key_env: str = Field(default="OPENAI_API_KEY", description="APIキーの環境変数名")
    max_tokens: int = Field(default=4096, ge=100)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)


class AgentLLMConfig(BaseModel):
    """エージェント別LLM設定（オプション）

    各エージェントは個別のLLM設定を持てる。
    未設定の場合はグローバルのllm設定を使用する。
    """

    provider: Literal["openai", "azure", "anthropic"] | None = Field(
        default=None, description="LLMプロバイダー（未設定時はグローバル設定を使用）"
    )
    model: str | None = Field(
        default=None, description="モデル名（未設定時はグローバル設定を使用）"
    )
    api_key_env: str | None = Field(
        default=None, description="APIキー環境変数名（未設定時はグローバル設定を使用）"
    )
    max_tokens: int | None = Field(
        default=None, ge=100, description="最大トークン数（未設定時はグローバル設定を使用）"
    )
    temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="生成温度（未設定時はグローバル設定を使用）"
    )
    rate_limit: RateLimitConfig | None = Field(
        default=None, description="レートリミット設定（未設定時はグローバル設定を使用）"
    )

    def merge_with_global(self, global_llm: LLMConfig) -> LLMConfig:
        """グローバル設定とマージして完全なLLMConfigを生成

        Args:
            global_llm: グローバルLLM設定

        Returns:
            マージされたLLMConfig
        """
        return LLMConfig(
            provider=self.provider if self.provider is not None else global_llm.provider,
            model=self.model if self.model is not None else global_llm.model,
            api_key_env=self.api_key_env
            if self.api_key_env is not None
            else global_llm.api_key_env,
            max_tokens=self.max_tokens if self.max_tokens is not None else global_llm.max_tokens,
            temperature=self.temperature
            if self.temperature is not None
            else global_llm.temperature,
            rate_limit=self.rate_limit if self.rate_limit is not None else global_llm.rate_limit,
        )


class AuthConfig(BaseModel):
    """認証設定"""

    enabled: bool = Field(default=False)
    api_key_env: str = Field(default="HIVEFORGE_API_KEY")


class CORSConfig(BaseModel):
    """CORS設定"""

    enabled: bool = Field(default=True, description="CORSを有効にするか")
    allow_origins: list[str] = Field(
        default=["*"],
        description="許可するオリジン（本番では具体的なオリジンを指定）",
    )
    allow_credentials: bool = Field(default=True)
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])


class ServerConfig(BaseModel):
    """サーバー設定"""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    cors: CORSConfig = Field(default_factory=CORSConfig)


class LoggingConfig(BaseModel):
    """ロギング設定"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    events_max_file_size_mb: int = Field(default=100, ge=1)


class HiveConfig(BaseModel):
    """Hive基本設定"""

    name: str = Field(default="default-hive")
    vault_path: str = Field(default="./Vault")


class BeekeeperConfig(BaseModel):
    """Beekeeper設定"""

    enabled: bool = Field(default=True)
    max_colonies: int = Field(default=10, ge=1, le=100)
    session_timeout_minutes: int = Field(default=60, ge=5)
    llm: AgentLLMConfig | None = Field(
        default=None, description="Beekeeper専用LLM設定（未設定時はグローバル設定を使用）"
    )


class QueenBeeConfig(BaseModel):
    """Queen Bee設定"""

    enabled: bool = Field(default=True)
    max_workers_per_colony: int = Field(default=5, ge=1, le=20)
    task_assignment_strategy: Literal["round_robin", "priority", "load_balanced"] = Field(
        default="round_robin"
    )
    llm: AgentLLMConfig | None = Field(
        default=None, description="Queen Bee専用LLM設定（未設定時はグローバル設定を使用）"
    )


class WorkerBeeConfig(BaseModel):
    """Worker Bee設定"""

    enabled: bool = Field(default=True)
    tool_timeout_seconds: int = Field(default=60, ge=10)
    max_retries: int = Field(default=3, ge=0, le=10)
    trust_level_default: Literal["untrusted", "limited", "standard", "elevated", "full"] = Field(
        default="standard"
    )
    llm: AgentLLMConfig | None = Field(
        default=None, description="Worker Bee専用LLM設定（未設定時はグローバル設定を使用）"
    )


class AgentsConfig(BaseModel):
    """エージェント設定"""

    beekeeper: BeekeeperConfig = Field(default_factory=BeekeeperConfig)
    queen_bee: QueenBeeConfig = Field(default_factory=QueenBeeConfig)
    worker_bee: WorkerBeeConfig = Field(default_factory=WorkerBeeConfig)


class ConflictConfig(BaseModel):
    """衝突検出・解決設定"""

    detection_enabled: bool = Field(default=True)
    auto_resolve_low_severity: bool = Field(default=True)
    escalation_timeout_minutes: int = Field(default=30, ge=5)


class ConferenceConfig(BaseModel):
    """Conference設定"""

    enabled: bool = Field(default=True)
    max_participants: int = Field(default=10, ge=2, le=50)
    voting_timeout_minutes: int = Field(default=15, ge=1)
    quorum_percentage: int = Field(default=50, ge=1, le=100)


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
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    conflict: ConflictConfig = Field(default_factory=ConflictConfig)
    conference: ConferenceConfig = Field(default_factory=ConferenceConfig)

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
