# Dashboard

The HiveForge VS Code extension provides a real-time dashboard for monitoring Runs, Tasks, and KPIs.

## Installation

The extension is bundled with the devcontainer. For manual installation:

```bash
cd vscode-extension
npm install
npm run compile
```

Then install the `.vsix` package via VS Code's Extensions view.

## Hive Monitor

The **Hive Monitor** is a Webview panel showing:

### KPI Gauges

Visual gauges displaying key performance indicators:

| Gauge | Description | Good Value |
|-------|-------------|------------|
| Correctness | Task completion without failures | ≥ 80% |
| Guard Pass Rate | Quality verification pass rate | ≥ 70% |
| Repeatability | Consistency across runs | ≥ 60% |
| Avg Cycle Time | Average task duration | Lower is better |
| Collaboration Score | Cross-colony coordination | ≥ 70% |

Gauge colors indicate status:

- :material-circle:{ style="color: #4caf50" } **Green** (≥ 60%) — Healthy
- :material-circle:{ style="color: #ff9800" } **Orange** (30–59%) — Warning
- :material-circle:{ style="color: #f44336" } **Red** (< 30%) — Critical

### Run Overview

- Current Run ID and status
- Task count breakdown (completed / total)
- Task outcome distribution

### Evaluation Summary

When Honeycomb episodes are recorded, the dashboard shows:

- Episode count
- Per-Colony KPI breakdown
- Improvement trends

## Event Log TreeView

The sidebar **Event Log** view displays all events in chronological order:

- Event type icons
- Timestamp and Run ID
- Click to view event details

## Status Bar

The bottom status bar shows:

- Current Run status (icon + text)
- Click to open Hive Monitor

## Refresh

Data refreshes automatically on Run state changes. Manual refresh:

- Click the refresh button in the Hive Monitor toolbar
- Command Palette → **HiveForge: Refresh Dashboard**

## Configuration

The extension connects to the API server at `http://localhost:8000` by default.

Configure in VS Code settings:

```json
{
  "hiveforge.apiUrl": "http://localhost:8000"
}
```
