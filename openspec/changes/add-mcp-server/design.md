## Context

The content manager backend is a FastAPI (Starlette-based) application. External AI coding tools (Claude Code, GitHub Copilot, Cursor) support MCP servers for tool integration. We want to expose task operations via an MCP endpoint so developers can create and monitor tasks from their IDE.

The backend already has:
- OIDC/JWT authentication for browser-based users (`auth.py`)
- A `settings` table (key/value JSONB) for configuration storage
- Task CRUD endpoints (`POST /api/tasks`, `GET /api/tasks/{id}`)
- A settings page at `/settings` with existing sections

## Goals / Non-Goals

**Goals:**
- Expose an MCP Streamable HTTP endpoint at `/mcp` on the existing backend
- API key authentication (simpler than OIDC for CLI/IDE tool integration)
- Auto-generate API key on startup, store in settings table
- Settings page shows API key and example config for claude-code / copilot
- Three tools: `new_task`, `task_status`, `task_output`

**Non-Goals:**
- OAuth/OIDC for MCP clients (too complex for IDE tool configs)
- Multiple API keys or per-user keys (single shared key is sufficient)
- MCP resources or prompts (tools only)
- Rate limiting on the MCP endpoint

## Decisions

### 1. Use MCP Python SDK with Starlette mount

**Decision:** Use the official `mcp` Python SDK's `MCPServer` class and mount `streamable_http_app()` onto the existing FastAPI app via `app.mount("/mcp", ...)`.

**Rationale:** FastAPI is built on Starlette, so the SDK's Starlette integration works directly. This avoids running a separate process. The `streamable_http_path="/"` option means the endpoint is at `/mcp` (not `/mcp/mcp`).

**Alternative considered:** Running a separate MCP server process — rejected because it adds deployment complexity and requires another port/service.

### 2. API key auth via TokenVerifier

**Decision:** Implement a custom `TokenVerifier` that validates the Bearer token in the Authorization header against the stored API key. The MCP SDK's `token_verifier` parameter on `MCPServer` handles extracting the Bearer token and calling our verifier.

**Rationale:** The SDK has built-in support for token verification. Our verifier simply compares the token against the stored API key using `secrets.compare_digest` for timing-safe comparison.

**Alternative considered:** Custom ASGI middleware — rejected because the SDK already provides the auth hook, and using it is simpler and more maintainable.

### 3. API key stored in settings table

**Decision:** Store the API key as a setting with key `mcp_api_key` in the existing `settings` table. Generate a 32-byte hex token via `secrets.token_hex(32)` on startup if the key doesn't exist.

**Rationale:** Reuses existing infrastructure (no migration needed). The settings table is already used for configuration. A 64-character hex string provides 256 bits of entropy.

**Alternative considered:** Separate `api_keys` table — rejected as over-engineering for a single shared key.

### 4. Startup hook generates API key

**Decision:** Add API key generation to the existing `lifespan` context manager in `main.py`. On startup, check if `mcp_api_key` exists in settings; if not, generate and insert it.

**Rationale:** Guarantees the key exists before any request is served. The lifespan hook already exists for other initialization.

### 5. MCP server in dedicated module

**Decision:** Create `backend/mcp_server.py` containing the `MCPServer` instance, tools, and token verifier. Export a function to create the ASGI app that `main.py` mounts.

**Rationale:** Keeps MCP-specific logic separate from the main API. The module can import database utilities and models as needed.

### 6. Settings page displays API key with copy functionality

**Decision:** Add an "MCP Server" section to the settings page showing: the API key (masked by default with a reveal toggle), a "Copy" button, a pre-formatted example JSON config block for claude-code/copilot, and a "Regenerate API Key" button.

**Rationale:** Users need to copy the key and config into their tools. Masking by default prevents shoulder-surfing.

### 7. Regenerate endpoint as POST /api/settings/regenerate-mcp-key

**Decision:** Add a dedicated admin-only endpoint for regenerating the API key. Returns the new key in the response.

**Rationale:** A dedicated endpoint is clearer than overloading `PUT /api/settings`. It communicates intent and can be easily audited.

## Risks / Trade-offs

- **Single API key for all users** → If compromised, all MCP access is affected. Mitigation: regenerate button in settings. Future enhancement could add per-user keys.
- **No revocation list** → Old keys are immediately invalid after regeneration. Mitigation: this is acceptable since there's only one key.
- **MCP endpoint on same port as API** → Shares resources with the main API. Mitigation: MCP tools are lightweight (database queries only), so resource contention is minimal.
