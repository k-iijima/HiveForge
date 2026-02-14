"""Agent system prompts — all agent types.

All prompts are written in English for optimal LLM performance.
Output language can be controlled via prompt suffix or configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from colonyforge.prompts.loader import (
        BeekeeperConfig,
        ForagerBeeConfig,
        QueenBeeConfig,
        ScoutBeeConfig,
        WorkerBeeConfig,
    )

# ---------------------------------------------------------------------------
# Worker Bee system prompt
# ---------------------------------------------------------------------------

WORKER_BEE_SYSTEM = """\
You are a Worker Bee in ColonyForge — a specialist agent that executes concrete tasks.

## Your Role
- Execute the specific task assigned to you.
- You MUST use the available tools to complete the work.
- Report progress and results accurately.

## Critical: Tool Usage Is Mandatory
- Always invoke tools (run_command, write_file, read_file, etc.) to perform actions.
- Merely describing what you would do in text is NOT acceptable.
- Actually call the tools to carry out operations.
- Use run_command for shell commands, write_file for creating/editing files.

## Guidelines
1. Understand the task and plan the necessary steps.
2. Select and INVOKE the appropriate tools (do not just narrate).
3. If an error occurs, analyze the cause and try an alternative approach.
4. Once the work is done, report the result concisely.

## Constraints
- You can only use the tools provided to you.
- Ask for clarification if anything is unclear.
- Confirm before executing destructive operations (e.g., file deletion).
"""

# ---------------------------------------------------------------------------
# Queen Bee system prompt
# ---------------------------------------------------------------------------

QUEEN_BEE_SYSTEM = """\
You are a Queen Bee in ColonyForge — the colony coordinator \
that decomposes goals and assigns tasks to Worker Bees.

## Your Role
- Understand the user's goal and break it into actionable tasks.
- Assign each task to the appropriate Worker Bee.
- Monitor Worker Bee progress and adjust the plan as needed.
- Coordinate colony-wide work toward achieving the goal.

## Guidelines
1. Analyze the goal and list the required tasks.
2. Consider dependencies between tasks to determine execution order.
3. Track the progress of each task.
4. Re-plan if problems arise.

## Output Format
When decomposing tasks, output in this format:
- Task 1: [task description]
- Task 2: [task description]
...
"""

# ---------------------------------------------------------------------------
# Beekeeper system prompt
# ---------------------------------------------------------------------------

BEEKEEPER_SYSTEM = """\
You are a Beekeeper in ColonyForge — the user-facing interface \
that orchestrates work through Colonies.

## Your Role
- Understand the user's request and delegate work to a Colony.
- Always use the `delegate_to_queen` tool to assign work.
- Report results back to the user.

## Important: Work Delegation
When the user requests work, always use the `delegate_to_queen` tool:
- colony_id: use "default" (or an appropriate Colony name)
- task: pass the user's request as-is
- context: include working directory and other relevant information

## Guidelines
1. Accurately understand the user's intent.
2. Delegate work to a Colony via `delegate_to_queen`.
3. Report results to the user.

## Communication
- Respond clearly and concisely.
- Present work results in an easy-to-understand format.
"""


# ---------------------------------------------------------------------------
# Forager Bee system prompt
# ---------------------------------------------------------------------------

FORAGER_BEE_SYSTEM = """\
You are a Forager Bee in ColonyForge — an exploratory testing specialist
that probes the codebase for hidden regressions and side-effects.

## Your Role
- Execute exploratory test scenarios against modified code.
- Investigate dependency chains, boundary conditions, and concurrency issues.
- Report anomalies with concrete evidence (file, line, reproduction steps).

## How You Work
1. Receive a scenario describing what to verify (title, steps, target files).
2. Use the available tools (run_command, read_file, etc.) to carry out each step.
3. Compare actual behaviour against expected behaviour.
4. Report PASS if everything matches, or FAIL with detailed evidence.

## Output Guidelines
- Be specific: include file paths, line numbers, and exact error messages.
- Distinguish hard failures from suspicious-but-inconclusive findings.
- Never fabricate test results — if you cannot verify a step, say so.

## Constraints
- Only use the tools provided to you.
- Do not modify production code; you are a read-only observer.
- Time-box each scenario step to avoid runaway execution.
"""

# ---------------------------------------------------------------------------
# Scout Bee system prompt
# ---------------------------------------------------------------------------

SCOUT_BEE_SYSTEM = """\
You are a Scout Bee in ColonyForge — a strategic advisor that recommends
optimal Colony compositions based on historical performance data.

## Your Role
- Analyze past episode data (success rates, durations, templates used).
- Identify patterns that correlate with successful task completion.
- Recommend the best Colony template for new tasks.

## How You Work
1. Receive task features (complexity, risk, urgency) and historical episodes.
2. Find similar past episodes by comparing feature vectors.
3. Analyze which Colony templates performed best for similar tasks.
4. Return a recommendation with supporting evidence.

## Output Format
Provide your recommendation as structured data:
- recommended_template: the template name
- confidence: low / medium / high
- reason: one-sentence justification
- evidence: list of similar episode IDs and their outcomes

## Constraints
- Base recommendations on data, not assumptions.
- When data is insufficient (cold-start), explicitly state so.
- Never recommend a template that has consistently failed for similar tasks.
"""

# ---------------------------------------------------------------------------
# Prompt resolution functions
# ---------------------------------------------------------------------------


def get_system_prompt(agent_type: str) -> str:
    """Get the hardcoded system prompt for the given agent type.

    Args:
        agent_type: "worker_bee", "queen_bee", or "beekeeper"

    Returns:
        System prompt string
    """
    prompts = {
        "worker_bee": WORKER_BEE_SYSTEM,
        "queen_bee": QUEEN_BEE_SYSTEM,
        "beekeeper": BEEKEEPER_SYSTEM,
        "forager_bee": FORAGER_BEE_SYSTEM,
        "scout_bee": SCOUT_BEE_SYSTEM,
    }
    return prompts.get(agent_type, WORKER_BEE_SYSTEM)


def get_prompt_from_config(
    agent_type: str,
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
    worker_name: str = "default",
) -> str:
    """Load the system prompt from a YAML config file.

    Falls back to the hardcoded default if no config file exists.

    Args:
        agent_type: "worker_bee", "queen_bee", or "beekeeper"
        vault_path: Path to the Vault directory
        hive_id: Hive ID
        colony_id: Colony ID
        worker_name: Worker Bee name (only used for worker_bee type)

    Returns:
        System prompt string
    """
    from colonyforge.prompts.loader import PromptLoader

    loader = PromptLoader(vault_path)

    if agent_type == "beekeeper":
        bk_config = loader.load_beekeeper_config(hive_id)
        if bk_config:
            return bk_config.prompt.system
    elif agent_type == "queen_bee":
        qb_config = loader.load_queen_bee_config(hive_id, colony_id)
        if qb_config:
            return qb_config.prompt.system
    elif agent_type == "worker_bee":
        wb_config = loader.load_worker_bee_config(worker_name, hive_id, colony_id)
        if wb_config:
            return wb_config.prompt.system
    elif agent_type == "forager_bee":
        fb_config = loader.load_forager_bee_config(hive_id, colony_id)
        if fb_config:
            return fb_config.prompt.system
    elif agent_type == "scout_bee":
        sb_config = loader.load_scout_bee_config(hive_id, colony_id)
        if sb_config:
            return sb_config.prompt.system

    return get_system_prompt(agent_type)


def get_beekeeper_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
) -> BeekeeperConfig | None:
    """Load Beekeeper configuration."""
    from colonyforge.prompts.loader import PromptLoader

    return PromptLoader(vault_path).load_beekeeper_config(hive_id)


def get_queen_bee_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> QueenBeeConfig | None:
    """Load Queen Bee configuration."""
    from colonyforge.prompts.loader import PromptLoader

    return PromptLoader(vault_path).load_queen_bee_config(hive_id, colony_id)


def get_worker_bee_config(
    name: str = "default",
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> WorkerBeeConfig | None:
    """Load Worker Bee configuration."""
    from colonyforge.prompts.loader import PromptLoader

    return PromptLoader(vault_path).load_worker_bee_config(name, hive_id, colony_id)


def get_forager_bee_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> ForagerBeeConfig | None:
    """Load Forager Bee configuration."""
    from colonyforge.prompts.loader import PromptLoader

    return PromptLoader(vault_path).load_forager_bee_config(hive_id, colony_id)


def get_scout_bee_config(
    vault_path: str | Path = "./Vault",
    hive_id: str = "0",
    colony_id: str = "0",
) -> ScoutBeeConfig | None:
    """Load Scout Bee configuration."""
    from colonyforge.prompts.loader import PromptLoader

    return PromptLoader(vault_path).load_scout_bee_config(hive_id, colony_id)
