## 1. Dependencies & Backend Setup

- [x] 1.1 Add `mcp` Python SDK to `backend/requirements.txt`
- [x] 1.2 Add API key auto-generation to the lifespan context manager in `main.py` — on startup, check if `mcp_api_key` exists in settings, if not generate via `secrets.token_hex(32)` and insert it

## 2. MCP Server Module

- [x] 2.1 Create `backend/mcp_server.py` with `MCPServer` instance, custom `TokenVerifier` (validates Bearer token against stored `mcp_api_key` using `secrets.compare_digest`), and `create_mcp_app()` function returning `streamable_http_app()`
- [x] 2.2 Implement `new_task` tool — accepts `description` string, creates task using existing logic (insert row, generate title via LLM with fallback), publishes `task_created` WebSocket event, returns task UUID
- [x] 2.3 Implement `task_status` tool — accepts `task_id` UUID string, returns task title/status/category/timestamps, or error if not found
- [x] 2.4 Implement `task_output` tool — accepts `task_id` UUID string, returns output if task is `completed`/`review`, in-progress message otherwise, or error if not found
- [x] 2.5 Mount MCP app in `main.py` via `app.mount("/mcp", create_mcp_app())` and integrate session manager start/stop into the lifespan context manager

## 3. Admin Settings API

- [x] 3.1 Add `POST /api/settings/regenerate-mcp-key` endpoint requiring admin role — generates new key via `secrets.token_hex(32)`, stores in settings table, returns `{"mcp_api_key": "<new-key>"}`
- [x] 3.2 Ensure `GET /api/settings` includes `mcp_api_key` in the response when it exists

## 4. Frontend Settings UI

- [x] 4.1 Add "MCP API Key" section to the Settings page — displays masked key with Reveal/Hide toggle, Copy button with "Copied!" feedback
- [x] 4.2 Add Regenerate button with confirmation dialog, calls `POST /api/settings/regenerate-mcp-key`, updates displayed key on success
- [x] 4.3 Add example MCP configuration block using current page origin and API key, with Copy button
- [x] 4.4 Update settings page layout to include the new "MCP API Key" section after "MCP Server Configuration"

## 5. Tests

- [x] 5.1 Add backend tests for API key auto-generation on startup (key created when missing, preserved when exists)
- [x] 5.2 Add backend tests for `POST /api/settings/regenerate-mcp-key` (admin succeeds, non-admin rejected, new key returned)
- [x] 5.3 Add backend tests for MCP endpoint — tool discovery (`tools/list` returns 3 tools), auth rejection (missing/invalid token), valid auth accepted
- [x] 5.4 Add backend tests for MCP tools — `new_task` creates task and returns UUID, `task_status` returns info or not-found, `task_output` returns output for completed/review or in-progress message
- [x] 5.5 Add frontend tests for MCP API Key section — masked display, reveal/hide toggle, copy button, regenerate flow, example config rendering

## 6. Docker & Integration

- [x] 6.1 Rebuild with `docker compose up --build` and verify `/mcp` endpoint responds, API key is generated, settings page shows key and config
