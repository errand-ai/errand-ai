## Context

The task runner agent executes tasks in disposable Docker containers created inside a DinD sidecar. Each task-runner container uses `network_mode="host"` on the DinD daemon, sharing the worker pod's network namespace. The worker processes tasks sequentially — one at a time per pod. MCP servers are injected into the task-runner's configuration as HTTP URLs (Streamable HTTP transport), and the agent connects to them on startup.

Currently the agent has no browser automation capability. It cannot interact with web UIs for testing, nor browse websites that block simple HTTP clients. The Playwright MCP server (`@playwright/mcp`) provides full browser control via MCP tools but cannot handle concurrent sessions — each instance serves one client at a time.

## Goals / Non-Goals

**Goals:**

- Give the task runner agent full browser automation (navigate, click, fill forms, take screenshots, evaluate JS)
- Support both automated UI testing and general web browsing use cases
- Maintain the distroless security posture of the task-runner image
- Ensure browser failures (OOM, crash) don't kill the worker pod or lose task state
- Prevent context window overflow from accumulated screenshots in long agent runs

**Non-Goals:**

- Modifying the task-runner base image (stays distroless)
- Multi-browser support (Chromium only for v1)
- Persistent browser state across tasks
- Conditional Playwright startup based on task content (always start for v1, optimise later)
- Browser pool / shared Playwright service (each worker gets its own instance)

## Decisions

### Decision 1: DinD sibling container (not pod sidecar)

The Playwright MCP server runs as a second container inside DinD, created and destroyed alongside the task-runner for each task.

**Alternatives considered:**
- **Pod sidecar** (always-running container in the worker pod): Simpler Helm config, but requires state cleanup between tasks, wastes resources when idle, and browser crashes affect all future tasks until the sidecar restarts.
- **Embedded in task-runner** (Playwright inside distroless): Would require abandoning distroless and bloating the task-runner image by ~1-2GB.
- **Shared browser pool** (cluster-wide Browserless service): Adds infrastructure complexity and a shared point of failure for something that benefits from per-task isolation.

**Rationale:** DinD sibling matches the existing disposable-sandbox philosophy. Fresh browser per task, automatic cleanup, no state leakage, only uses resources during task execution. The worker already manages container lifecycles — adding a second is a natural extension.

### Decision 2: Streamable HTTP transport on port 8931

`@playwright/mcp` serves both Streamable HTTP (`/mcp`) and legacy SSE (`/sse`) on the same port when started with `--port`. The task-runner already uses `MCPServerStreamableHttp` for all MCP connections.

**Configuration:** `npx @playwright/mcp --port 8931 --host 0.0.0.0`

The task-runner connects via `http://localhost:8931/mcp` in the injected MCP config. Port 8931 is arbitrary and chosen to avoid conflicts with other services.

### Decision 3: Docker-level memory limits on Playwright container

The Playwright container gets `--memory` and `--memory-swap` flags when created in DinD. If Chromium exceeds the limit, Docker OOM-kills only the Playwright container. The task-runner's MCP client receives a connection error, which the agent handles as a tool failure. The worker pod and task-runner continue running.

**Default limit:** 512MB (configurable via Helm values). This accommodates typical headless Chromium usage while protecting the pod.

### Decision 4: `call_model_input_filter` for context management

The task-runner registers a `call_model_input_filter` with the `RunConfig` that runs before every LLM call. The filter scans conversation history for image content (base64 screenshots) and retains only the most recent N screenshots (default: 5), replacing older ones with a text placeholder. This bounds image token usage to ~3,800 tokens regardless of turn count.

**Why not `truncation="auto"`:** Only works with the OpenAI Responses API, not through LiteLLM to Anthropic/other models.

**Why not compaction sessions:** `OpenAIResponsesCompactionSession` is OpenAI-only and produces opaque encrypted items incompatible with other providers.

### Decision 5: Playwright MCP image based on Microsoft's official Playwright image

The `playwright-mcp` Dockerfile uses `mcr.microsoft.com/playwright:v1.50.0-noble` as the base, which includes all browser dependencies pre-installed. `@playwright/mcp` is installed globally via npm. The image is ~1-2GB but exists independently from the task-runner.

### Decision 6: Worker manages Playwright lifecycle in `process_task_in_container`

The existing `process_task_in_container()` function gains a Playwright container lifecycle before and after the task-runner:

1. Create Playwright container with `network_mode="host"` and memory limits
2. Start Playwright container
3. Health-check: poll `http://localhost:8931/mcp` until ready (with timeout)
4. Inject `{"playwright": {"url": "http://localhost:8931/mcp"}}` into the task-runner's MCP config
5. Create and run task-runner (existing flow)
6. After task-runner exits: stop and remove Playwright container
7. On any error: ensure Playwright container is cleaned up in `finally` block

### Decision 7: Environment variables for Playwright configuration

The worker reads Playwright settings from environment variables (set via Helm values):
- `PLAYWRIGHT_MCP_IMAGE`: Image name (default from Helm chart appVersion)
- `PLAYWRIGHT_MEMORY_LIMIT`: Memory limit string (default: `512m`)
- `PLAYWRIGHT_PORT`: Port number (default: `8931`)
- `PLAYWRIGHT_STARTUP_TIMEOUT`: Seconds to wait for health check (default: `30`)

## Risks / Trade-offs

- **Image size** (~1-2GB for Playwright): Each worker pod pulls this image on first task. Mitigated by DinD image caching across tasks within the same pod lifecycle, and `IfNotPresent` pull policy.
- **Startup latency** (~5-10s for Chromium): Every task pays this cost even if the agent doesn't use browser tools. Acceptable for v1; can optimise with conditional startup later.
- **DinD network assumption**: Both containers using `network_mode="host"` on DinD share the pod's network namespace. This is tested and confirmed working for existing MCP connections (backend, Perplexity, Hindsight).
- **Screenshot token cost**: A 1024x768 PNG screenshot costs ~765 tokens. The `call_model_input_filter` caps retained screenshots at 5 (~3,800 tokens). Risk: agent loses visual context from earlier in the run. Mitigation: the agent can retake screenshots as needed.
- **Playwright container OOM** → Agent receives MCP connection error, task may fail or retry. This is the desired behaviour — better than pod-level OOM.

## Open Questions

- None currently — the exploration phase resolved the key architectural questions.
