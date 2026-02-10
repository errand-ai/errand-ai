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
  auth.py              # OIDC config, JWT validation, role extraction
  auth_routes.py       # /auth/login, /auth/callback, /auth/logout
  models.py            # SQLAlchemy models (Task, Tag, Setting)
  database.py          # DB engine/session setup
  llm.py               # OpenAI SDK client, LLM title generation
  worker.py            # Worker process entrypoint
  alembic/             # Database migrations
  Dockerfile
frontend/
  src/                 # Vue 3 app source
  src/stores/auth.ts   # Pinia auth store (token, idToken, roles)
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
- **Auth**: Keycloak OIDC (Authorization Code flow, confidential client)

## Development Workflow

All new feature development **must** use git worktrees. Each feature gets its own branch and worktree, keeping `main` clean and allowing parallel work on multiple features.

### 1. Create a feature branch with a git worktree

```bash
# From the main repo directory
git worktree add ../content-manager-<feature-name> -b <feature-name>
cd ../content-manager-<feature-name>
```

Use descriptive branch names (e.g. `add-task-queue`, `fix-auth-redirect`, `update-helm-probes`).

### 2. Bump the VERSION file (semantic versioning)

Before any code changes, increment the version in `VERSION` following [semver](https://semver.org/):

- **MAJOR** (X.0.0) — breaking API or data model changes
- **MINOR** (0.X.0) — new features, backwards-compatible additions
- **PATCH** (0.0.X) — bug fixes, minor corrections, config tweaks

CI enforces immutable tags — if you forget to bump, the pipeline will fail on duplicate tags.

### 3. Develop and test locally

Run the full stack locally with Docker Compose and verify changes **before committing**:

```bash
docker compose up --build  # Build and start all services (postgres, migrations, backend, worker, frontend)
docker compose down        # Stop and remove containers
```

Local URLs: frontend at `http://localhost:3000`, backend API at `http://localhost:8000`.

**Every commit must pass local testing.** Do not commit code that hasn't been verified with `docker compose up --build`. The CI pipeline builds images and ArgoCD deploys them — broken commits on a branch waste CI resources and risk bad deployments.

### 4. Push and create a pull request

```bash
git push -u origin <feature-name>
gh pr create --title "<short description>" --body "<details>"
```

### 5. Verify the PR deployment before merging

After pushing, CI builds container images and the Helm chart. **Before merging the PR**:

- Confirm the GitHub Actions build completes successfully (images + Helm chart pushed to GHCR)
- Verify the built images and Helm chart deploy cleanly on Kubernetes (ArgoCD sync or manual `helm upgrade --dry-run`)
- Check the running deployment is functional (pod health, ingress routing, basic smoke test)

**Do not merge a PR until the built artifacts have been validated on Kubernetes.** A green CI build alone is not sufficient — the deployment must work end-to-end.

### 6. Clean up after merge

```bash
# After the PR is merged, remove the worktree
cd /Users/rob/github/content-manager
git worktree remove ../content-manager-<feature-name>
git branch -d <feature-name>  # delete local branch (remote is deleted by GitHub on merge)
```

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

## Authentication (Keycloak SSO)

- OIDC Authorization Code flow: backend is the confidential client, handles code exchange
- JWT audience validation disabled — Keycloak sets `aud: "account"`, not the client_id
- Roles claim: `resource_access.content-manager.roles` (client-specific, not `realm_access.roles`)
- Logout requires `id_token_hint` parameter to Keycloak end-session endpoint
- Token + id_token delivered to frontend via URL fragment from `/auth/callback`

## Kubernetes Deployment

- **ArgoCD version**: v3.3.0 (image tag `latest`) — RBAC model follows v3 conventions
- **ArgoCD app name**: `content-manager` (not `content-manager-rancher` — the `-rancher` suffix is only on the values file)
- **ArgoCD gotcha**: Non-existent app names return `PermissionDenied` (not `NotFound`) — always verify the app name with `list_applications` before debugging RBAC
- **ArgoCD RBAC testing**: `kubectl -n argocd exec deploy/argocd-server -- argocd admin settings rbac can <user> <action> <resource> '<project>/<app>' --namespace argocd`
- **ArgoCD MCP account**: `mcpserver` local account (apiKey auth), role `readonly-user` (get, sync, restart deployments)
- **Cluster context**: `devops-consultants` / namespace: `content-manager`
- **Ingress**: nginx ingress controller (class `nginx`) — routes `/api` and `/auth` to backend, `/` to frontend
- **TLS**: cert-manager with `letsencrypt-prod-dns` ClusterIssuer (DNS-01 challenge; `letsencrypt-prod` uses HTTP-01 with haproxy class which doesn't work)
- **Database**: CloudNativePG — secret `content-manager-postgres-app`, key `uri`
- **Frontend in K8s**: nginx serves static files only (no proxy_pass); ingress handles path routing
- **Proxy headers**: uvicorn runs with `--proxy-headers --forwarded-allow-ips *` so `request.base_url` returns `https://` behind TLS-terminating ingress
- **ArgoCD values**: Override values at `~/github/argocd/apps/content-manager-rancher-values.yaml`
- **KEDA**: Disabled for now (CRDs not installed on cluster)

## Helm Chart

- Image tags in templates default to `.Chart.AppVersion` when `values.image.tag` is empty
- CI sets `appVersion` via `helm package --app-version` from the VERSION file
- PR builds get tags like `0.4.0-pr2`; main builds get `0.4.0`
- Static assets in `frontend/public/` must have `chmod 644` or nginx returns 403 (Docker copies permissions as-is)

## Frontend Layout

- App.vue `<main>` has no max-width — content fills viewport width
- Header inner div has no max-width — logo left-aligned, user controls right-aligned
- KanbanBoard wraps TaskForm in `max-w-7xl mx-auto` to keep it constrained
- Kanban columns use `flex-1` to expand to fill available width
- Local dev frontend runs on port 3000 (nginx), backend on 8000

## Current State

- Version: `0.8.0` (in `VERSION` file) — bump per semver before committing (CI enforces immutable tags)
- All feature work uses git worktrees + feature branches + PRs (see Development Workflow)
- Deployed at: https://content-manager.devops-consultants.net
- Tests: 85 backend (pytest) + 84 frontend (vitest) — CI `test` job gates both build jobs
- 19 component specs in `openspec/specs/`
