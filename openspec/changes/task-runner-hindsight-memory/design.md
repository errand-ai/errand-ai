## Context

The task runner executes in ephemeral Docker containers — each task starts with zero context about past executions. The agent receives a system prompt, user prompt, and MCP tools, but has no knowledge of previous tasks, past decisions, or accumulated learnings.

Hindsight is a memory platform already deployed in the devops-consultants K8s cluster at `http://hindsight-api.hindsight.svc.cluster.local:8888`. It provides three core operations: retain (store facts), recall (search memories), and reflect (synthesised reasoning over memories). It exposes both a REST API and a built-in MCP server at `/mcp/{bank_id}/`.

The worker currently injects MCP servers (Perplexity, content-manager backend) and system prompt sections following a consistent pattern: check config → inject into `mcpServers` dict → append usage instructions to system prompt.

## Goals / Non-Goals

**Goals:**
- Give the task runner agent persistent memory across task executions via Hindsight
- Pre-load relevant context before each task to reduce cold-start and avoid wasting agent turns on recall
- Follow the existing worker injection patterns for MCP servers and system prompt sections
- Support local development with Hindsight via docker-compose

**Non-Goals:**
- Per-user or per-task memory banks (single shared bank for now)
- Mental model tools (retain/recall/reflect are sufficient for v1)
- Hindsight authentication (not needed for internal K8s service or local dev)
- Admin UI for Hindsight configuration (use existing settings API)

## Decisions

### Decision 1: Two-layer integration (MCP + worker pre-loading)

**Choice:** Integrate Hindsight at two layers:
1. **MCP layer** — Inject Hindsight as an MCP server in the task runner's `mcp.json`, giving the agent access to `retain`, `recall`, and `reflect` tools during execution
2. **Worker layer** — Before launching the container, the worker calls Hindsight's REST API to recall context relevant to the task and injects it into the system prompt

**Why:** MCP-only means the agent must spend turns on recall at the start of every task. Worker pre-loading ensures the agent always starts with relevant context. MCP tools let the agent retain new learnings and do ad-hoc recall/reflect during execution.

**Alternatives considered:**
- MCP only: Simpler but wastes agent turns on initial recall; agent might forget to recall
- REST API only (worker): No agent agency over memory; can't retain during execution
- Python SDK in task-runner: Adds a dependency to the task-runner image and requires non-MCP code paths

### Decision 2: Use REST API for worker pre-loading (not Python SDK)

**Choice:** The worker calls Hindsight's REST API directly via `httpx` (already a backend dependency) rather than adding the `hindsight-client` Python package.

**Why:** The worker only needs one operation (recall). Adding a whole SDK for one HTTP call is overkill. `httpx` is already available in the backend. The REST API is simple: `POST /api/banks/{bank_id}/recall` with `{"query": "..."}`.

**Alternatives considered:**
- `hindsight-client` Python SDK: Clean interface but new dependency for one call
- Skip pre-loading entirely: Agent handles everything via MCP; wastes turns

### Decision 3: Single-bank MCP endpoint with bank ID in URL

**Choice:** Use the single-bank MCP endpoint pattern: `http://hindsight-api:8888/mcp/{bank_id}/`. The bank ID comes from a new `hindsight_bank_id` admin setting (default: `content-manager-tasks`).

**Why:** Single-bank mode is simpler — the agent doesn't need to specify `bank_id` on every tool call. The bank is scoped to this application's tasks. URL-based bank selection is the highest priority in Hindsight's resolution order.

**Alternatives considered:**
- Multi-bank mode with `X-Bank-Id` header: More flexible but unnecessary complexity for v1
- Hardcoded bank ID: Less configurable; different environments may want different banks

### Decision 4: Hindsight injection follows existing pattern

**Choice:** Add Hindsight MCP injection in `process_task_in_container` following the same pattern as Perplexity and content-manager backend:
1. Check if `HINDSIGHT_URL` env var is set
2. Inject `hindsight` entry into `mcpServers` dict
3. Append memory usage instructions to system prompt

**Why:** Consistency with existing code. The pattern is proven and well-understood. Environment variable gating means Hindsight is opt-in per deployment.

### Decision 5: Docker-compose uses slim image with LiteLLM

**Choice:** Add Hindsight to docker-compose using the `slim` image (~500MB) with embedded pg0 storage, pointed at the existing LiteLLM endpoint for LLM operations.

**Why:** The `latest` image is ~9GB (includes local ML models) which is excessive for local dev. The slim image requires an external LLM provider — we already have LiteLLM configured via `OPENAI_BASE_URL`. Embedded pg0 avoids needing a second PostgreSQL instance.

**Alternatives considered:**
- `latest` (full) image: Self-contained but 9GB download
- Shared PostgreSQL: Possible but adds migration complexity and risks conflicts

### Decision 6: Worker recall query constructed from task context

**Choice:** The worker constructs a recall query from the task title and description, limited to a reasonable token budget. The recalled context is injected as a `## Relevant Context from Memory` section in the system prompt.

**Why:** The task title/description is the most relevant signal for what memories to retrieve. Injecting into the system prompt means the agent sees context before it starts reasoning, without spending tool-call turns.

## Risks / Trade-offs

- **Memory noise**: Recall may return irrelevant memories, cluttering the system prompt → Mitigation: Use a conservative `max_tokens` limit (2048) for pre-loaded context; agent can always recall more via MCP if needed
- **Hindsight unavailability**: If Hindsight is down, worker pre-loading and MCP tools both fail → Mitigation: Worker catches recall failures gracefully (log warning, continue without context); MCP connection failure is already handled by the task runner's existing error handling
- **Turn cost**: MCP retain/recall/reflect consume agent turns → Mitigation: Pre-loading reduces the need for recall turns; retain is low-cost (one call at end of task); acceptable trade-off for persistent memory
- **Docker-compose startup time**: Hindsight slim image needs to initialise on first run → Mitigation: Worker doesn't depend on Hindsight being healthy; tasks still run without memory
