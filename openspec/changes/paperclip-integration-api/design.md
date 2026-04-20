## Context

The Paperclip errand adapter communicates with errand via MCP tools and one REST SSE endpoint. Three MCP gaps and one REST auth gap need addressing:

1. `new_task` doesn't accept a `profile` parameter — tasks created via MCP can't use a specific profile without going through `schedule_task` (which adds 15s scheduler delay)
2. No MCP tool to list available task profiles — the adapter's `listModels()` needs this to populate the profile dropdown
3. `task_status` returns plaintext — the adapter needs structured data to reliably detect task state
4. Log streaming SSE endpoint requires OIDC JWT — MCP consumers only have an API key

## Goals / Non-Goals

**Goals:**
- Add `profile` parameter to `new_task` MCP tool
- Add `list_task_profiles` MCP tool
- Add structured JSON output option to `task_status` MCP tool
- Add API key authentication to the log streaming SSE endpoint

**Non-Goals:**
- Per-task token usage tracking (future enhancement)
- Changes to the REST task creation endpoint
- Changes to the task runner or container runtime

## Decisions

### 1. Add `profile` param to `new_task` (not a new tool)

Extend the existing `new_task` tool signature with an optional `profile: str | None` parameter. When set, resolve the profile name to an ID and assign it to the task. Task goes directly to `pending` status (immediate execution).

**Rationale:** Simpler than adding a separate tool. The existing `new_task` flow already handles title generation, category classification, and position assignment — just needs profile resolution added.

### 2. `list_task_profiles` as a new MCP tool

Returns a JSON array of `{ name, description, model }` for each profile. Omits internal fields (system_prompt, mcp_servers, etc.) that aren't needed by external consumers.

**Rationale:** The REST endpoint `GET /api/task-profiles` requires admin auth and returns too many internal fields. A dedicated MCP tool scoped to external consumer needs is cleaner.

### 3. Structured `task_status` via optional `format` parameter

Add `format: str = "text"` parameter to `task_status`. When `"json"`, return a JSON string with `{ id, title, status, category, created_at, updated_at, has_output }`. Default `"text"` preserves backward compatibility.

**Rationale:** Adding a parameter to the existing tool avoids breaking changes. Existing MCP consumers (the task runner's agent, Hindsight) continue using plaintext.

**Alternative considered:** A separate `task_status_json` tool. Rejected — unnecessary tool proliferation for a format option.

### 4. API key auth for log streaming via query parameter

The SSE endpoint `GET /api/tasks/{id}/logs/stream` already accepts a `token` query parameter (for SSE, since EventSource can't set headers). Add logic to also accept the MCP API key as this token value, in addition to the existing JWT.

**Rationale:** The endpoint already has a query-param auth path for SSE compatibility. Accepting the MCP API key there requires minimal changes — just check the API key if JWT validation fails.

## Risks / Trade-offs

- **MCP API key on log streaming** — Expands the API key's scope from MCP-only to include one REST endpoint. Mitigation: the API key already grants full task management via MCP; log streaming is read-only and lower privilege.
- **`task_status` signature change** — Adding a parameter is backwards-compatible but makes the tool slightly more complex. Mitigation: default is `"text"`, existing callers unaffected.

## Open Questions

- None — all decisions are straightforward extensions of existing patterns.
