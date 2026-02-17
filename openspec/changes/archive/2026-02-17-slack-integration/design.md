## Context

The platform-foundation change establishes the platform abstraction, encrypted credential storage, credential management UI, and task audit metadata. This change builds on that foundation to add Slack as the first interaction surface — a bidirectional interface where users manage tasks directly from Slack.

Slack integration requires inbound webhook handling (Slack POSTs to our backend), slash command parsing, Block Kit response formatting, request signature verification, and user identity resolution.

The system already has: FastAPI backend (main.py), Keycloak OIDC auth, platform abstraction with registry and credential management, task API with audit fields, Helm chart with ingress routing for /api, /auth, /mcp, /.

## Goals / Non-Goals

**Goals:**
- Accept and process Slack slash commands for task operations
- Return rich Block Kit formatted responses
- Verify all inbound Slack requests via HMAC-SHA256 signature
- Resolve Slack users to email addresses for audit trail
- Route Slack webhook traffic through the existing ingress

**Non-Goals:**
- Interactive messages (buttons, modals, dropdowns) — follow-on change
- Slack event subscriptions beyond URL verification — future
- Slack notification push (proactive messages to Slack) — future
- Socket Mode (we use HTTP webhooks via public URL)
- Multiple Slack workspace support (one workspace for now)

## Decisions

### 1. Slash commands over bot mentions

**Decision:** Use Slack slash commands (`/task new`, `/task status`, etc.) as the primary interaction model, not @bot mentions.

**Rationale:** Slash commands provide: structured input parsing, built-in help/autocomplete in Slack, private responses (only the invoker sees the response by default), and don't require the bot to be in every channel. Bot mentions require natural language parsing and add complexity.

**Alternative considered:** App mentions + NLP parsing — rejected for Phase 1. Could be added later for a more conversational experience.

### 2. Single `/task` command with subcommands

**Decision:** Register one Slack slash command `/task` that dispatches on the first argument: `new`, `status`, `list`, `run`, `output`.

**Rationale:** Slack limits the number of slash commands per app. A single command with subcommands is standard practice (like `/github issue`, `/github pr`). Parsing is simple: split on first space, dispatch on first token.

**Command syntax:**
- `/task new <title>` — create a task
- `/task status <id>` — get task status (accepts UUID or short prefix)
- `/task list [status]` — list tasks, optionally filtered by status
- `/task run <id>` — queue a task for execution
- `/task output <id>` — get task output

### 3. FastAPI router mounted at /slack, not a separate app

**Decision:** Add a FastAPI `APIRouter` for Slack routes, mounted on the main app at `/slack`.

**Rationale:** Keeps everything in one process. Slack webhooks need database access (to create/query tasks) and the request volumes are low (human-initiated commands, not high-throughput). A separate service would add operational complexity for no benefit.

### 4. Signature verification as a FastAPI dependency

**Decision:** Implement Slack request signature verification as a FastAPI `Depends()` that runs before every Slack route handler. The dependency reads the raw request body, `X-Slack-Signature`, and `X-Slack-Request-Timestamp` headers.

**Rationale:** Central enforcement — impossible to forget verification on a new route. FastAPI dependencies are the standard pattern for cross-cutting concerns. The dependency raises `HTTPException(403)` on verification failure.

**Security properties:**
- Timestamp check: reject requests > 5 minutes old (prevents replay attacks)
- HMAC-SHA256: `v0=hmac(signing_secret, "v0:{timestamp}:{body}")` compared timing-safe with `hmac.compare_digest`
- Raw body required: must read body before FastAPI parses it (use `Request.body()`)

### 5. Slack user email cached in-memory with TTL

**Decision:** Cache Slack user_id → email mappings in an in-memory dict with 1-hour TTL. Cache miss triggers `users.info` Slack API call.

**Rationale:** Slash commands arrive at human pace (< 1/sec). Caching avoids redundant API calls for repeated commands from the same user. In-memory is fine because: single process, low cardinality (team members, not millions of users), and cache loss on restart is acceptable (just triggers fresh API calls).

**Alternative considered:** Redis cache — overkill for this use case. DB cache table — unnecessary persistence for ephemeral data.

### 6. Block Kit for response formatting

**Decision:** Build responses using Slack's Block Kit JSON format with section blocks, markdown text, and dividers.

**Rationale:** Block Kit is Slack's recommended approach for rich messages. It supports markdown formatting, structured layouts, and (in future) interactive elements. Text-only responses are functional but lack structure for multi-field displays like task details.

**Message patterns:**
- Task created: header + fields (title, status, category) + context (created by, timestamp)
- Task status: header + fields (title, status, category, dates) + context
- Task list: header + list of tasks with status emoji + counts
- Task output: header + code block with output text (truncated if long)
- Error: warning emoji + error text

### 7. Short ID prefix matching for task references

**Decision:** Allow users to reference tasks by UUID prefix (first 6-8 characters) in slash commands, not just full UUID.

**Rationale:** Full UUIDs are 36 characters — impractical to type in Slack. Prefix matching (e.g., `/task status a1b2c3`) is natural and unlikely to collide with typical task volumes (< 10k tasks). If ambiguous, return an error listing matches.

## Risks / Trade-offs

- **[Slack API rate limits]** → `users.info` is rate-limited. Mitigation: 1-hour cache means at most 1 call per user per hour. Team-sized workspaces won't hit limits.
- **[Public webhook endpoint]** → `/slack/commands` is internet-facing. Mitigation: HMAC signature verification rejects all non-Slack traffic. Timestamp check prevents replay attacks.
- **[Slash command 3-second timeout]** → Slack requires a response within 3 seconds or shows an error. Mitigation: for operations that may take longer (task run), respond immediately with "queued" and optionally use `response_url` for async follow-up.
- **[Block Kit output truncation]** → Slack messages have a ~3000 character limit per text block. Task output can be much longer. Mitigation: truncate with "... (truncated, use web UI for full output)" message and include a link.
- **[Ingress path conflict]** → `/slack` must not conflict with frontend catch-all route. Mitigation: ingress paths are matched in order; `/slack` before `/` ensures correct routing.

## Migration Plan

1. Add `slack-sdk` to `backend/requirements.txt`
2. Create `backend/platforms/slack/` package
3. Mount Slack router on main FastAPI app
4. Update Helm ingress template with `/slack` path
5. Deploy backend — Slack endpoints available but non-functional until credentials configured
6. Create Slack app in Slack API dashboard:
   - Enable slash commands: `/task` pointing to `https://<domain>/slack/commands`
   - OAuth scopes: `commands`, `chat:write`, `users:read.email`
   - Copy Bot Token and Signing Secret
7. Admin configures Slack credentials via platform settings UI
8. Verify: issue `/task list` in Slack workspace
