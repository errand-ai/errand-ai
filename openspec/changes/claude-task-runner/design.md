## Context

Errand's task-runner executes tasks in containers using an OpenAI-compatible agent loop that calls LLM APIs (billed per token). Individual users running errand-desktop on macOS often already have Claude Max subscriptions. The Claude Code CLI supports headless execution (`claude -p`) with OAuth token authentication, enabling subscription-based usage without API billing.

The current task-runner architecture streams structured JSON events from stderr (tool_call, tool_result, thinking, agent_end) through the container runtime to Valkey pub/sub and then to the frontend via WebSocket. Any claude integration must preserve this streaming pipeline.

Anthropic shut down third-party OAuth token extraction (OpenClaw incident, January 2026) — but that involved replacing the claude client entirely. Running the actual `claude` CLI binary in containers is analogous to the official Claude Code GitHub Action, which uses the same `CLAUDE_CODE_OAUTH_TOKEN` mechanism.

## Goals / Non-Goals

**Goals:**
- Allow errand-desktop users to run tasks using their Claude Max subscription via `claude -p`
- Preserve existing live streaming UX (tool calls, progress, results visible in real-time)
- Graceful fallback to API-billed agent loop when claude is unavailable or fails
- Support all user-configured MCP servers when delegating to claude
- Restrict this feature to local/desktop deployments only

**Non-Goals:**
- Supporting this on K8s/Helm production deployments
- Implementing OAuth token refresh (rely on `claude setup-token` 1-year tokens)
- Replacing the existing API-billed agent loop (this is an alternative, not a replacement)
- Building a custom Anthropic API client (we use the official claude CLI only)
- Keychain extraction from errand-desktop (user runs `claude setup-token` manually)

## Decisions

### 1. Authentication via `claude setup-token` (not Keychain extraction)

**Decision**: Users generate a long-lived token via `claude setup-token` and paste it into errand Settings.

**Alternatives considered**:
- *Keychain extraction via errand-desktop*: Would require macOS Security framework access, creates tight coupling to desktop app, fragile if Claude changes keychain entry format
- *Custom OAuth refresh flow*: Reverse-engineering Anthropic's OAuth endpoints risks account bans and ToS violations
- *Direct API key*: Would use API billing, defeating the purpose

**Rationale**: `claude setup-token` generates a 1-year token specifically designed for headless/automated use. It's the same mechanism the official GitHub Action uses. No refresh needed, no Keychain dependency, works on any deployment that has the claude CLI.

### 2. Hybrid execution with try/fallback pattern

**Decision**: The claude-task-runner's `main.py` attempts `claude -p` first. On failure (auth error, rate limit, crash), it falls back to the existing Python agent loop.

**Alternatives considered**:
- *Claude-only execution*: No fallback — simpler but fragile; auth failures = task failure
- *Outer agent delegates via execute_command*: The outer agent (cheap model) decides when to call claude. But this requires an LLM to make the delegation decision, adding latency and API cost for the routing decision alone
- *Separate entrypoint*: Different Dockerfile CMD for claude mode — but prevents fallback

**Rationale**: The try/fallback pattern gives the best of both worlds. Users who configure claude get it when it works, and transparent fallback when it doesn't. No routing agent needed — the image choice IS the routing decision.

### 3. Separate container image (not runtime install)

**Decision**: A `claude-task-runner` Dockerfile extending the base `task-runner` image, adding Node.js and `@anthropic-ai/claude-code`.

**Alternatives considered**:
- *Runtime npm install*: Agent installs claude CLI on first run — adds ~20s startup latency per task
- *Single image with claude baked in*: Everyone pays the ~90MB size increase even if they don't use claude
- *Volume mount from host*: Mount the host's claude installation — fragile, platform-dependent

**Rationale**: Separate images let users opt-in without penalising others. The image size increase (~90MB for Node.js + claude) is acceptable for desktop use. CI builds both images in parallel.

### 4. Stream transformation (claude stream-json → errand events)

**Decision**: Read claude's stdout (`--output-format stream-json`), transform events to errand's existing format, emit to container stderr.

**Architecture**:
```
claude -p --output-format stream-json (stdout)
  → main.py reads line by line
  → transforms to errand event format
  → emits to stderr (container stderr)
  → TaskManager async_run() picks up
  → publishes to Valkey
  → frontend WebSocket renders
```

**Event mapping**:
| Claude stream-json event | Errand event type |
|---|---|
| `content_block_start` (type: tool_use) | `tool_call` |
| `content_block_stop` (after tool use) | `tool_result` |
| `text_delta` | `thinking` |
| `result` | `agent_end` |
| `system/api_retry` | `raw` |

**Rationale**: The frontend already renders tool_call, tool_result, thinking, and agent_end events. By transforming at the task-runner level, no frontend changes are needed.

### 5. Task Profile `container_image` field

**Decision**: Add a nullable `container_image` text column to `TaskProfile`. Values: `null` (default image), `"claude"` (resolved to claude-task-runner image), or an arbitrary image string (custom).

**Rationale**: Clean extension of existing profile system. The TaskManager resolves the image at container preparation time, with a simple lookup: null → `TASK_RUNNER_IMAGE` env var, "claude" → `CLAUDE_TASK_RUNNER_IMAGE` env var, other → use as-is.

### 6. Claude MCP config generation

**Decision**: TaskManager generates `~/.claude/settings.json` inside the container with the user's configured MCP servers translated to Claude Code format. This file is injected alongside the existing `/workspace/mcp.json`.

**Rationale**: Claude Code reads MCP server config from `~/.claude/settings.json`. Both errand and Claude Code support HTTP Streamable transport, so the translation is straightforward. This gives claude access to Playwright, Hindsight, and any other MCP servers the user has configured.

### 7. K8s deployment lockout

**Decision**: When `CONTAINER_RUNTIME=kubernetes`, reject `"claude"` as a container_image value at the TaskProfile validation level and hide the option in the frontend.

**Rationale**: Running claude CLI with a user's personal subscription on shared K8s infrastructure crosses a clear ToS line. The technical mechanism (validation error on save) is simple and explicit. The frontend hides the option entirely so users aren't confused by an option they can't use.

## Risks / Trade-offs

- **[ToS enforcement]** Anthropic could tighten restrictions on `CLAUDE_CODE_OAUTH_TOKEN` in containers → Mitigation: Feature is clearly opt-in with user-facing disclaimers. We use the official CLI binary, same as GitHub Actions. If Anthropic blocks it, fallback to API agent loop is automatic.
- **[Token expiry]** `setup-token` tokens expire after 1 year → Mitigation: Store `expiresAt` with the credential, show expiry warning in Settings UI when approaching.
- **[Rate limiting]** Multiple concurrent tasks can exhaust Max subscription quota → Mitigation: This is the user's responsibility (same as manually running multiple `claude -p` sessions). Document in the disclaimer.
- **[Image size]** claude-task-runner is ~90MB larger than base image → Mitigation: Acceptable for desktop use. Separate image means non-claude users aren't affected.
- **[Claude CLI updates]** Breaking changes in claude CLI stream-json format → Mitigation: Pin claude CLI version in Dockerfile. Stream transformer has fallback for unrecognised events (emit as `raw` type).
- **[Streaming fidelity]** Some claude events may not map cleanly to errand event types → Mitigation: Unknown events emitted as `raw` type, preserving data even if frontend rendering is basic.
