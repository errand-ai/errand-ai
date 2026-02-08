# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **content-manager** project. It is in early development — the repository uses OpenSpec (spec-driven workflow) for structured change management.

## OpenSpec Workflow

This project uses the `openspec` CLI (v1.1.1) with the `spec-driven` schema. Changes follow an artifact-driven workflow:

1. **Create a change**: `openspec new change "<name>"` — scaffolds `openspec/changes/<name>/`
2. **Create artifacts in order**: proposal → design + specs (parallel, both depend on proposal) → tasks
3. **Implement**: Work through tasks, marking `- [ ]` → `- [x]` as each is completed
4. **Archive**: Once all tasks are done, archive the change

When updating a design decision across artifacts, grep the change directory for the old term to ensure all references are updated (proposal, design, specs, and tasks must stay in sync).

### Key Commands

```bash
openspec new change "<name>"              # Start a new change
openspec status --change "<name>"         # Check artifact status
openspec status --change "<name>" --json  # Machine-readable status
openspec instructions <artifact> --change "<name>"        # Get artifact template/instructions
openspec instructions apply --change "<name>" --json      # Get implementation instructions
openspec list --json                      # List all active changes
openspec schemas --json                   # List available workflow schemas
```

### Slash Commands (Claude Code Skills)

- `/opsx:new` — Start a new change
- `/opsx:continue` — Create the next artifact for a change
- `/opsx:ff` — Fast-forward: create all artifacts in one go
- `/opsx:apply` — Implement tasks from a change
- `/opsx:verify` — Verify implementation matches change artifacts
- `/opsx:archive` — Archive a completed change
- `/opsx:explore` — Think through ideas before starting a change
- `/opsx:sync` — Sync delta specs to main specs

## Project Structure

```
openspec/
  config.yaml          # OpenSpec config (schema: spec-driven)
  changes/             # Active changes (created by openspec new)
backend/
  main.py              # FastAPI app (API endpoints)
  models.py            # SQLAlchemy models
  database.py          # DB engine/session setup
  worker.py            # Worker process entrypoint
  alembic/             # Database migrations
  Dockerfile
frontend/
  src/                 # Vue 3 app source
  Dockerfile
helm/
  content-manager/     # Helm chart for K8s deployment
.github/
  workflows/build.yml  # CI: build images + Helm chart, push to GHCR
```

## Tech Stack

- **Frontend**: Vue 3 + Vite + Tailwind CSS (with Pinia for state management)
- **Backend**: Python FastAPI + SQLAlchemy + Alembic
- **Worker**: Python (shared codebase with backend, separate entrypoint)
- **Database**: PostgreSQL (external, app manages migrations via Alembic)
- **Deployment**: Helm chart on Kubernetes, KEDA for worker autoscaling, ArgoCD
- **CI/CD**: GitHub Actions, immutable versioning from `VERSION` file

## Local Development

Run the full stack locally with Docker Compose before committing any changes:

```bash
docker compose up        # Start all services (postgres, migrations, backend, worker, frontend)
docker compose down      # Stop and remove containers
docker compose up --build  # Rebuild images after Dockerfile changes
```

**Always test changes locally before pushing to GitHub.** The CI pipeline builds images and ArgoCD deploys them — verify locally first.

## Serena (Code Intelligence)

This project uses a Serena MCP server for semantic code navigation. Config: `.serena/project.yml`

- Languages: Python (pylsp) + Vue — Python listed first so `.py` files use pylsp, not Vue LSP
- `pylsp` is installed into Serena's uv-managed Python, not the system Python
- After changing `.serena/project.yml`, restart Serena via `/mcp` in Claude Code, then `activate_project`
- Verify Python LSP: `get_symbols_overview` on a `.py` file should return Python symbols, not `{"Module": ["script setup"]}`

## Memory (Hindsight)

This project uses a [Hindsight](https://hindsight.vectorize.io) MCP server for persistent memory across conversations. The server is configured as `hindsight` in Claude Code's MCP settings, connected to the `claude-code` memory bank at `https://hindsight.coward.cloud/mcp/claude-code/`.

**You must use Hindsight for all memory operations in this project — do not use local auto-memory files.**

### When to store memories (retain)

- After completing a significant change or implementation
- When discovering important architectural decisions, patterns, or conventions
- When learning project-specific gotchas, workarounds, or debugging insights
- When the user explicitly asks you to remember something

### When to recall memories

- **At the start of every conversation**: recall relevant context about the project, recent changes, and conventions
- Before starting any non-trivial task: recall related past work, decisions, and patterns
- When the user references something from a previous session

### Tools

- **`mcp__hindsight__retain`** — Store a memory. Provide a clear, factual `content` string. Use `context` to categorize (e.g. `"architecture"`, `"conventions"`, `"decisions"`, `"debugging"`).
- **`mcp__hindsight__recall`** — Search memories. Provide a natural language `query`. Use `max_results` to control how many results to retrieve.

### Debugging

- Hindsight REST API is available at `https://hindsight.coward.cloud/api/` (e.g. `/api/banks` lists memory banks)

## Current State

- Version: `0.1.0` (in `VERSION` file)
- MVP scaffold complete (archived as `mvp-project-scaffold` change)
- No tests yet
- 7 component specs in `openspec/specs/`: ci-pipelines, database-migrations, helm-deployment, kanban-frontend, local-dev-environment, task-api, task-worker
