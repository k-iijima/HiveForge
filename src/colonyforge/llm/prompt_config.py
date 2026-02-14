"""Prompt config schemas and loader — backward-compatible re-export.

All schema classes and loader have moved to ``colonyforge.prompts.loader``.
This module re-exports them so that existing imports continue to work.

Canonical location: ``src/colonyforge/prompts/loader.py``
"""

from __future__ import annotations

# Re-export everything from the canonical location
from colonyforge.prompts.loader import (  # noqa: F401  — re-export
    BeekeeperConfig,
    ForagerBeeConfig,
    LLMConfig,
    PromptLoader,
    PromptTemplate,
    QueenBeeConfig,
    ScoutBeeConfig,
    WorkerBeeConfig,
    get_prompt_loader,
)

__all__ = [
    "LLMConfig",
    "PromptTemplate",
    "QueenBeeConfig",
    "WorkerBeeConfig",
    "BeekeeperConfig",
    "ForagerBeeConfig",
    "ScoutBeeConfig",
    "PromptLoader",
    "get_prompt_loader",
]
