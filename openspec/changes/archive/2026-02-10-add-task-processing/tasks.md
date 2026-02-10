## 1. Database & Models

- [x] 1.1 Create Alembic migration: add `description` column (nullable text) to `tasks` table, create `tags` table (id UUID PK, name unique text), create `task_tags` join table (task_id FK, tag_id FK, composite PK with cascade delete on task)
- [x] 1.2 Migrate existing `need-input` tasks: update status to `new`, create "Needs Info" tag, insert `task_tags` rows linking those tasks to the tag
- [x] 1.3 Add `Tag` and `TaskTag` SQLAlchemy models in `models.py`, add `description` field to `Task` model
- [x] 1.4 Update `VALID_STATUSES` in `main.py` — remove `need-input`, leaving 6 statuses

## 2. OpenAI Client Setup

- [x] 2.1 Add `openai` dependency to backend `requirements.txt` (or `pyproject.toml`)
- [x] 2.2 Create LLM client module (`llm.py`): initialize async OpenAI client from `LITELLM_BASE_URL` and `LITELLM_API_KEY` env vars during app startup; expose `get_llm_client()` helper that returns `None` if not configured
- [x] 2.3 Add `generate_title(description: str)` function: calls `chat.completions.create` with system prompt to summarize into 2-5 word title, reads model from `llm_model` setting (default `claude-haiku-4-5-20251001`), 5-second timeout, returns fallback title on failure

## 3. Tag API Endpoints

- [x] 3.1 Add `GET /api/tags` endpoint with optional `q` query param — returns matching tags (case-insensitive prefix, limit 10, alphabetical), requires authentication
- [x] 3.2 Update `TaskResponse` Pydantic model to include `tags` (list of strings) and `description` (optional string)
- [x] 3.3 Update `GET /api/tasks` and `GET /api/tasks/{id}` to eagerly load and return tags
- [x] 3.4 Update `TaskUpdate` schema to accept optional `tags` field (list of strings); implement tag upsert logic in `PATCH /api/tasks/{id}` — create missing tags, replace task_tags associations

## 4. Task Creation with LLM

- [x] 4.1 Change `TaskCreate` schema from `{title}` to `{input}` field
- [x] 4.2 Update `POST /api/tasks` endpoint: count words in input; if >5 words, call `generate_title()` and store input as description; if <=5 words, use input as title with null description and apply "Needs Info" tag
- [x] 4.3 Update `task_created` event payload to include `tags` and `description`

## 5. LLM Model List Endpoint

- [x] 5.1 Add `GET /api/llm/models` endpoint with `require_admin` dependency — calls OpenAI client `models.list()`, returns sorted array of model ID strings; returns 502 on failure, 503 if client not configured

## 6. Frontend Data Types & API

- [x] 6.1 Update `TaskData` interface in `useApi.ts` — add `description: string | null` and `tags: string[]` fields; remove `need-input` from `TaskStatus` type
- [x] 6.2 Update `createTask()` in `useApi.ts` — send `{input}` instead of `{title}`
- [x] 6.3 Add `fetchTags(query: string)` function in `useApi.ts` — calls `GET /api/tags?q=<query>`
- [x] 6.4 Add `fetchLlmModels()` function in `useApi.ts` — calls `GET /api/llm/models`
- [x] 6.5 Add `saveLlmModel(model: string)` function in `useApi.ts` — calls `PUT /api/settings` with `{llm_model: model}`

## 7. Frontend Kanban Board Updates

- [x] 7.1 Update `KanbanBoard.vue` columns array — remove `need-input` entry (6 columns)
- [x] 7.2 Update `TaskForm.vue` placeholder from "New task title..." to "New task...", rename internal variable from `title` to `input`
- [x] 7.3 Update `TaskCard.vue` — remove status text line, add tag pills display below title

## 8. Frontend Edit Modal Updates

- [x] 8.1 Update `TaskEditModal.vue` — remove `need-input` from statuses array (6 statuses)
- [x] 8.2 Add description textarea field below title in edit modal
- [x] 8.3 Add tag input area with removable tag pills, text input, and autocomplete dropdown (debounced 200ms, calls `fetchTags`)
- [x] 8.4 Update save handler to include `description` and `tags` in PATCH payload

## 9. Settings Page LLM Model Dropdown

- [x] 9.1 Add "LLM Model" section to `SettingsPage.vue` with dropdown populated from `fetchLlmModels()`
- [x] 9.2 Pre-select current model from settings (key `llm_model`, default `claude-haiku-4-5-20251001`)
- [x] 9.3 Save on selection change via `saveLlmModel()`, show success/error feedback

## 10. Environment & Configuration

- [x] 10.1 Add `LITELLM_BASE_URL` and `LITELLM_API_KEY` to `docker-compose.yml` (with placeholder/empty values)
- [x] 10.2 Add LiteLLM env vars to Helm chart values and deployment template

## 11. Backend Tests

- [x] 11.1 Add tests for tag autocomplete endpoint (`GET /api/tags` — with query, without query, no matches)
- [x] 11.2 Add tests for task creation with LLM (mock OpenAI client — long input generates title, short input uses title directly with "Needs Info" tag, LLM failure uses fallback)
- [x] 11.3 Add tests for task PATCH with tags (set tags, remove tags, tags field omitted preserves existing)
- [x] 11.4 Add tests for `GET /api/llm/models` (admin access, non-admin 403, LLM unavailable 502, not configured 503)
- [x] 11.5 Add tests for updated task responses (include description and tags fields)
- [x] 11.6 Add test for `need-input` status rejection (HTTP 422)

## 12. Frontend Tests

- [x] 12.1 Add tests for updated `TaskCard` (displays tags, no status text)
- [x] 12.2 Add tests for `TaskForm` (placeholder text, sends `{input}`)
- [x] 12.3 Add tests for tag input in edit modal (add tag, remove tag, autocomplete dropdown)
- [x] 12.4 Add tests for description field in edit modal
- [x] 12.5 Add tests for LLM model dropdown on settings page (loads models, saves selection, handles errors)

## 13. Verification

- [x] 13.1 Run full backend test suite (`pytest`) — all tests pass
- [x] 13.2 Run full frontend test suite (`vitest`) — all tests pass
- [x] 13.3 Run `docker compose up --build` and verify end-to-end: create task with long description (title generated), create short task (gets "Needs Info" tag), edit tags in modal, verify card display, verify settings model dropdown
