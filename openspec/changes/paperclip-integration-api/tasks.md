## 1. MCP Profile Tools

- [x] 1.1 Add `profile: str | None = None` parameter to `new_task` MCP tool
- [x] 1.2 When `profile` is set in `new_task`, resolve profile name to ID via DB lookup; return error if not found
- [x] 1.3 When `profile` is set, assign `profile_id` to the created task (skip LLM-based profile auto-assignment)
- [x] 1.4 Implement `list_task_profiles` MCP tool — query `TaskProfile` table, return JSON array of `{ name, description, model }` per profile
- [x] 1.5 Add `title: str | None = None` parameter to `new_task` MCP tool
- [x] 1.6 When `title` is set, use it as the task title and store `description` verbatim — skip LLM summariser entirely
- [x] 1.7 When `title` is not set, preserve existing behaviour (LLM summariser for >5 words, description-as-title for <=5 words)

## 2. Structured Task Status

- [x] 2.1 Add `format: str = "text"` parameter to `task_status` MCP tool
- [x] 2.2 When `format="json"`, return a JSON string with `id`, `title`, `status`, `category`, `created_at`, `updated_at`, `has_output` fields
- [x] 2.3 When `format="text"` (or omitted), return existing plaintext format unchanged

## 3. API Key Auth for Log Streaming

- [x] 3.1 In the `GET /api/tasks/{id}/logs/stream` endpoint, add fallback auth: if JWT validation fails, check if the `token` query parameter matches the `mcp_api_key` database setting
- [x] 3.2 Use `secrets.compare_digest` for timing-safe API key comparison (matching the MCP server's `ApiKeyVerifier` pattern)

## 4. Tests

- [x] 4.1 Test `new_task` with valid `profile` creates task with correct `profile_id`
- [x] 4.2 Test `new_task` with invalid `profile` returns error message
- [x] 4.3 Test `new_task` without `profile` behaves as before (backward compatible)
- [x] 4.11 Test `new_task` with explicit `title` sets title and description verbatim (no LLM call)
- [x] 4.12 Test `new_task` with `title` and `profile` sets both correctly
- [x] 4.13 Test `new_task` without `title` still calls LLM summariser (backward compatible)
- [x] 4.4 Test `list_task_profiles` returns correct JSON structure
- [x] 4.5 Test `list_task_profiles` returns empty array when no profiles exist
- [x] 4.6 Test `task_status` with `format="json"` returns valid JSON with expected fields
- [x] 4.7 Test `task_status` with `format="text"` returns plaintext (backward compatible)
- [x] 4.8 Test log streaming endpoint accepts MCP API key as token
- [x] 4.9 Test log streaming endpoint still accepts JWT as token
- [x] 4.10 Test log streaming endpoint rejects invalid token with 401
