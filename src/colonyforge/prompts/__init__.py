"""Centralized prompt and agent configuration management.

All system prompts, prompt templates, YAML configuration schemas,
and prompt loading logic are consolidated here.

Directory structure:
    prompts/
    ├── __init__.py          # Public API (this file)
    ├── agents.py            # Agent system prompts (Beekeeper, Queen, Worker)
    ├── task_decomposition.py # Task decomposition prompt
    ├── vlm.py               # VLM / visual analysis prompts
    ├── loader.py            # YAML prompt loader (PromptLoader)
    └── defaults/            # Default YAML agent configs
        ├── worker_bee.yml
        ├── queen_bee.yml
        └── beekeeper.yml

Usage:
    from colonyforge.prompts import (
        WORKER_BEE_SYSTEM,
        QUEEN_BEE_SYSTEM,
        BEEKEEPER_SYSTEM,
        TASK_DECOMPOSITION_SYSTEM,
        TOOL_USE_RETRY_PROMPT,
        get_system_prompt,
        get_prompt_from_config,
        PromptLoader,
        PromptTemplate,
    )
"""

from __future__ import annotations

from colonyforge.prompts.agents import (
    BEEKEEPER_SYSTEM,
    FORAGER_BEE_SYSTEM,
    QUEEN_BEE_SYSTEM,
    SCOUT_BEE_SYSTEM,
    WORKER_BEE_SYSTEM,
    get_prompt_from_config,
    get_system_prompt,
)
from colonyforge.prompts.loader import (
    BeekeeperConfig,
    ForagerBeeConfig,
    PromptLoader,
    PromptTemplate,
    QueenBeeConfig,
    ScoutBeeConfig,
    WorkerBeeConfig,
    get_prompt_loader,
)
from colonyforge.prompts.task_decomposition import TASK_DECOMPOSITION_SYSTEM
from colonyforge.prompts.vlm import (
    DESCRIBE_PAGE_PROMPT,
    FIND_ELEMENT_PROMPT,
    SCREENSHOT_ANALYSIS_PROMPT,
    UI_COMPARISON_PROMPT,
)

# Re-exported from runner — kept as class constant but defined here for reference
TOOL_USE_RETRY_PROMPT = (
    "Your response did not include any tool calls. "
    "You MUST use the available tools (run_command, write_file, read_file, etc.) "
    "to complete this task. Do not just describe what you would do — "
    "actually invoke the tools."
)

__all__ = [
    # Agent system prompts
    "WORKER_BEE_SYSTEM",
    "QUEEN_BEE_SYSTEM",
    "BEEKEEPER_SYSTEM",
    "FORAGER_BEE_SYSTEM",
    "SCOUT_BEE_SYSTEM",
    # Task decomposition
    "TASK_DECOMPOSITION_SYSTEM",
    # Tool retry
    "TOOL_USE_RETRY_PROMPT",
    # VLM prompts
    "SCREENSHOT_ANALYSIS_PROMPT",
    "UI_COMPARISON_PROMPT",
    "DESCRIBE_PAGE_PROMPT",
    "FIND_ELEMENT_PROMPT",
    # Prompt resolution
    "get_system_prompt",
    "get_prompt_from_config",
    # Loader & schemas
    "PromptLoader",
    "PromptTemplate",
    "QueenBeeConfig",
    "WorkerBeeConfig",
    "BeekeeperConfig",
    "ForagerBeeConfig",
    "ScoutBeeConfig",
    "get_prompt_loader",
]
