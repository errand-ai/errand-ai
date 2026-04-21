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
- Capture `X-Client-Id` HTTP header to identify MCP client in `created_by`
- Skip `review` state for tasks created by external clients when the task runner reports `needs_input`

**Non-Goals:**
- Per-task token usage tracking (future enhancement)
- Changes to the REST task creation endpoint
- Configurable list of external client IDs (hard-code awareness for now; generalise later if needed)
- K8s Secret volumes for env var injection (env vars in container spec are sufficient for now)

## Decisions

### 1. Add `profile` param to `new_task` (not a new tool)

Extend the existing `new_task` tool signature with an optional `profile: str | None` parameter. When set, resolve the profile name to an ID and assign it to the task. Task goes directly to `pending` status (immediate execution).

**Rationale:** Simpler than adding a separate tool. The existing `new_task` flow already handles title generation, category classification, and position assignment — just needs profile resolution added.

### 2. Add `title` param to `new_task` to bypass LLM summariser

Extend the existing `new_task` tool signature with an optional `title: str | None` parameter. When set, the title is used verbatim and the description is stored as-is — the LLM summariser is skipped entirely. Category defaults to `"immediate"`.

**Rationale:** The Paperclip adapter already has its own title and description from the upstream request. Calling the LLM summariser would waste tokens, add latency, and risk altering the caller's intent. When `title` is omitted, existing behaviour is preserved (LLM generates title for descriptions >5 words).

### 3. Capture `X-Client-Id` header for `created_by`

MCP tool handlers accept a `ctx: Context` parameter that provides access to the underlying HTTP request. Read the `X-Client-Id` header from the request and use its value as `created_by` on the task, falling back to `"mcp"` when the header is absent.

**Rationale:** Avoids adding yet another tool parameter. HTTP headers are the standard mechanism for client identification. The MCP SDK's `Context.request_context.request` exposes the Starlette `Request` object, so headers are directly accessible. Any MCP client can set `X-Client-Id` without changes to the MCP protocol.

### 4. Skip `review` state for external client tasks

When the task runner finishes a task with `status="needs_input"`, the current logic moves it to `review` so the errand UI can present questions to the user. For tasks where `created_by` is not `"system"`, `"mcp"`, or a known errand user (i.e. it's an external client like `"paperclip"`), skip `review` and move directly to `completed`. The external client is responsible for handling any clarification questions raised during task processing.

**Rationale:** The Paperclip adapter manages its own conversation flow. Putting tasks into `review` would leave them stuck in the errand UI with no one to answer them. The `created_by` field already distinguishes task origin, so no new metadata is needed.

**Implementation:** Add `created_by` to the `DequeuedTask` dataclass so it's available at wrap-up time. In the wrap-up logic, when `parsed.status == "needs_input"` and `task.created_by` is not a known internal source, set `target_status = "completed"` instead of `"review"`.

### 5. Per-task encrypted environment variables

Add an optional `env` parameter to `new_task` and `schedule_task` — typed as `dict | None` so the MCP schema generates `{"type": "object"}`. Values are encrypted with the existing Fernet cipher (`CREDENTIAL_ENCRYPTION_KEY`) and stored in a new `encrypted_env` column on the Task model. At execution time, the TaskManager decrypts and merges these into the container's env vars.

**Rationale:** The Paperclip adapter generates per-run JWT tokens for authenticating callbacks to the Paperclip API. These are sensitive, short-lived values that must be scoped to a single task — not stored in global settings. Using the existing Fernet encryption pattern (from `platforms/credentials.py`) keeps the security model consistent.

**Schema change:** New nullable `encrypted_env` Text column on the `tasks` table. Requires an Alembic migration. The column stores the Fernet-encrypted JSON string. When `CREDENTIAL_ENCRYPTION_KEY` is not set, the tool returns an error rather than storing plaintext.

**Runtime injection:** In `_run_task`, after building the base `env_vars` dict, decrypt `encrypted_env` from the `DequeuedTask` and merge. Per-task env vars override global credentials with the same key name.

**Type lesson learned:** MCP tool parameters must use native Python types that map to the correct JSON schema. Using `str` for structured data generates `{"type": "string"}` which causes the SDK to silently drop object/array arguments from clients. Use `dict` for objects and `list` for arrays.

### 6. Skills management via MCP tools

Add three MCP tools for managing skills:

- **`list_skills`** — returns JSON array of `{ name, description }` for each skill (mirrors the REST `GET /api/skills` but scoped for MCP consumers)
- **`upsert_skill`** — creates or updates a skill by name. Accepts `name`, `description`, `instructions`, and an optional `files` parameter typed as `list | None` (array of `{ path, content }` objects). If a skill with the same name exists, it is updated; otherwise a new one is created. Files are replaced in full on update.
- **`delete_skill`** — deletes a skill by name

**Rationale:** The Paperclip adapter maintains skill definitions as `skills/<name>/SKILL.md` files in its deployment. It needs to sync these into errand's skills system so they can be injected into the task-runner at execution. The existing REST endpoints require admin OIDC auth which MCP clients don't have. Dedicated MCP tools with API key auth are the clean path.

**Upsert semantics:** The adapter calls `upsert_skill` for each skill it manages. Using upsert-by-name avoids the need to track errand skill IDs on the Paperclip side. On update, all existing SkillFiles are deleted and replaced with the provided set — this matches the "sync from source of truth" pattern.

### 7. `list_task_profiles` as a new MCP tool

Returns a JSON array of `{ name, description, model }` for each profile. Omits internal fields (system_prompt, mcp_servers, etc.) that aren't needed by external consumers.

**Rationale:** The REST endpoint `GET /api/task-profiles` requires admin auth and returns too many internal fields. A dedicated MCP tool scoped to external consumer needs is cleaner.

### 8. Structured `task_status` via optional `format` parameter

Add `format: str = "text"` parameter to `task_status`. When `"json"`, return a JSON string with `{ id, title, status, category, created_at, updated_at, has_output }`. Default `"text"` preserves backward compatibility.

**Rationale:** Adding a parameter to the existing tool avoids breaking changes. Existing MCP consumers (the task runner's agent, Hindsight) continue using plaintext.

**Alternative considered:** A separate `task_status_json` tool. Rejected — unnecessary tool proliferation for a format option.

### 9. API key auth for log streaming via query parameter

The SSE endpoint `GET /api/tasks/{id}/logs/stream` already accepts a `token` query parameter (for SSE, since EventSource can't set headers). Add logic to also accept the MCP API key as this token value, in addition to the existing JWT.

**Rationale:** The endpoint already has a query-param auth path for SSE compatibility. Accepting the MCP API key there requires minimal changes — just check the API key if JWT validation fails.

### 10. MCP tool call logging

Patch `_tool_manager.call_tool` on the FastMCP instance to log tool name and key arguments at INFO level. FastMCP registers its handler at init time via `_setup_handlers()`, so replacing `mcp.call_tool` after construction has no effect — the low-level server retains a reference to the original bound method. Patching `_tool_manager.call_tool` intercepts the actual dispatch path.

**Rationale:** The MCP SDK logs only `"Processing request of type CallToolRequest"` with no tool name, and the HTTP access log shows only `POST /mcp/ 200`. Without tool-level logging, diagnosing integration issues requires reading Paperclip logs instead of errand's own logs.

## Risks / Trade-offs

- **MCP API key on log streaming** — Expands the API key's scope from MCP-only to include one REST endpoint. Mitigation: the API key already grants full task management via MCP; log streaming is read-only and lower privilege.
- **`task_status` signature change** — Adding a parameter is backwards-compatible but makes the tool slightly more complex. Mitigation: default is `"text"`, existing callers unaffected.
- **MCP parameter types** — Using `str` for structured parameters (dicts, lists) causes the SDK to generate the wrong JSON schema (`{"type": "string"}`) and silently drop arguments. Always use `dict` for objects and `list` for arrays.

## Open Questions

- None — all decisions validated during integration testing with the Paperclip adapter.
