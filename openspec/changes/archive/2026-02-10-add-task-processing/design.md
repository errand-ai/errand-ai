## Context

The content-manager has a basic task model (title + status) with 7 kanban columns including "Need Input". Tasks are created via a simple title input, displayed on cards with title + status text, and edited via a modal with title + status fields. There is no description field, no tagging, and no LLM integration. The admin settings page (added in v0.6.0) currently has system prompt and MCP server config sections — it uses a key-value `settings` table with JSONB values.

The backend uses FastAPI + SQLAlchemy (async) with PostgreSQL, Alembic migrations, and Valkey pub/sub for WebSocket events. The frontend is Vue 3 + Pinia + Tailwind CSS with Vue Router. LiteLLM is available as an OpenAI-compatible proxy — we will use the OpenAI Python SDK pointed at LiteLLM's base URL.

## Goals / Non-Goals

**Goals:**
- Add a `description` field to tasks and a tagging system to replace the "Need Input" column
- Auto-generate task titles from longer descriptions using an LLM call
- Display tags on kanban cards and provide tag autocomplete in the edit modal
- Add LLM model selection to the admin settings page
- Clean up card display by removing redundant status text

**Non-Goals:**
- Full-text search on descriptions or tags
- Tag colors, categories, or hierarchies
- Bulk tag operations or tag management UI (beyond autocomplete in the edit modal)
- LLM features beyond title generation (e.g., task categorization, priority suggestion)
- Streaming LLM responses — title generation is a short, synchronous call

## Decisions

### 1. Tag data model: separate `tags` table with `task_tags` join table

**Decision**: Create a `tags` table with `id` (UUID PK) and `name` (unique text) columns, and a `task_tags` join table with `task_id` + `tag_id` foreign keys (composite PK). Tags are normalized — a tag name exists once and is reused across tasks.

**Rationale**: A normalized model enables autocomplete by querying the `tags` table directly, prevents name inconsistencies, and supports future features like tag counts or filtering. The alternative (storing tags as a JSONB array on the task) would be simpler but makes autocomplete harder and doesn't enforce uniqueness.

### 2. Task input behavior: threshold-based title vs description

**Decision**: When a new task is submitted, count the words in the input. If the input has **5 or fewer words**, treat it as the title directly and auto-apply the "Needs Info" tag. If it has **more than 5 words**, store it as the description and call the LLM to generate a short title (2-5 words).

**Rationale**: 5 words is a natural boundary — "Fix the login bug" is a title, while "The login page throws a 500 error when users with special characters in their email try to reset their password" is a description that needs summarizing. The threshold is simple to implement and understand.

**Impact**: The `POST /api/tasks` endpoint changes from accepting `{title}` to accepting `{input}` — the backend determines whether it becomes a title or description based on word count.

### 3. LLM client: OpenAI Python SDK with LiteLLM as base URL

**Decision**: Use the `openai` Python SDK (async client) with `base_url` set to the `LITELLM_BASE_URL` environment variable and `api_key` set to `LITELLM_API_KEY`. The model is read from the `llm_model` setting (default: `claude-haiku-4-5-20251001`).

**Rationale**: The OpenAI SDK is the de facto standard for LLM API calls. LiteLLM provides an OpenAI-compatible API, so pointing the SDK at LiteLLM works out of the box. This gives future flexibility to swap LiteLLM for any OpenAI-compatible provider (e.g., direct OpenAI, vLLM, Ollama) without changing application code — only the environment variables need updating.

**Trade-off**: We depend on LiteLLM maintaining OpenAI API compatibility, which is its core purpose.

### 4. LLM call is synchronous in the request path

**Decision**: The LLM title generation call happens inline during `POST /api/tasks`, before the response is returned. If the LLM call fails, the task is still created but with a fallback title (first 5 words of the description + "...") and a "Needs Info" tag.

**Rationale**: Title generation via a small model (Haiku) is fast (< 1 second typically). Making it async would add complexity (task created without title, then updated later via worker) for minimal latency gain. The fallback ensures task creation never fails due to LLM issues.

**Trade-off**: If LiteLLM is slow or down, task creation latency increases. The fallback mitigates this — the user gets a task immediately and can edit the title later.

### 5. Tag autocomplete: backend search endpoint

**Decision**: Add `GET /api/tags?q=<prefix>` endpoint that returns tags matching the prefix (case-insensitive, limited to 10 results). The frontend calls this endpoint as the user types in the tag input field (debounced at 200ms).

**Rationale**: Server-side search scales regardless of tag count and keeps the frontend simple. The alternative (loading all tags upfront) works initially but degrades as tag count grows.

### 6. Remove "Need Input" status: migration strategy

**Decision**: An Alembic migration removes `need-input` from valid statuses. Existing tasks with `need-input` status are updated to `new`, and a "Needs Info" tag is created and attached to each of them via the `task_tags` join table. The migration runs after the `tags` and `task_tags` tables are created (single migration file).

**Rationale**: This preserves the information that was previously encoded in the "Need Input" column — the tag carries the same meaning. Moving to `new` is the safest target status since it's the starting column.

### 7. Model list endpoint: backend proxy

**Decision**: Add `GET /api/llm/models` (admin-only) that calls `LITELLM_BASE_URL/v1/models` server-side and returns the response. The frontend settings page calls this endpoint to populate the model dropdown.

**Rationale**: The frontend cannot call LiteLLM directly — it doesn't have the API key and LiteLLM may not be exposed publicly. A backend proxy keeps credentials server-side and allows future caching or filtering of the model list.

### 8. Settings page model dropdown: save on selection

**Decision**: The model dropdown on the settings page shows available models from the `/api/llm/models` endpoint. The current selection (from `GET /api/settings` key `llm_model`) is pre-selected. Changing the selection saves immediately via `PUT /api/settings` with `{llm_model: "<selected>"}`. If no `llm_model` setting exists, the dropdown defaults to `claude-haiku-4-5-20251001`.

**Rationale**: Immediate save on selection is simpler than adding a separate save button for a single dropdown. The default model ensures the system works out of the box without admin configuration.

### 9. Task card display: title + tags, no status

**Decision**: Task cards display the title and any tags (as small colored pills). The status text currently shown on cards is removed — the column the card is in already indicates status.

**Rationale**: Removing redundant information declutters the cards and makes room for tags. Tags are more useful metadata to display at a glance than status.

### 10. Description field in edit modal

**Decision**: The edit modal gains a textarea for the task description below the title field. The description is optional and can be edited freely. Tags are managed via a separate input below the description.

**Rationale**: Users need to view and edit the full description somewhere. The edit modal is the natural place since it already handles task editing.

## Risks / Trade-offs

- **[Risk] LLM latency on task creation** → Mitigated by using a fast model (Haiku) and falling back to truncated title + "Needs Info" tag if the call fails or times out (5 second timeout).
- **[Risk] LiteLLM unavailable** → Task creation still works — the LLM call is best-effort. Title generation degrades gracefully.
- **[Risk] Word count threshold is imperfect** → 5 words is a heuristic. "Fix bug in auth module" (5 words) is a fine title but technically at the boundary. This is acceptable — users can always edit the title.
- **[Trade-off] Single migration for schema changes + data migration** → Simpler to manage but not independently reversible. Acceptable since this is a forward-only change.
- **[Trade-off] Tag autocomplete adds API calls** → Mitigated by debouncing (200ms) and limiting results (10). The query is a simple `ILIKE` prefix match on an indexed column.

## Migration Plan

1. **Database**: Single Alembic migration that:
   - Adds `description` column (nullable text) to `tasks` table
   - Creates `tags` table and `task_tags` join table
   - Migrates `need-input` tasks to `new` status with "Needs Info" tag
2. **Backend**: Add `openai` dependency, new endpoints, updated task create logic. Existing endpoints remain backward-compatible (title still works, description and tags are optional).
3. **Frontend**: Update components for 6 columns, new card layout, tag UI. All changes are additive or visual — no breaking changes to user workflows.
4. **Environment**: Add `LITELLM_BASE_URL` and `LITELLM_API_KEY` to docker-compose, Helm values, and deployment config. If not set, LLM features degrade gracefully (fallback title).
5. **Rollback**: Downgrade migration drops `tags`/`task_tags` tables and `description` column, restores `need-input` status. Tasks that were migrated from `need-input` to `new` remain as `new` (the tag is lost on rollback — acceptable since this is a forward-progressing feature).
