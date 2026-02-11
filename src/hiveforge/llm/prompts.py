"""Agent prompts — backward-compatible re-export.

All prompt constants and functions have moved to ``hiveforge.prompts``.
This module re-exports them so that existing ``from hiveforge.llm.prompts import …``
statements continue to work without changes.

Canonical location: ``src/hiveforge/prompts/``
"""

from __future__ import annotations

# Re-export everything from the canonical location
from hiveforge.prompts.agents import (  # noqa: F401  — re-export
    BEEKEEPER_SYSTEM,
    QUEEN_BEE_SYSTEM,
    WORKER_BEE_SYSTEM,
    get_beekeeper_config,
    get_prompt_from_config,
    get_queen_bee_config,
    get_system_prompt,
    get_worker_bee_config,
)

__all__ = [
    "WORKER_BEE_SYSTEM",
    "QUEEN_BEE_SYSTEM",
    "BEEKEEPER_SYSTEM",
    "get_system_prompt",
    "get_prompt_from_config",
    "get_beekeeper_config",
    "get_queen_bee_config",
    "get_worker_bee_config",
]
