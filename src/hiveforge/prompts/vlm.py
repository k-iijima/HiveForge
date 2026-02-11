"""VLM (Vision Language Model) prompts.

Prompts for screenshot analysis, UI comparison,
page description, and element finding.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Screenshot analysis (OllamaClient.analyze_screenshot)
# ---------------------------------------------------------------------------

SCREENSHOT_ANALYSIS_PROMPT = """\
Analyze this screenshot and describe:
1. Main UI elements visible (sidebar, editor, panels, buttons, etc.)
2. Any text content visible on screen
3. Current state of the application
4. Any errors, warnings, or notifications visible

{context}

Provide a structured analysis."""


def format_screenshot_prompt(context: str = "") -> str:
    """Format the screenshot analysis prompt with optional context."""
    ctx = f"Additional context: {context}" if context else ""
    return SCREENSHOT_ANALYSIS_PROMPT.format(context=ctx)


# ---------------------------------------------------------------------------
# UI comparison (LocalVLMAnalyzer.compare)
# ---------------------------------------------------------------------------

UI_COMPARISON_PROMPT = """\
Compare these two UI states:

BEFORE:
{before}

AFTER:
{after}

What changed between these two states? List the differences."""


def format_comparison_prompt(before: str, after: str) -> str:
    """Format the UI comparison prompt with before/after analysis."""
    return UI_COMPARISON_PROMPT.format(before=before, after=after)


# ---------------------------------------------------------------------------
# Page description (AgentUIHandlers.handle_describe_page)
# ---------------------------------------------------------------------------

DESCRIBE_PAGE_PROMPT = "Describe this screen in detail."

DESCRIBE_PAGE_PROMPT_WITH_FOCUS = (
    'Describe this screen in detail. Pay special attention to "{focus}".'
)


def format_describe_page_prompt(focus: str = "") -> str:
    """Format the describe-page prompt with optional focus."""
    if focus:
        return DESCRIBE_PAGE_PROMPT_WITH_FOCUS.format(focus=focus)
    return DESCRIBE_PAGE_PROMPT


# ---------------------------------------------------------------------------
# Element finding (AgentUIHandlers.handle_find_element)
# ---------------------------------------------------------------------------

FIND_ELEMENT_PROMPT = """\
Locate "{description}" on this screen.

If found, respond in this JSON format:
{{"found": true, "x": <x-coordinate>, "y": <y-coordinate>, \
"description": "element description"}}

If not found:
{{"found": false, "reason": "why not found"}}"""


def format_find_element_prompt(description: str) -> str:
    """Format the find-element prompt with the target description."""
    return FIND_ELEMENT_PROMPT.format(description=description)
