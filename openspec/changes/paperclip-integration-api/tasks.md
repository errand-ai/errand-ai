## 1. MCP Profile Tools

- [x] 1.1 Add `profile: str | None = None` parameter to `new_task` MCP tool
- [x] 1.2 When `profile` is set in `new_task`, resolve profile name to ID via DB lookup; return error if not found
- [x] 1.3 When `profile` is set, assign `profile_id` to the created task (skip LLM-based profile auto-assignment)
- [x] 1.4 Implement `list_task_profiles` MCP tool — query `TaskProfile` table, return JSON array of `{ name, description, model }` per profile
- [x] 1.5 Add `title: str | None = None` parameter to `new_task` MCP tool
- [x] 1.6 When `title` is set, use it as the task title and store `description` verbatim — skip LLM summariser entirely
- [x] 1.7 When `title` is not set, preserve existing behaviour (LLM summariser for >5 words, description-as-title for <=5 words)

## 2. Client Identification via HTTP Header

- [x] 2.1 Add `ctx: Context` parameter to `new_task` MCP tool handler
- [x] 2.2 Read `X-Client-Id` header from `ctx.request_context.request.headers`; use as `created_by` (fall back to `"mcp"`)
- [x] 2.3 Add `ctx: Context` parameter to `schedule_task` MCP tool handler and apply the same `X-Client-Id` → `created_by` logic

## 3. Skip Review State for External Client Tasks

- [x] 3.1 Add `created_by: str | None` field to `DequeuedTask` dataclass; populate it in `from_orm`
- [x] 3.2 In task wrap-up, when `parsed.status == "needs_input"` and `created_by` is an external client, set `target_status = "completed"` instead of `"review"`

## 4. Per-Task Encrypted Environment Variables

- [x] 4.1 Add nullable `encrypted_env` Text column to Task model (`errand/models.py`)
- [x] 4.2 Create Alembic migration for the new column
- [x] 4.3 Add `env: str | None = None` parameter to `new_task` — accepts JSON object of key/value pairs
- [x] 4.4 Encrypt `env` values with Fernet cipher and store in `encrypted_env`; return error if `CREDENTIAL_ENCRYPTION_KEY` is not set
- [x] 4.5 Add `env` parameter to `schedule_task` with the same encryption logic
- [x] 4.6 Add `encrypted_env` field to `DequeuedTask` dataclass; populate from ORM
- [x] 4.7 In `_run_task`, decrypt `encrypted_env` and merge into container env vars (per-task overrides global)

## 5. Skills Management via MCP Tools

- [x] 5.1 Implement `list_skills` MCP tool — return JSON array of `{ name, description }` per skill
- [x] 5.2 Implement `upsert_skill` MCP tool — create or update skill by name; accept `name`, `description`, `instructions`, optional `files` array of `{ path, content }`
- [x] 5.3 On upsert update: delete existing SkillFiles and replace with provided set
- [x] 5.4 Validate skill name against existing pattern (lowercase, no leading/trailing hyphens, max 64 chars)
- [x] 5.5 Implement `delete_skill` MCP tool — delete skill by name; return error if not found
- [x] 5.6 Relax MCP skill name validation to allow consecutive hyphens (external clients append hash suffixes with `--`)

## 6. Structured Task Status

- [x] 6.1 Add `format: str = "text"` parameter to `task_status` MCP tool
- [x] 6.2 When `format="json"`, return a JSON string with `id`, `title`, `status`, `category`, `created_at`, `updated_at`, `has_output` fields
- [x] 6.3 When `format="text"` (or omitted), return existing plaintext format unchanged

## 7. API Key Auth for Log Streaming

- [x] 7.1 In the `GET /api/tasks/{id}/logs/stream` endpoint, add fallback auth: if JWT validation fails, check if the `token` query parameter matches the `mcp_api_key` database setting
- [x] 7.2 Use `secrets.compare_digest` for timing-safe API key comparison (matching the MCP server's `ApiKeyVerifier` pattern)

## 8. Tests

- [x] 8.1 Test `new_task` with valid `profile` creates task with correct `profile_id`
- [x] 8.2 Test `new_task` with invalid `profile` returns error message
- [x] 8.3 Test `new_task` without `profile` behaves as before (backward compatible)
- [x] 8.4 Test `new_task` with explicit `title` sets title and description verbatim (no LLM call)
- [x] 8.5 Test `new_task` with `title` and `profile` sets both correctly
- [x] 8.6 Test `new_task` without `title` still calls LLM summariser (backward compatible)
- [x] 8.7 Test `list_task_profiles` returns correct JSON structure
- [x] 8.8 Test `list_task_profiles` returns empty array when no profiles exist
- [x] 8.9 Test `task_status` with `format="json"` returns valid JSON with expected fields
- [x] 8.10 Test `task_status` with `format="text"` returns plaintext (backward compatible)
- [x] 8.11 Test log streaming endpoint accepts MCP API key as token
- [x] 8.12 Test log streaming endpoint still accepts JWT as token
- [x] 8.13 Test log streaming endpoint rejects invalid token with 401
- [x] 8.14 Test `new_task` with `X-Client-Id` header sets `created_by` to header value
- [x] 8.15 Test `new_task` without `X-Client-Id` header sets `created_by` to `"mcp"`
- [x] 8.16 Test `schedule_task` with `X-Client-Id` header sets `created_by` to header value
- [x] 8.17 Test task wrap-up: external client task with `needs_input` moves to `completed` (not `review`)
- [x] 8.18 Test task wrap-up: internal task with `needs_input` moves to `review` (backward compatible)
- [x] 8.19 Test `new_task` with `env` parameter stores encrypted env vars
- [x] 8.20 Test `new_task` without `env` parameter leaves `encrypted_env` null
- [x] 8.21 Test `new_task` with `env` but no encryption key returns error
- [x] 8.22 Test `schedule_task` with `env` parameter stores encrypted env vars
- [x] 8.23 Test task runner decrypts and injects per-task env vars into container
- [x] 8.24 Test `list_skills` returns correct JSON structure
- [x] 8.25 Test `list_skills` returns empty array when no skills exist
- [x] 8.26 Test `upsert_skill` creates new skill with files
- [x] 8.27 Test `upsert_skill` updates existing skill, replacing files
- [x] 8.28 Test `upsert_skill` with invalid name returns error
- [x] 8.29 Test `delete_skill` removes skill and files
- [x] 8.30 Test `delete_skill` with non-existent name returns error
- [x] 8.31 Test `upsert_skill` accepts name with consecutive hyphens (e.g. `code-review--abc123`)
