# Installation

## Prerequisites

- Python 3.11 or later
- VS Code (recommended)
- Docker (for devcontainer)

## Devcontainer (Recommended)

The simplest way to start is with the included devcontainer, which eliminates environment differences and guarantees a reproducible build.

1. Open the project in VS Code
2. Command Palette → **Dev Containers: Reopen in Container**

The devcontainer includes:

- Python 3.12
- All dependencies pre-installed (`pip install -e ".[dev]"`)
- Development tools: Ruff, pytest, mypy
- VS Code extensions: Python, Pylance, Ruff

## Local Installation

If you cannot use devcontainers:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

## GPU Support (Windows + NVIDIA)

Rancher Desktop does not support GPU. Use Docker on Ubuntu WSL:

```powershell
# 1. Start Docker in Ubuntu WSL
wsl -d Ubuntu -e sudo service docker start

# 2. Test GPU access
wsl -d Ubuntu docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

Or use the provided script:

```powershell
.\scripts\start-wsl-docker.cmd
```

## Verify Installation

```bash
# Check CLI is available
colonyforge --help

# Start the API server
colonyforge server

# Open Swagger UI
# http://localhost:8000/docs
```
