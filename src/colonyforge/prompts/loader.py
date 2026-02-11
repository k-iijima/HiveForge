"""Prompt configuration schema and YAML loader.

Loads agent-specific prompts and settings from YAML files.
Directory structure: Vault/hives/{hive_id}/colonies/{colony_id}/

- queen_bee.yml: Queen Bee config + prompt
- {name}_worker_bee.yml: Worker Bee config + prompt
- beekeeper.yml: Beekeeper config + prompt (hive level)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------


class LLMConfig(BaseModel):
    """LLM settings (optional per-agent override)."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(None, description="LLM provider (openai, anthropic, azure)")
    model: str | None = Field(None, description="Model name")
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="Generation temperature")
    max_tokens: int | None = Field(None, gt=0, description="Maximum tokens")


class PromptTemplate(BaseModel):
    """Prompt template."""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(..., description="System prompt")
    task_prefix: str | None = Field(None, description="Task description prefix (optional)")
    task_suffix: str | None = Field(None, description="Task description suffix (optional)")


class QueenBeeConfig(BaseModel):
    """Queen Bee YAML configuration schema."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default", description="Queen Bee name")
    description: str | None = Field(None, description="Description")
    prompt: PromptTemplate = Field(..., description="Prompt template")
    llm: LLMConfig | None = Field(None, description="LLM settings override (optional)")
    max_workers: int = Field(default=5, ge=1, le=100, description="Max workers")
    task_assignment_strategy: Literal["round_robin", "priority", "load_balanced"] = Field(
        default="round_robin", description="Task assignment strategy"
    )


class WorkerBeeConfig(BaseModel):
    """Worker Bee YAML configuration schema."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Worker Bee name (role identifier)")
    description: str | None = Field(None, description="Description")
    prompt: PromptTemplate = Field(..., description="Prompt template")
    llm: LLMConfig | None = Field(None, description="LLM settings override (optional)")
    tools: list[str] | None = Field(None, description="Available tools (None = all)")
    trust_level: Literal["untrusted", "limited", "standard", "elevated", "full"] = Field(
        default="standard", description="Trust level"
    )


class BeekeeperConfig(BaseModel):
    """Beekeeper YAML configuration schema."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default", description="Beekeeper name")
    description: str | None = Field(None, description="Description")
    prompt: PromptTemplate = Field(..., description="Prompt template")
    llm: LLMConfig | None = Field(None, description="LLM settings override (optional)")


# ---------------------------------------------------------------------------
# PromptLoader
# ---------------------------------------------------------------------------


class PromptLoader:
    """Load agent prompts and settings from YAML files.

    Resolution priority:
    1. Vault/hives/{hive_id}/colonies/{colony_id}/ (colony-specific)
    2. Vault/hives/{hive_id}/ (hive-level default)
    3. Package defaults (src/colonyforge/prompts/defaults/)
    4. Hardcoded constants in agents.py
    """

    def __init__(self, vault_path: str | Path = "./Vault"):
        self.vault_path = Path(vault_path)
        # Package-bundled default prompt directory
        self._default_prompts_dir = Path(__file__).parent / "defaults"

    def _find_config_file(
        self,
        filename: str,
        hive_id: str = "0",
        colony_id: str | None = None,
    ) -> Path | None:
        """Find a config file by priority order."""
        candidates = []

        # 1. Colony-specific
        if colony_id:
            candidates.append(
                self.vault_path / "hives" / hive_id / "colonies" / colony_id / filename
            )

        # 2. Hive-level default
        candidates.append(self.vault_path / "hives" / hive_id / filename)

        # 3. Package defaults
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
        """Load Queen Bee configuration."""
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
        """Load Worker Bee configuration."""
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
        """Load Beekeeper configuration (hive-level)."""
        path = self._find_config_file("beekeeper.yml", hive_id, None)
        if path is None:
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return BeekeeperConfig.model_validate(data)

    def ensure_default_prompts(self, hive_id: str = "0", colony_id: str = "0") -> None:
        """Create default prompt files if they don't exist."""
        from colonyforge.prompts.agents import (
            BEEKEEPER_SYSTEM,
            QUEEN_BEE_SYSTEM,
            WORKER_BEE_SYSTEM,
        )

        # Create directories
        colony_dir = self.vault_path / "hives" / hive_id / "colonies" / colony_id
        colony_dir.mkdir(parents=True, exist_ok=True)

        hive_dir = self.vault_path / "hives" / hive_id
        hive_dir.mkdir(parents=True, exist_ok=True)

        # Queen Bee
        queen_path = colony_dir / "queen_bee.yml"
        if not queen_path.exists():
            config = QueenBeeConfig(
                name="default",
                description="Default Queen Bee",
                prompt=PromptTemplate(system=QUEEN_BEE_SYSTEM),
            )
            self._save_config(queen_path, config)

        # Worker Bee
        worker_path = colony_dir / "default_worker_bee.yml"
        if not worker_path.exists():
            config = WorkerBeeConfig(
                name="default",
                description="Default Worker Bee",
                prompt=PromptTemplate(system=WORKER_BEE_SYSTEM),
            )
            self._save_config(worker_path, config)

        # Beekeeper
        beekeeper_path = hive_dir / "beekeeper.yml"
        if not beekeeper_path.exists():
            config = BeekeeperConfig(
                name="default",
                description="Default Beekeeper",
                prompt=PromptTemplate(system=BEEKEEPER_SYSTEM),
            )
            self._save_config(beekeeper_path, config)

    def _save_config(self, path: Path, config: BaseModel) -> None:
        """Save configuration to a YAML file."""
        data = config.model_dump(exclude_none=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_prompt_loader(vault_path: str | Path = "./Vault") -> PromptLoader:
    """Get a PromptLoader instance."""
    return PromptLoader(vault_path)
