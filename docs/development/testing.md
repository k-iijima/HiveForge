# Testing

## Test Strategy

ColonyForge targets **100% branch coverage** for all core modules.

> **Coverage is not the goal. Clarifying the preconditions, situations, and behaviors for each path is the goal.**

## Running Tests

### Unit Tests

```bash
# All tests (excluding E2E)
pytest

# Specific test file
pytest tests/test_events.py -v

# With coverage
pytest --cov=colonyforge --cov-report=html
```

### E2E Visual Tests

E2E tests use Agent UI + Playwright MCP + VLM (Ollama) for visual UI verification.

#### Prerequisites

The following services must be running in the devcontainer:

| Service | Port | Purpose |
|---------|------|---------|
| `colonyforge-playwright-mcp` | 8931 | Browser automation |
| `colonyforge-dev-ollama` | 11434 | VLM image analysis |
| `colonyforge-code-server` | 8080 | Test target (VS Code) |

#### Running E2E Tests

```bash
PLAYWRIGHT_MCP_URL="http://colonyforge-playwright-mcp:8931" \
OLLAMA_BASE_URL="http://colonyforge-dev-ollama:11434" \
VLM_HEADLESS="true" \
pytest tests/e2e/test_colonyforge_visual.py -v -m e2e
```

Or via VS Code tasks: Command Palette → `Tasks: Run Test Task` → **E2E: ビジュアルテスト (pytest)**

### VS Code Extension Tests

```bash
cd vscode-extension
npm run compile  # TypeScript error check
npm run lint     # ESLint
```

## Test Statistics

| Category | Count |
|----------|-------|
| Unit tests | ~2,370+ |
| E2E tests | 51 |
| Coverage minimum | 96% |

## Test Structure

### AAA Pattern (Arrange-Act-Assert)

```python
def test_run_completion_requires_all_tasks_done():
    """Run cannot be completed while tasks are pending.

    Verifies that the state machine enforces task completion
    before allowing Run completion.
    """
    # Arrange: Create a Run with an incomplete task
    run = create_test_run()
    create_test_task(run.run_id, status="pending")

    # Act & Assert: Attempting to complete should raise
    with pytest.raises(InvalidStateTransitionError):
        complete_run(run.run_id)
```

### Test Categories

| Marker | Description |
|--------|-------------|
| (default) | Unit tests — run with `pytest` |
| `@pytest.mark.e2e` | End-to-end tests requiring browser/containers |
| `@pytest.mark.benchmark` | Performance benchmarks |

### E2E Test Classes

| Class | Count | What it Tests |
|-------|-------|---------------|
| `TestHiveMonitorRealRendering` | 19 | Accessibility snapshot DOM verification |
| `TestHiveMonitorValueConsistency` | 16 | API → display value exact match |
| `TestHiveMonitorVLMVisualEval` | 8 | VLM layout/color/theme recognition |
| `TestHiveMonitorVLMOCR` | 10 | VLM text readability and exact value OCR |
