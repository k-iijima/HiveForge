# Git Workflow

ColonyForge follows a Colony-based parallel development workflow.

## Branch Model

| Branch | Purpose | Lifetime |
|--------|---------|----------|
| `master` | Release only (protected) | Permanent |
| `develop` | Integration trunk | Permanent |
| `feat/<hive>/<colony>/<ticket>-<slug>` | Colony work | **Short-lived** (1–3 days) |
| `fix/…`, `hotfix/…` | Bug fixes | Short-lived |
| `exp/…` | Experiments (disposable) | Variable |

## Worktree Usage

Use `git worktree add` for parallel Colony development (max 3 worktrees):

```bash
git worktree add ../wt-api -b feat/ec-site/api/123-login develop
```

## Rebase / Merge Rules

| Source | Target | Strategy |
|--------|--------|----------|
| Personal branch | `develop` | Rebase (linear history) |
| Shared branch | `develop` | Merge (preserve history) |
| `develop` | `master` | Merge --no-ff (release boundary) |

## PR Gate Checks

All PRs must pass:

| Gate | Description |
|------|-------------|
| `guard-l1` | Lint / Unit tests / Schema validation |
| `guard-l2` | Design consistency check |
| `forager-regression` | Regression testing |
| `sentinel-safety` | Safety checks |

## Commit Conventions

```
feat: Add login endpoint
fix: Handle null task result
test: Add KPI improvement cycle tests
chore: Update dependencies
docs: Add CLI reference
refactor: Extract event serialization
```

Each commit must leave all tests passing.
