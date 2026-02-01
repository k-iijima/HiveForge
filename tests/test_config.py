"""設定管理モジュールのテスト"""

from pathlib import Path

from hiveforge.core.config import (
    AgentLLMConfig,
    HiveForgeSettings,
    LLMConfig,
    RateLimitConfig,
    get_settings,
    reload_settings,
)


class TestHiveForgeSettings:
    """HiveForgeSettingsのテスト"""

    def test_default_values(self):
        """デフォルト値が正しく設定される"""
        # Arrange & Act: デフォルト設定を作成
        settings = HiveForgeSettings()

        # Assert: デフォルト値が設定されている
        assert settings.governance.max_retries == 3
        assert settings.governance.max_oscillations == 5
        assert settings.llm.provider == "openai"
        assert settings.server.port == 8000

    def test_from_yaml_with_valid_file(self, tmp_path):
        """有効なYAMLファイルから設定を読み込む"""
        # Arrange: YAMLファイルを作成
        config_file = tmp_path / "hiveforge.config.yaml"
        config_file.write_text("""
hive:
  name: test-hive
  vault_path: /custom/vault
governance:
  max_retries: 5
  max_oscillations: 10
""")

        # Act: YAMLから読み込み
        settings = HiveForgeSettings.from_yaml(config_file)

        # Assert: カスタム値が設定されている
        assert settings.hive.name == "test-hive"
        assert settings.hive.vault_path == "/custom/vault"
        assert settings.governance.max_retries == 5
        assert settings.governance.max_oscillations == 10

    def test_from_yaml_with_nonexistent_file(self):
        """存在しないファイルパスを指定した場合はデフォルト値"""
        # Arrange: 存在しないパス
        nonexistent_path = Path("/nonexistent/config.yaml")

        # Act: 読み込み試行
        settings = HiveForgeSettings.from_yaml(nonexistent_path)

        # Assert: デフォルト値が使用される
        assert settings.governance.max_retries == 3

    def test_from_yaml_with_none_and_no_default_files(self, tmp_path, monkeypatch):
        """config_pathがNoneでデフォルトファイルも存在しない場合"""
        # Arrange: デフォルト探索パスに何もない状態にする
        # ワーキングディレクトリを空の一時ディレクトリに変更
        monkeypatch.chdir(tmp_path)

        # Act: Noneで読み込み
        settings = HiveForgeSettings.from_yaml(None)

        # Assert: デフォルト値が使用される
        assert settings.governance.max_retries == 3

    def test_from_yaml_finds_default_config_file(self, tmp_path, monkeypatch):
        """デフォルトパスの設定ファイルを自動検出する"""
        # Arrange: デフォルトパスに設定ファイルを作成
        config_file = tmp_path / "hiveforge.config.yaml"
        config_file.write_text("""
hive:
  name: auto-detected
""")
        monkeypatch.chdir(tmp_path)

        # Act: config_path=None で読み込み
        settings = HiveForgeSettings.from_yaml(None)

        # Assert: 自動検出された設定が使用される
        assert settings.hive.name == "auto-detected"

    def test_from_yaml_finds_yml_extension(self, tmp_path, monkeypatch):
        """hiveforge.config.yml も自動検出する"""
        # Arrange: .yml 拡張子の設定ファイルを作成
        config_file = tmp_path / "hiveforge.config.yml"
        config_file.write_text("""
hive:
  name: yml-detected
""")
        monkeypatch.chdir(tmp_path)

        # Act: config_path=None で読み込み
        settings = HiveForgeSettings.from_yaml(None)

        # Assert: .yml ファイルが検出される
        assert settings.hive.name == "yml-detected"


class TestGetVaultPath:
    """get_vault_path メソッドのテスト"""

    def test_absolute_path_unchanged(self):
        """絶対パスはそのまま返される"""
        # Arrange: 絶対パスを設定
        settings = HiveForgeSettings.model_validate(
            {"hive": {"vault_path": "/absolute/vault/path"}}
        )

        # Act: パスを取得
        vault_path = settings.get_vault_path()

        # Assert: 絶対パスがそのまま返される
        assert vault_path == Path("/absolute/vault/path")
        assert vault_path.is_absolute()

    def test_relative_path_resolved_to_absolute(self, tmp_path, monkeypatch):
        """相対パスは現在のディレクトリからの絶対パスに解決される"""
        # Arrange: 相対パスを設定
        monkeypatch.chdir(tmp_path)
        settings = HiveForgeSettings.model_validate({"hive": {"vault_path": "./relative/vault"}})

        # Act: パスを取得
        vault_path = settings.get_vault_path()

        # Assert: 絶対パスに解決される
        assert vault_path.is_absolute()
        assert vault_path == (tmp_path / "relative" / "vault").resolve()


class TestSettingsSingleton:
    """設定シングルトンのテスト"""

    def test_get_settings_returns_instance(self, tmp_path, monkeypatch):
        """get_settings はインスタンスを返す"""
        # Arrange: 設定ファイルがない状態にする
        monkeypatch.chdir(tmp_path)
        # シングルトンをリセット
        import hiveforge.core.config as config_module

        config_module._settings = None

        # Act: 設定を取得
        settings = get_settings()

        # Assert: インスタンスが返される
        assert isinstance(settings, HiveForgeSettings)

    def test_reload_settings_updates_singleton(self, tmp_path, monkeypatch):
        """reload_settings はシングルトンを更新する"""
        # Arrange: カスタム設定ファイルを作成
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("""
hive:
  name: reloaded-hive
""")
        monkeypatch.chdir(tmp_path)

        # シングルトンをリセット
        import hiveforge.core.config as config_module

        config_module._settings = None

        # Act: 設定を再読み込み
        settings = reload_settings(config_file)

        # Assert: 新しい設定が反映される
        assert settings.hive.name == "reloaded-hive"

        # 再度 get_settings を呼ぶと同じインスタンスが返される
        same_settings = get_settings()
        assert same_settings.hive.name == "reloaded-hive"


class TestAgentsConfig:
    """エージェント設定のテスト"""

    def test_default_agents_config(self):
        """デフォルトのエージェント設定"""
        settings = HiveForgeSettings()

        assert settings.agents.beekeeper.enabled is True
        assert settings.agents.beekeeper.max_colonies == 10
        assert settings.agents.queen_bee.max_workers_per_colony == 5
        assert settings.agents.worker_bee.trust_level_default == "standard"

    def test_agents_from_yaml(self, tmp_path):
        """YAMLからエージェント設定を読み込む"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
agents:
  beekeeper:
    enabled: true
    max_colonies: 20
  queen_bee:
    max_workers_per_colony: 10
    task_assignment_strategy: priority
  worker_bee:
    trust_level_default: elevated
    tool_timeout_seconds: 120
""")

        settings = HiveForgeSettings.from_yaml(config_file)

        assert settings.agents.beekeeper.max_colonies == 20
        assert settings.agents.queen_bee.max_workers_per_colony == 10
        assert settings.agents.queen_bee.task_assignment_strategy == "priority"
        assert settings.agents.worker_bee.trust_level_default == "elevated"
        assert settings.agents.worker_bee.tool_timeout_seconds == 120


class TestConflictConfig:
    """衝突設定のテスト"""

    def test_default_conflict_config(self):
        """デフォルトの衝突設定"""
        settings = HiveForgeSettings()

        assert settings.conflict.detection_enabled is True
        assert settings.conflict.auto_resolve_low_severity is True
        assert settings.conflict.escalation_timeout_minutes == 30

    def test_conflict_from_yaml(self, tmp_path):
        """YAMLから衝突設定を読み込む"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
conflict:
  detection_enabled: false
  auto_resolve_low_severity: false
  escalation_timeout_minutes: 60
""")

        settings = HiveForgeSettings.from_yaml(config_file)

        assert settings.conflict.detection_enabled is False
        assert settings.conflict.auto_resolve_low_severity is False
        assert settings.conflict.escalation_timeout_minutes == 60


class TestConferenceConfig:
    """Conference設定のテスト"""

    def test_default_conference_config(self):
        """デフォルトのConference設定"""
        settings = HiveForgeSettings()

        assert settings.conference.enabled is True
        assert settings.conference.max_participants == 10
        assert settings.conference.quorum_percentage == 50

    def test_conference_from_yaml(self, tmp_path):
        """YAMLからConference設定を読み込む"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
conference:
  enabled: true
  max_participants: 20
  voting_timeout_minutes: 30
  quorum_percentage: 75
""")

        settings = HiveForgeSettings.from_yaml(config_file)

        assert settings.conference.max_participants == 20
        assert settings.conference.voting_timeout_minutes == 30
        assert settings.conference.quorum_percentage == 75


class TestRateLimitConfig:
    """レートリミット設定のテスト"""

    def test_default_rate_limit_config(self):
        """デフォルトのレートリミット設定"""
        settings = HiveForgeSettings()

        assert settings.llm.rate_limit.requests_per_minute == 60
        assert settings.llm.rate_limit.requests_per_day == 0
        assert settings.llm.rate_limit.tokens_per_minute == 90000
        assert settings.llm.rate_limit.max_concurrent == 10
        assert settings.llm.rate_limit.burst_limit == 10
        assert settings.llm.rate_limit.retry_after_429 == 60

    def test_rate_limit_from_yaml(self, tmp_path):
        """YAMLからレートリミット設定を読み込む"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  provider: openai
  model: gpt-4
  rate_limit:
    requests_per_minute: 100
    requests_per_day: 10000
    tokens_per_minute: 50000
    max_concurrent: 5
    burst_limit: 20
    retry_after_429: 30
""")

        settings = HiveForgeSettings.from_yaml(config_file)

        assert settings.llm.rate_limit.requests_per_minute == 100
        assert settings.llm.rate_limit.requests_per_day == 10000
        assert settings.llm.rate_limit.tokens_per_minute == 50000
        assert settings.llm.rate_limit.max_concurrent == 5
        assert settings.llm.rate_limit.burst_limit == 20
        assert settings.llm.rate_limit.retry_after_429 == 30

    def test_rate_limit_config_standalone(self):
        """RateLimitConfig単体テスト"""
        config = RateLimitConfig(
            requests_per_minute=200,
            max_concurrent=20,
        )

        assert config.requests_per_minute == 200
        assert config.max_concurrent == 20
        # デフォルト値
        assert config.requests_per_day == 0


class TestAgentLLMConfig:
    """エージェント別LLM設定のテスト"""

    def test_default_agent_llm_config_all_none(self):
        """デフォルトでは全てNone（グローバル設定を継承）"""
        # Arrange & Act: デフォルト設定
        agent_llm = AgentLLMConfig()

        # Assert: 全てNone
        assert agent_llm.provider is None
        assert agent_llm.model is None
        assert agent_llm.api_key_env is None
        assert agent_llm.max_tokens is None
        assert agent_llm.temperature is None
        assert agent_llm.rate_limit is None

    def test_merge_with_global_inherits_unset_values(self):
        """未設定の値はグローバル設定から継承される"""
        # Arrange: グローバル設定とエージェント設定
        global_llm = LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
            max_tokens=4096,
            temperature=0.2,
        )
        agent_llm = AgentLLMConfig()  # 全てNone

        # Act: マージ
        merged = agent_llm.merge_with_global(global_llm)

        # Assert: 全てグローバル設定から継承
        assert merged.provider == "openai"
        assert merged.model == "gpt-4o"
        assert merged.api_key_env == "OPENAI_API_KEY"
        assert merged.max_tokens == 4096
        assert merged.temperature == 0.2

    def test_merge_with_global_overrides_set_values(self):
        """設定された値はグローバル設定を上書きする"""
        # Arrange: グローバル設定とエージェント設定（一部上書き）
        global_llm = LLMConfig(
            provider="openai",
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.2,
        )
        agent_llm = AgentLLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet",
            api_key_env="ANTHROPIC_API_KEY",
        )

        # Act: マージ
        merged = agent_llm.merge_with_global(global_llm)

        # Assert: 上書きされた値とグローバルから継承された値
        assert merged.provider == "anthropic"  # 上書き
        assert merged.model == "claude-3-5-sonnet"  # 上書き
        assert merged.api_key_env == "ANTHROPIC_API_KEY"  # 上書き
        assert merged.max_tokens == 4096  # 継承
        assert merged.temperature == 0.2  # 継承

    def test_merge_with_global_partial_override(self):
        """一部の値のみ上書きする場合"""
        # Arrange: グローバル設定とエージェント設定（モデルのみ上書き）
        global_llm = LLMConfig(
            provider="openai",
            model="gpt-4o",
            max_tokens=4096,
        )
        agent_llm = AgentLLMConfig(
            model="gpt-4o-mini",  # 高速モデルに変更
            temperature=0.0,  # より決定的に
        )

        # Act: マージ
        merged = agent_llm.merge_with_global(global_llm)

        # Assert: 部分上書き
        assert merged.provider == "openai"  # 継承
        assert merged.model == "gpt-4o-mini"  # 上書き
        assert merged.temperature == 0.0  # 上書き

    def test_agents_config_with_llm_from_yaml(self, tmp_path):
        """YAMLからエージェント別LLM設定を読み込む"""
        # Arrange: YAMLファイルを作成
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  provider: openai
  model: gpt-4o
  max_tokens: 4096

agents:
  beekeeper:
    llm:
      model: gpt-4o
      temperature: 0.3
  queen_bee:
    llm:
      model: gpt-4o-mini
  worker_bee:
    llm:
      provider: anthropic
      model: claude-3-5-sonnet
      api_key_env: ANTHROPIC_API_KEY
""")

        # Act: 読み込み
        settings = HiveForgeSettings.from_yaml(config_file)

        # Assert: 各エージェントのLLM設定が正しく読み込まれる
        assert settings.agents.beekeeper.llm is not None
        assert settings.agents.beekeeper.llm.model == "gpt-4o"
        assert settings.agents.beekeeper.llm.temperature == 0.3

        assert settings.agents.queen_bee.llm is not None
        assert settings.agents.queen_bee.llm.model == "gpt-4o-mini"
        assert settings.agents.queen_bee.llm.provider is None  # 未設定

        assert settings.agents.worker_bee.llm is not None
        assert settings.agents.worker_bee.llm.provider == "anthropic"
        assert settings.agents.worker_bee.llm.model == "claude-3-5-sonnet"
        assert settings.agents.worker_bee.llm.api_key_env == "ANTHROPIC_API_KEY"

    def test_agents_llm_merge_with_global(self, tmp_path):
        """エージェント別LLM設定をグローバル設定とマージ"""
        # Arrange: YAMLファイルを作成
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
llm:
  provider: openai
  model: gpt-4o
  max_tokens: 4096
  temperature: 0.2

agents:
  worker_bee:
    llm:
      model: gpt-4o-mini
      temperature: 0.0
""")

        settings = HiveForgeSettings.from_yaml(config_file)

        # Act: マージ
        worker_llm = settings.agents.worker_bee.llm.merge_with_global(settings.llm)

        # Assert: 上書きと継承が正しく動作
        assert worker_llm.provider == "openai"  # 継承
        assert worker_llm.model == "gpt-4o-mini"  # 上書き
        assert worker_llm.max_tokens == 4096  # 継承
        assert worker_llm.temperature == 0.0  # 上書き

    def test_agent_without_llm_config(self):
        """LLM設定がないエージェントはNone"""
        # Arrange & Act: デフォルト設定
        settings = HiveForgeSettings()

        # Assert: 全エージェントのllmがNone
        assert settings.agents.beekeeper.llm is None
        assert settings.agents.queen_bee.llm is None
        assert settings.agents.worker_bee.llm is None
