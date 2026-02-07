"""プロンプト設定スキーマと読み込み機能

YAML形式でプロンプトをカスタマイズ可能にする。
ディレクトリ構造: Vault/hives/{hive_id}/colonies/{colony_id}/

- queen_bee.yml: Queen Beeの設定・プロンプト
- {name}_worker_bee.yml: Worker Beeの設定・プロンプト
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# スキーマ定義
# -----------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """LLM設定（オプション）"""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(None, description="LLMプロバイダー (openai, anthropic, azure)")
    model: str | None = Field(None, description="モデル名")
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="生成温度")
    max_tokens: int | None = Field(None, gt=0, description="最大トークン数")


class PromptTemplate(BaseModel):
    """プロンプトテンプレート"""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(..., description="システムプロンプト")
    task_prefix: str | None = Field(None, description="タスク説明の接頭辞（オプション）")
    task_suffix: str | None = Field(None, description="タスク説明の接尾辞（オプション）")


class QueenBeeConfig(BaseModel):
    """Queen Bee設定ファイルのスキーマ"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default", description="Queen Beeの名前")
    description: str | None = Field(None, description="説明")
    prompt: PromptTemplate = Field(..., description="プロンプトテンプレート")
    llm: LLMConfig | None = Field(None, description="専用LLM設定（オプション）")
    max_workers: int = Field(default=5, ge=1, le=100, description="最大Worker数")
    task_assignment_strategy: Literal["round_robin", "priority", "load_balanced"] = Field(
        default="round_robin", description="タスク割り当て戦略"
    )


class WorkerBeeConfig(BaseModel):
    """Worker Bee設定ファイルのスキーマ"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Worker Beeの名前（役割識別用）")
    description: str | None = Field(None, description="説明")
    prompt: PromptTemplate = Field(..., description="プロンプトテンプレート")
    llm: LLMConfig | None = Field(None, description="専用LLM設定（オプション）")
    tools: list[str] | None = Field(None, description="使用可能なツールのリスト（None=全て）")
    trust_level: Literal["untrusted", "limited", "standard", "elevated", "full"] = Field(
        default="standard", description="信頼レベル"
    )


class BeekeeperConfig(BaseModel):
    """Beekeeper設定ファイルのスキーマ"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default", description="Beekeeperの名前")
    description: str | None = Field(None, description="説明")
    prompt: PromptTemplate = Field(..., description="プロンプトテンプレート")
    llm: LLMConfig | None = Field(None, description="専用LLM設定（オプション）")


# -----------------------------------------------------------------------------
# プロンプトローダー
# -----------------------------------------------------------------------------


class PromptLoader:
    """YAML形式のプロンプト設定を読み込む

    読み込み優先順位:
    1. Vault/hives/{hive_id}/colonies/{colony_id}/ のファイル
    2. Vault/hives/{hive_id}/ のファイル（Hive全体のデフォルト）
    3. パッケージ内のデフォルトファイル (src/hiveforge/llm/default_prompts/)
    4. コード内のハードコードされたデフォルト
    """

    def __init__(self, vault_path: str | Path = "./Vault"):
        self.vault_path = Path(vault_path)
        # パッケージ内のデフォルトプロンプトディレクトリ
        self._default_prompts_dir = Path(__file__).parent / "default_prompts"

    def _find_config_file(
        self,
        filename: str,
        hive_id: str = "0",
        colony_id: str | None = None,
    ) -> Path | None:
        """設定ファイルを探す（優先順位順）"""
        candidates = []

        # 1. Colony固有
        if colony_id:
            candidates.append(
                self.vault_path / "hives" / hive_id / "colonies" / colony_id / filename
            )

        # 2. Hive全体のデフォルト
        candidates.append(self.vault_path / "hives" / hive_id / filename)

        # 3. パッケージ内のデフォルト
        candidates.append(self._default_prompts_dir / filename)

        for path in candidates:
            if path.exists():
                return path

        return None

    def load_queen_bee_config(
        self,
        hive_id: str = "0",
        colony_id: str = "0",
    ) -> QueenBeeConfig | None:
        """Queen Bee設定を読み込む"""
        path = self._find_config_file("queen_bee.yml", hive_id, colony_id)
        if path is None:
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return QueenBeeConfig.model_validate(data)

    def load_worker_bee_config(
        self,
        name: str = "default",
        hive_id: str = "0",
        colony_id: str = "0",
    ) -> WorkerBeeConfig | None:
        """Worker Bee設定を読み込む"""
        filename = f"{name}_worker_bee.yml"
        path = self._find_config_file(filename, hive_id, colony_id)
        if path is None:
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return WorkerBeeConfig.model_validate(data)

    def load_beekeeper_config(
        self,
        hive_id: str = "0",
    ) -> BeekeeperConfig | None:
        """Beekeeper設定を読み込む（Beekeeperはhive単位）"""
        path = self._find_config_file("beekeeper.yml", hive_id, None)
        if path is None:
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return BeekeeperConfig.model_validate(data)

    def ensure_default_prompts(self, hive_id: str = "0", colony_id: str = "0") -> None:
        """デフォルトプロンプトファイルを作成（存在しない場合）"""
        from hiveforge.llm.prompts import (
            BEEKEEPER_SYSTEM,
            QUEEN_BEE_SYSTEM,
            WORKER_BEE_SYSTEM,
        )

        # ディレクトリ作成
        colony_dir = self.vault_path / "hives" / hive_id / "colonies" / colony_id
        colony_dir.mkdir(parents=True, exist_ok=True)

        hive_dir = self.vault_path / "hives" / hive_id
        hive_dir.mkdir(parents=True, exist_ok=True)

        # Queen Bee
        queen_path = colony_dir / "queen_bee.yml"
        if not queen_path.exists():
            config = QueenBeeConfig(
                name="default",
                description="デフォルトのQueen Bee",
                prompt=PromptTemplate(system=QUEEN_BEE_SYSTEM),
            )
            self._save_config(queen_path, config)

        # Worker Bee
        worker_path = colony_dir / "default_worker_bee.yml"
        if not worker_path.exists():
            config = WorkerBeeConfig(
                name="default",
                description="デフォルトのWorker Bee",
                prompt=PromptTemplate(system=WORKER_BEE_SYSTEM),
            )
            self._save_config(worker_path, config)

        # Beekeeper
        beekeeper_path = hive_dir / "beekeeper.yml"
        if not beekeeper_path.exists():
            config = BeekeeperConfig(
                name="default",
                description="デフォルトのBeekeeper",
                prompt=PromptTemplate(system=BEEKEEPER_SYSTEM),
            )
            self._save_config(beekeeper_path, config)

    def _save_config(self, path: Path, config: BaseModel) -> None:
        """設定をYAMLファイルに保存"""
        data = config.model_dump(exclude_none=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_prompt_loader(vault_path: str | Path = "./Vault") -> PromptLoader:
    """プロンプトローダーを取得"""
    return PromptLoader(vault_path)
