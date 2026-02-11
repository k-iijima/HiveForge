---
hide:
  - navigation
  - toc
---

# ColonyForge

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install ColonyForge and get up and running in minutes.

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-book-open-variant:{ .lg .middle } **User Guide**

    ---

    Learn concepts, CLI commands, dashboard, and agent roles.

    [:octicons-arrow-right-24: User Guide](guide/index.md)

-   :material-api:{ .lg .middle } **API Reference**

    ---

    REST API endpoints, event types, and Pydantic models.

    [:octicons-arrow-right-24: Reference](reference/api.md)

-   :material-cog:{ .lg .middle } **Architecture**

    ---

    Event sourcing, state machines, and system design.

    [:octicons-arrow-right-24: Architecture](architecture/index.md)

</div>

## What is ColonyForge?

ColonyForge is a **multi-agent collaborative development system** powered by LLMs. Specialized agents — Beekeeper, Queen Bee, Worker Bee, Sentinel Hornet, Guard Bee, Forager Bee, and Referee Bee — work together through VS Code and GitHub Copilot Chat to assist software development.

### Core Philosophy

> **Build reliable systems from reliable parts, combined in reliable ways.**

### Key Features

- **Multi-Agent Collaboration** — Hierarchical agent structure with specialized roles
- **Generate → Verify → Select** — Parallel N-candidate generation with automated judging
- **Hive/Colony Hierarchy** — Organize multiple Runs into specialized Colonies
- **Akashic Record (AR)** — Append-only immutable event log
- **Honeycomb** — Learning and improvement from execution history
- **Causal Tracing (Lineage)** — Trace "why" from any artifact
- **State Machines** — Strict lifecycle management for Hive/Colony/Run/Task
- **Evidence-first** — Decisions backed by diffs, tests, and rationale
- **MCP Integration** — Operate directly from GitHub Copilot Chat
- **VS Code Extension** — Dashboard and event log visualization
