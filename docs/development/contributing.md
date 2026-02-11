# Development Guide

## Core Philosophy

> **Build reliable systems from reliable parts, combined in reliable ways.**

## Development Environment

### Devcontainer (Recommended)

```bash
# Open in VS Code
# Command Palette → "Dev Containers: Reopen in Container"
```

The devcontainer includes Python 3.12, all dependencies, and development tools.

### Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Coding Standards

### Python Style

- **Python 3.12+** with type hints required
- **Ruff** for formatting and linting
- **Docstrings** in Google style (Japanese OK)
- **Line length**: 100 characters

### File Organization

- **Target ≤200 lines per file** — split if exceeded
- **One file, one responsibility**
- **No circular imports** — dependencies are unidirectional
- **Reusable utilities** in dedicated modules

### Pydantic Models

```python
from pydantic import BaseModel, Field, ConfigDict

class TaskCreatedEvent(BaseModel):
    """Task creation event"""
    model_config = ConfigDict(strict=True, frozen=True)

    task_id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., min_length=1, max_length=200)
```

### Fail-Fast Principle

- **No implicit fallbacks** — raise exceptions immediately
- **No broad `except Exception`** — catch specific types only
- **No error swallowing** — no `except: pass`
- **No string-wrapped errors** — propagate exceptions, don't return `{"error": str(e)}`

## TDD Workflow

1. Write a test (RED)
2. Verify it fails
3. Write minimal implementation (GREEN)
4. Commit
5. Refactor (REFACTOR)
6. Commit
7. Next test

### AAA Pattern

```python
def test_event_hash_excludes_hash_field():
    """Hash field itself is excluded from hash computation"""
    # Arrange
    data_without_hash = {"type": "test", "value": 1}
    data_with_hash = {"type": "test", "value": 1, "hash": "ignored"}

    # Act
    hash_without = compute_hash(data_without_hash)
    hash_with = compute_hash(data_with_hash)

    # Assert
    assert hash_without == hash_with
```

### Test Guidelines

1. Docstrings explain **purpose** and **importance**
2. Arrange/Act/Assert sections marked with comments
3. Variable names express **intent**, not position (e.g., `data_without_hash`, not `data1`)
4. One test = one behavior

## Commit Conventions

- `feat:` — New feature
- `fix:` — Bug fix
- `test:` — Test changes
- `chore:` — Build/CI changes
- `docs:` — Documentation
- `refactor:` — Code restructuring

Each commit must leave tests passing.

## Building Documentation

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Live preview
mkdocs serve

# Build static site
mkdocs build --strict

# Build output in site/
```
