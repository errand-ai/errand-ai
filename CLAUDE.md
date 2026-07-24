# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **errand** project. It is in early development — the repository uses OpenSpec (spec-driven workflow) for structured change management.

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
Dockerfile             # Multi-stage: node (frontend build) + python (errand)
testing/
  docker-compose.yml   # Local dev environment (Docker Compose)
openspec/
  config.yaml          # OpenSpec config (schema: spec-driven)
  changes/             # Active changes (created by openspec new)
errand/
  main.py              # FastAPI app (API endpoints + static file serving)
  task_manager.py      # Async TaskManager (runs as background task in server process)
  mcp_server.py        # MCP Streamable HTTP server (tools: new_task, task_status, etc.)
  auth.py              # OIDC config, JWT validation, role extraction
  auth_routes.py       # /auth/login, /auth/callback, /auth/logout
  models.py            # SQLAlchemy models (Task, Tag, Setting)
  database.py          # DB engine/session setup
  llm.py               # OpenAI SDK client, LLM title generation
  container_runtime.py # Pluggable container runtime (Docker, K8s, Apple) with async interface
  alembic/             # Database migrations
frontend/
  src/                 # Vue 3 app source
  src/stores/auth.ts   # Pinia auth store (token, idToken, roles)
helm/
  errand/              # Helm chart for K8s deployment
.github/
  workflows/build.yml  # CI: build images + Helm chart, push to GHCR
```

## Tech Stack

- **Frontend**: Vue 3 + Vite + Tailwind CSS (with Pinia for state management)
- **Backend**: Python FastAPI + SQLAlchemy + Alembic
- **Task Processing**: Async TaskManager runs as a background task inside the server process (no separate worker)
- **Database**: PostgreSQL (external, app manages migrations via Alembic)
- **Deployment**: Helm chart on Kubernetes, ArgoCD
- **CI/CD**: GitHub Actions, immutable versioning from `VERSION` file
- **Auth**: Keycloak OIDC (Authorization Code flow, confidential client)

## Development Workflow

Changes are implemented sequentially — one change at a time, branching from `main`. Do not start implementing a new change until the current one is merged.
**Never push directly to main** — always use a feature branch + PR. After a PR is created, use new commits (not amend + force-push).

### 1. Create a feature branch

```bash
git checkout -b <feature-name>
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
docker compose -f testing/docker-compose.yml up --build  # Build and start all services (postgres, migrations, errand)
docker compose -f testing/docker-compose.yml down        # Stop and remove containers
```

Local URL: `http://localhost:8000` (errand serves both API and frontend static files).

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
git checkout main
git pull origin main
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
- Roles claim: `resource_access.errand.roles` (client-specific, not `realm_access.roles`)
- Logout requires `id_token_hint` parameter to Keycloak end-session endpoint
- Token + id_token delivered to frontend via URL fragment from `/auth/callback`

## Task Processing (TaskManager)

The `TaskManager` (`errand/task_manager.py`) runs as an asyncio background task inside the FastAPI server process. It replaces the previous standalone worker process.

- **Leader election**: Postgres advisory lock (`pg_try_advisory_lock`) ensures only one replica processes tasks
- **Concurrency control**: `asyncio.Semaphore` limits concurrent tasks (configurable via `max_concurrent_tasks` setting, default: 3)
- **`TASK_MANAGER_ENABLED` env var**: Set to `false` to disable task processing (default: `true`)
- **`CONTAINER_RUNTIME` env var**: `docker` (default) or `kubernetes` — selects the runtime
- **DockerRuntime**: Wraps Docker SDK, used for local dev via docker-compose (host Docker socket)
  - `TASK_RUNNER_NETWORK` env var: when set, uses named Docker network instead of `network_mode="host"`
- **KubernetesRuntime**: Creates K8s Jobs + ConfigMaps, used in production
  - Jobs labelled with `app.kubernetes.io/managed-by: content-manager-worker`
  - Input files injected via ConfigMap mounted at `/workspace`
  - Output read from `/output/result.json` (emptyDir volume)
  - Orphaned Jobs cleaned up on startup
  - Server needs a ServiceAccount with RBAC for jobs, configmaps, pods, pods/log, pods/exec
- **Container runtime async interface**: Both sync and async methods on `ContainerRuntime` base class; KubernetesRuntime has native async overrides
- **Playwright**: Configured via `PLAYWRIGHT_MCP_URL` env var (standalone service, no sidecar management)
- **Google Workspace CLI (`gws`)**: Bundled in the task-runner image at `/usr/local/bin/gws`. When a user has connected Google Workspace, the access token is injected as `GOOGLE_WORKSPACE_CLI_TOKEN` and the matching agent skills are merged into `/workspace/skills/` from `/app/system-skills/gws/` on the server. Replaces the previous `gdrive-mcp` sidecar (removed; `GDRIVE_MCP_URL` is no longer used). Pinned via `GWS_VERSION` build arg.
- **Mid-task Google token refresh**: Google access tokens have a 60-minute TTL; long-running tasks can exhaust the token mid-flight. The `execute_command` wrapper in `task-runner/main.py` detects `"status": "UNAUTHENTICATED"` in subprocess output, calls `POST ${ERRAND_API_URL}/api/google/refresh-token` (force-refresh, bypasses the 5-minute buffer), mutates `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]`, and re-runs the same command once — transparently from the LLM's perspective. Two env vars are injected alongside `GOOGLE_WORKSPACE_CLI_TOKEN`: `ERRAND_API_URL` (the errand server base URL, derived from `ERRAND_MCP_URL`) and `ERRAND_API_KEY` (a *per-task* opaque bearer — NOT `mcp_api_key`, which would be readable by every task via `/workspace/mcp.json`; the bearer is stored in Valkey under `google_refresh_token:<bearer>` → `<task_id>` with an 8-hour TTL and validated by `errand/google_routes.py`). A module-level `asyncio.Lock` deduplicates concurrent refreshes; recovery is capped at one retry per `execute_command` invocation; a `token_refreshed` event is emitted to the transcript on every refresh attempt. OneDrive mid-task refresh is not yet implemented (its token lives in the MCP `Authorization` header and requires a different mechanism).
- **System skills**: `/app/system-skills/<set>/` contains skill sets baked into the server image at build time. The task manager loads them on demand via `SYSTEM_SKILL_REGISTRY` in `task_manager.py` — each entry maps a runtime condition (over a task-context dict) to a skill set path. Currently registered: `gws` (Google token), `cloud-storage` (OneDrive injected), `hindsight` (Hindsight URL configured), `repo-context` (always), `binary-files` (always). Cloud storage, Hindsight, repo-context, and binary-file handling instructions are delivered as `SKILL.md` files in these sets — the system prompt no longer carries inline blocks for them. Registry entries with `exempt_from_profile_filter=True` (everything except `gws`) survive the per-profile external-skill filter, preserving the always-present semantics those instructions had as inline prompt blocks. Adding a new system skill set = drop the SKILL.md files under `system-skills/<set>/<skill>/` (the build context for both Dockerfiles is the repo root) and add an entry to `SYSTEM_SKILL_REGISTRY`. Skills merge into the archive at the lowest precedence (DB > git > system).
- **Local dev**: docker-compose uses `CONTAINER_RUNTIME=docker` (default)
- **LLM request timeout**: The task manager resolves the per-task LLM timeout (`profile.llm_timeout` → `task_processing_timeout` setting → `30`s default) and passes it to the runner via the `LLM_REQUEST_TIMEOUT` env var. The runner constructs `AsyncOpenAI(..., timeout=...)` with the value. Compaction has a separate `COMPACTION_TIMEOUT_SECONDS` env var that does NOT inherit from `LLM_REQUEST_TIMEOUT`.

## LLM Timeouts

There are three independent timeout settings, each scoped to one call site, plus a per-profile override:

| Setting key | Used by | Default |
|---|---|---|
| `title_generation_timeout` | `errand/llm.py:generate_title()` | 30s |
| `task_processing_timeout` | task-runner agent loop (via `LLM_REQUEST_TIMEOUT` env) | 30s |
| `transcription_timeout` | `errand/llm.py:transcribe_audio()` | 30s |

Per-profile override: `task_profiles.llm_timeout` (nullable integer). When non-null on the profile attached to a task, it supersedes `task_processing_timeout` for that task only. The renamed `title_generation_timeout` was previously called `llm_timeout`; migration `026` renames the row in place.

## Kubernetes Deployment

- **ArgoCD version**: v3.3.0 (image tag `latest`) — RBAC model follows v3 conventions
- **ArgoCD app name**: `errand` (not `errand-rancher` — the `-rancher` suffix is only on the values file)
- **ArgoCD gotcha**: Non-existent app names return `PermissionDenied` (not `NotFound`) — always verify the app name with `list_applications` before debugging RBAC
- **ArgoCD RBAC testing**: `kubectl -n argocd exec deploy/argocd-server -- argocd admin settings rbac can <user> <action> <resource> '<project>/<app>' --namespace argocd`
- **ArgoCD MCP account**: `mcpserver` local account (apiKey auth), role `readonly-user` (get, sync, restart deployments)
- **Cluster context**: `devops-consultants` / namespace: `errand`
- **Ingress**: nginx ingress controller (class `nginx`) — routes all paths to server (single service)
- **TLS**: cert-manager with `letsencrypt-prod-dns` ClusterIssuer (DNS-01 challenge; `letsencrypt-prod` uses HTTP-01 with haproxy class which doesn't work)
- **Database**: CloudNativePG — secret `errand-postgres-app`, key `uri`
- **Proxy headers**: uvicorn runs with `--proxy-headers --forwarded-allow-ips *` so `request.base_url` returns `https://` behind TLS-terminating ingress
- **ArgoCD values**: Override values at `~/github/argocd/errand-rancher-values.yaml`
- **KEDA**: Disabled for now (CRDs not installed on cluster)

## Helm Chart

- Image tags in templates default to `.Chart.AppVersion` when `values.image.tag` is empty
- CI sets `appVersion` via `helm package --app-version` from the VERSION file
- PR builds get tags like `0.4.0-pr2.<run_number>` (the `github.run_number` suffix makes every push to the PR branch a unique, increasing SemVer pre-release so ArgoCD redeploys each commit — no need to bump `VERSION` per PR commit); main builds get `0.4.0`
- Server serves frontend static files in production (Vite build output in `static/` directory)
- No separate frontend container — single combined Docker image

## MCP Server (Backend)

- MCP SDK `TransportSecuritySettings`: DNS rebinding protection is auto-enabled when FastMCP host defaults to `localhost` — rejects non-localhost Host headers with 421. Disabled via `enable_dns_rebinding_protection=False` since we use API key auth.
- MCP SDK dependency cascade: upgrading `mcp` can require bumping `pydantic`, `PyJWT`, and `uvicorn` minimum versions — check for conflicts when updating.
- Helm deploys Twitter secrets via `envFrom`/`secretRef` — K8s secret keys must match env var names exactly (e.g. `TWITTER_API_KEY`).

## Slack outbound messaging

The task-runner can post to Slack via two MCP tools on `errand/mcp_server.py`:

- `slack_message(target, text, blocks?)` — post to a channel or DM a user. `target` accepts a channel ID, `#channel`, user ID, `@user`, or email. Returns `{ok, channel, ts, error?}`.
- `slack_reply(channel, thread_ts, text, blocks?)` — reply in an existing thread. Use the `ts` returned from a previous `slack_message` (or `slack_reply`) to chain follow-ons.

The bot token is loaded server-side from encrypted credentials and is never sent to the task-runner. Posts go through `errand/platforms/slack/outbound.py` which handles auto-join for public channels (`C…` IDs only — private/DM are not auto-joined), translates HTTP 429 into a structured error, and surfaces Slack errors verbatim.

**Allowlist setting**: `slack_outbound_allowlist` (key in `settings` table, value is a JSON list). Empty / unset = unrestricted within the workspace; non-empty = strict allowlist of channel/user identifiers in any accepted form. Allowlist entries are resolved to Slack IDs and compared against the resolved target.

**Bot scopes** (audit before re-installing the Slack app): `chat:write`, `chat:write.public`, `im:write`, `users:read`, `users:read.email`, `channels:read`, `groups:read`, `channels:join`.

Both tools are catalog-only (not in `DEFAULT_HOT_TOOLS`); the task-runner discovers them via `discover_tools`.

## Frontend Layout

- App.vue `<main>` has no max-width — content fills viewport width
- Header inner div has no max-width — logo left-aligned, user controls right-aligned
- KanbanBoard wraps TaskForm in `max-w-7xl mx-auto` to keep it constrained
- Kanban columns use `flex-1` to expand to fill available width
- Local dev: errand serves everything on port 8000 (frontend static files included in Docker build)

## Python Environment

The macOS system Python is 3.9.6 (`/usr/bin/python3`) — too old for this project (requires 3.12+). Always use the errand venv:

```bash
# Errand tests (from repo root)
DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v

# Running any Python script
errand/.venv/bin/python <script.py>
```

Never use bare `python3` or `python` — they resolve to the system 3.9 which lacks required language features (e.g. `X | Y` union types, `match` statements). The errand venv at `errand/.venv/` has Python 3.12 with all project dependencies installed.

Homebrew provides newer Python versions at `/opt/homebrew/bin/python3.{12,13,14}`. To recreate the venv with a specific version:

```bash
/opt/homebrew/bin/python3.12 -m venv errand/.venv
errand/.venv/bin/pip install -r errand/requirements.txt
```

## Current State

- Version: `0.123.0` (in `VERSION` file) — bump per semver before committing (CI enforces immutable tags)
- Sequential development: one change at a time, branch from main, PR to merge (see Development Workflow)
- Deployed at: https://errand.devops-consultants.net
- Tests: 1656 errand + 65 task-runner (pytest) + 440 frontend (vitest) — CI `test` job gates both build jobs
- 52 component specs in `openspec/specs/`
