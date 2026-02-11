"""Prompt config schemas and loader — backward-compatible re-export.

All schema classes and loader have moved to ``hiveforge.prompts.loader``.
This module re-exports them so that existing imports continue to work.

Canonical location: ``src/hiveforge/prompts/loader.py``
"""

from __future__ import annotations

# Re-export everything from the canonical location
from hiveforge.prompts.loader import (  # noqa: F401  — re-export
    BeekeeperConfig,
    LLMConfig,
    PromptLoader,
    PromptTemplate,
    QueenBeeConfig,
    WorkerBeeConfig,
    get_prompt_loader,
)

__all__ = [
    "LLMConfig",
    "PromptTemplate",
    "QueenBeeConfig",
    "WorkerBeeConfig",
    "BeekeeperConfig",
    "PromptLoader",
    "get_prompt_loader",
]
