"""プロンプト設定のテスト

YAML形式のプロンプト設定ファイルの読み込みと検証をテスト。
AAAパターン（Arrange-Act-Assert）を使用。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from colonyforge.llm.prompt_config import (
    BeekeeperConfig,
    LLMConfig,
    PromptLoader,
    PromptTemplate,
    QueenBeeConfig,
    WorkerBeeConfig,
)
from colonyforge.llm.prompts import (
    BEEKEEPER_SYSTEM,
    QUEEN_BEE_SYSTEM,
    WORKER_BEE_SYSTEM,
    get_beekeeper_config,
    get_prompt_from_config,
    get_queen_bee_config,
    get_system_prompt,
    get_worker_bee_config,
)

# =============================================================================
# スキーマ検証テスト
# =============================================================================


class TestPromptTemplate:
    """PromptTemplateスキーマのテスト"""

    def test_system_prompt_required(self):
        """systemプロンプトは必須フィールド

        systemフィールドがない場合はValidationErrorが発生する。
        """
        # Arrange: systemフィールドなし
        # Act & Assert
        with pytest.raises(Exception):  # ValidationError
            PromptTemplate()  # type: ignore

    def test_minimal_prompt_template(self):
        """最小限のプロンプトテンプレートを作成できる

        systemのみ指定すれば他はオプション。
        """
        # Arrange
        system = "あなたはテスト用エージェントです。"

        # Act
        template = PromptTemplate(system=system)

        # Assert
        assert template.system == system
        assert template.task_prefix is None
        assert template.task_suffix is None

    def test_full_prompt_template(self):
        """全フィールドを指定したプロンプトテンプレート"""
        # Arrange
        system = "あなたはテスト用エージェントです。"
        prefix = "## タスク\n"
        suffix = "\n以上を実行してください。"

        # Act
        template = PromptTemplate(
            system=system,
            task_prefix=prefix,
            task_suffix=suffix,
        )

        # Assert
        assert template.system == system
        assert template.task_prefix == prefix
        assert template.task_suffix == suffix


class TestLLMConfig:
    """LLMConfigスキーマのテスト"""

    def test_empty_llm_config(self):
        """空のLLM設定を作成できる

        全フィールドがオプションなので空でも有効。
        """
        # Arrange & Act
        config = LLMConfig()

        # Assert
        assert config.provider is None
        assert config.model is None
        assert config.temperature is None
        assert config.max_tokens is None

    def test_full_llm_config(self):
        """全フィールドを指定したLLM設定"""
        # Arrange & Act
        config = LLMConfig(
            provider="openai",
            model="gpt-4o",
            temperature=0.5,
            max_tokens=2048,
        )

        # Assert
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.5
        assert config.max_tokens == 2048

    def test_temperature_range_validation(self):
        """温度は0.0-2.0の範囲内でなければならない"""
        # Arrange & Act & Assert
        with pytest.raises(Exception):  # ValidationError
            LLMConfig(temperature=3.0)

        with pytest.raises(Exception):
            LLMConfig(temperature=-0.1)


class TestQueenBeeConfig:
    """QueenBeeConfigスキーマのテスト"""

    def test_minimal_queen_bee_config(self):
        """最小限のQueen Bee設定"""
        # Arrange
        prompt = PromptTemplate(system="テスト")

        # Act
        config = QueenBeeConfig(prompt=prompt)

        # Assert
        assert config.name == "default"
        assert config.prompt.system == "テスト"
        assert config.max_workers == 5
        assert config.task_assignment_strategy == "round_robin"

    def test_full_queen_bee_config(self):
        """全フィールドを指定したQueen Bee設定"""
        # Arrange
        prompt = PromptTemplate(system="カスタムQueen Bee")
        llm = LLMConfig(model="gpt-4o")

        # Act
        config = QueenBeeConfig(
            name="custom-queen",
            description="カスタムQueen Bee",
            prompt=prompt,
            llm=llm,
            max_workers=10,
            task_assignment_strategy="load_balanced",
        )

        # Assert
        assert config.name == "custom-queen"
        assert config.description == "カスタムQueen Bee"
        assert config.llm.model == "gpt-4o"
        assert config.max_workers == 10
        assert config.task_assignment_strategy == "load_balanced"


class TestWorkerBeeConfig:
    """WorkerBeeConfigスキーマのテスト"""

    def test_minimal_worker_bee_config(self):
        """最小限のWorker Bee設定

        nameとpromptは必須。
        """
        # Arrange
        prompt = PromptTemplate(system="テスト")

        # Act
        config = WorkerBeeConfig(name="test-worker", prompt=prompt)

        # Assert
        assert config.name == "test-worker"
        assert config.prompt.system == "テスト"
        assert config.trust_level == "standard"
        assert config.tools is None

    def test_worker_with_tools(self):
        """ツール制限付きWorker Bee設定"""
        # Arrange
        prompt = PromptTemplate(system="テスト")
        allowed_tools = ["list_directory", "read_file"]

        # Act
        config = WorkerBeeConfig(
            name="reader",
            prompt=prompt,
            tools=allowed_tools,
            trust_level="limited",
        )

        # Assert
        assert config.tools == allowed_tools
        assert config.trust_level == "limited"


class TestBeekeeperConfig:
    """BeekeeperConfigスキーマのテスト"""

    def test_minimal_beekeeper_config(self):
        """最小限のBeekeeper設定"""
        # Arrange
        prompt = PromptTemplate(system="テスト")

        # Act
        config = BeekeeperConfig(prompt=prompt)

        # Assert
        assert config.name == "default"
        assert config.prompt.system == "テスト"


# =============================================================================
# PromptLoaderテスト
# =============================================================================


class TestPromptLoader:
    """PromptLoaderのテスト"""

    @pytest.fixture
    def temp_vault(self, tmp_path: Path) -> Path:
        """テスト用の一時Vaultディレクトリ"""
        vault = tmp_path / "Vault"
        vault.mkdir()
        return vault

    def test_no_config_file_returns_none(self, tmp_path: Path):
        """Vaultにもパッケージにも設定ファイルがない場合はNoneを返す

        存在しないファイル名を指定してテスト。
        """
        # Arrange
        vault = tmp_path / "Vault"
        vault.mkdir()
        loader = PromptLoader(vault)

        # Act: 存在しないWorker名を指定
        config = loader.load_worker_bee_config(name="nonexistent")

        # Assert
        assert config is None

    def test_fallback_to_package_defaults(self, temp_vault: Path):
        """Vaultに設定がない場合はパッケージ内のデフォルトを使う"""
        # Arrange
        loader = PromptLoader(temp_vault)

        # Act: Vaultには何もないがパッケージ内にデフォルトがある
        config = loader.load_queen_bee_config()

        # Assert: パッケージ内のデフォルトが読み込まれる
        assert config is not None
        assert config.name == "default"
        assert "Queen Bee" in config.prompt.system

    def test_load_queen_bee_config_from_colony(self, temp_vault: Path):
        """Colony固有のQueen Bee設定を読み込める"""
        # Arrange
        loader = PromptLoader(temp_vault)
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)

        config_content = """
name: custom-queen
prompt:
  system: カスタムQueen Beeです
max_workers: 8
task_assignment_strategy: priority
"""
        (colony_dir / "queen_bee.yml").write_text(config_content, encoding="utf-8")

        # Act
        config = loader.load_queen_bee_config(hive_id="0", colony_id="0")

        # Assert
        assert config is not None
        assert config.name == "custom-queen"
        assert config.prompt.system == "カスタムQueen Beeです"
        assert config.max_workers == 8
        assert config.task_assignment_strategy == "priority"

    def test_load_worker_bee_config(self, temp_vault: Path):
        """Worker Bee設定を読み込める"""
        # Arrange
        loader = PromptLoader(temp_vault)
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)

        config_content = """
name: coder
description: コーディング専門のWorker
prompt:
  system: あなたはコーディング専門のWorker Beeです。
tools:
  - read_file
  - write_file
  - run_command
trust_level: elevated
"""
        (colony_dir / "coder_worker_bee.yml").write_text(config_content, encoding="utf-8")

        # Act
        config = loader.load_worker_bee_config(name="coder", hive_id="0", colony_id="0")

        # Assert
        assert config is not None
        assert config.name == "coder"
        assert config.description == "コーディング専門のWorker"
        assert config.tools == ["read_file", "write_file", "run_command"]
        assert config.trust_level == "elevated"

    def test_load_beekeeper_config(self, temp_vault: Path):
        """Beekeeper設定を読み込める"""
        # Arrange
        loader = PromptLoader(temp_vault)
        hive_dir = temp_vault / "hives" / "0"
        hive_dir.mkdir(parents=True)

        config_content = """
name: main-beekeeper
description: メインのBeekeeper
prompt:
  system: あなたはカスタムBeekeeperです。
"""
        (hive_dir / "beekeeper.yml").write_text(config_content, encoding="utf-8")

        # Act
        config = loader.load_beekeeper_config(hive_id="0")

        # Assert
        assert config is not None
        assert config.name == "main-beekeeper"
        assert config.prompt.system == "あなたはカスタムBeekeeperです。"

    def test_config_priority_colony_over_hive(self, temp_vault: Path):
        """Colony固有の設定がHive全体の設定より優先される

        同じファイルがColonyとHiveに存在する場合、Colonyのものを使用。
        """
        # Arrange
        loader = PromptLoader(temp_vault)

        # Hive全体の設定
        hive_dir = temp_vault / "hives" / "0"
        hive_dir.mkdir(parents=True)
        (hive_dir / "queen_bee.yml").write_text(
            """
name: hive-queen
prompt:
  system: Hive全体のQueen Bee
""",
            encoding="utf-8",
        )

        # Colony固有の設定
        colony_dir = hive_dir / "colonies" / "0"
        colony_dir.mkdir(parents=True)
        (colony_dir / "queen_bee.yml").write_text(
            """
name: colony-queen
prompt:
  system: Colony固有のQueen Bee
""",
            encoding="utf-8",
        )

        # Act
        config = loader.load_queen_bee_config(hive_id="0", colony_id="0")

        # Assert: Colony固有の設定が使われる
        assert config is not None
        assert config.name == "colony-queen"
        assert config.prompt.system == "Colony固有のQueen Bee"

    def test_fallback_to_hive_config(self, temp_vault: Path):
        """Colony固有の設定がない場合はHive全体の設定を使う"""
        # Arrange
        loader = PromptLoader(temp_vault)

        # Hive全体の設定のみ
        hive_dir = temp_vault / "hives" / "0"
        hive_dir.mkdir(parents=True)
        (hive_dir / "queen_bee.yml").write_text(
            """
name: hive-queen
prompt:
  system: Hive全体のQueen Bee
""",
            encoding="utf-8",
        )

        # Act
        config = loader.load_queen_bee_config(hive_id="0", colony_id="0")

        # Assert: Hive全体の設定が使われる
        assert config is not None
        assert config.name == "hive-queen"

    def test_ensure_default_prompts(self, temp_vault: Path):
        """デフォルトプロンプトファイルを自動生成できる"""
        # Arrange
        loader = PromptLoader(temp_vault)

        # Act
        loader.ensure_default_prompts(hive_id="0", colony_id="0")

        # Assert: ファイルが生成されている
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        hive_dir = temp_vault / "hives" / "0"

        assert (colony_dir / "queen_bee.yml").exists()
        assert (colony_dir / "default_worker_bee.yml").exists()
        assert (hive_dir / "beekeeper.yml").exists()


# =============================================================================
# prompts.py関数テスト
# =============================================================================


class TestGetSystemPrompt:
    """get_system_prompt関数のテスト"""

    def test_worker_bee_prompt(self):
        """worker_beeのプロンプトを取得"""
        # Act
        prompt = get_system_prompt("worker_bee")

        # Assert
        assert prompt == WORKER_BEE_SYSTEM

    def test_queen_bee_prompt(self):
        """queen_beeのプロンプトを取得"""
        # Act
        prompt = get_system_prompt("queen_bee")

        # Assert
        assert prompt == QUEEN_BEE_SYSTEM

    def test_beekeeper_prompt(self):
        """beekeeperのプロンプトを取得"""
        # Act
        prompt = get_system_prompt("beekeeper")

        # Assert
        assert prompt == BEEKEEPER_SYSTEM

    def test_unknown_agent_type_defaults_to_worker(self):
        """不明なエージェントタイプはworker_beeにフォールバック"""
        # Act
        prompt = get_system_prompt("unknown")

        # Assert
        assert prompt == WORKER_BEE_SYSTEM


class TestGetPromptFromConfig:
    """get_prompt_from_config関数のテスト"""

    @pytest.fixture
    def temp_vault(self, tmp_path: Path) -> Path:
        """テスト用の一時Vaultディレクトリ"""
        vault = tmp_path / "Vault"
        vault.mkdir()
        return vault

    def test_returns_default_when_no_config(self, temp_vault: Path):
        """設定ファイルがない場合はデフォルトプロンプトを返す"""
        # Act
        prompt = get_prompt_from_config("worker_bee", vault_path=temp_vault)

        # Assert
        assert prompt == WORKER_BEE_SYSTEM

    def test_returns_custom_prompt_from_config(self, temp_vault: Path):
        """設定ファイルがある場合はカスタムプロンプトを返す"""
        # Arrange
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)

        custom_prompt = "あなたはカスタムWorker Beeです。"
        (colony_dir / "default_worker_bee.yml").write_text(
            f"""
name: default
prompt:
  system: {custom_prompt}
""",
            encoding="utf-8",
        )

        # Act
        prompt = get_prompt_from_config(
            "worker_bee", vault_path=temp_vault, hive_id="0", colony_id="0"
        )

        # Assert
        assert prompt == custom_prompt

    def test_load_named_worker_config(self, temp_vault: Path):
        """名前付きWorker Bee設定を読み込める"""
        # Arrange
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)

        custom_prompt = "あなたはレビュー専門のWorker Beeです。"
        (colony_dir / "reviewer_worker_bee.yml").write_text(
            f"""
name: reviewer
prompt:
  system: {custom_prompt}
""",
            encoding="utf-8",
        )

        # Act
        prompt = get_prompt_from_config(
            "worker_bee",
            vault_path=temp_vault,
            hive_id="0",
            colony_id="0",
            worker_name="reviewer",
        )

        # Assert
        assert prompt == custom_prompt


class TestConfigHelpers:
    """設定取得ヘルパー関数のテスト"""

    @pytest.fixture
    def temp_vault(self, tmp_path: Path) -> Path:
        """テスト用の一時Vaultディレクトリ"""
        vault = tmp_path / "Vault"
        vault.mkdir()
        return vault

    def test_get_queen_bee_config(self, temp_vault: Path):
        """get_queen_bee_config関数でQueen Bee設定を取得"""
        # Arrange
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)
        (colony_dir / "queen_bee.yml").write_text(
            """
name: test-queen
prompt:
  system: テスト
max_workers: 3
""",
            encoding="utf-8",
        )

        # Act
        config = get_queen_bee_config(vault_path=temp_vault)

        # Assert
        assert config is not None
        assert config.name == "test-queen"
        assert config.max_workers == 3

    def test_get_worker_bee_config(self, temp_vault: Path):
        """get_worker_bee_config関数でWorker Bee設定を取得"""
        # Arrange
        colony_dir = temp_vault / "hives" / "0" / "colonies" / "0"
        colony_dir.mkdir(parents=True)
        (colony_dir / "default_worker_bee.yml").write_text(
            """
name: default
prompt:
  system: テスト
trust_level: limited
""",
            encoding="utf-8",
        )

        # Act
        config = get_worker_bee_config(vault_path=temp_vault)

        # Assert
        assert config is not None
        assert config.trust_level == "limited"

    def test_get_beekeeper_config(self, temp_vault: Path):
        """get_beekeeper_config関数でBeekeeper設定を取得"""
        # Arrange
        hive_dir = temp_vault / "hives" / "0"
        hive_dir.mkdir(parents=True)
        (hive_dir / "beekeeper.yml").write_text(
            """
name: main
prompt:
  system: テスト
""",
            encoding="utf-8",
        )

        # Act
        config = get_beekeeper_config(vault_path=temp_vault)

        # Assert
        assert config is not None
        assert config.name == "main"
