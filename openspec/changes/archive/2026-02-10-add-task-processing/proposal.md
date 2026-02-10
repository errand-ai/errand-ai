## Why

Tasks currently store only a title and status — there is no way to capture detailed descriptions or categorize tasks. The input box prompts for a "title" which feels heavy for quick task entry. The "Need Input" column was a workaround for flagging tasks that lack detail, but a tagging system is more flexible and doesn't waste a kanban column on metadata. Task cards also redundantly display the status text even though the column already conveys state. Finally, there is no LLM integration yet — introducing one via LiteLLM (with model selection in the admin settings) sets up the foundation for future AI-powered features while immediately providing value through automatic title generation.

## What Changes

- **Simplify task input**: Change the placeholder from "New task title..." to "New task..." (remove the word "title")
- **Remove "Need Input" column**: Drop the `need-input` status from columns and valid statuses; migrate existing `need-input` tasks to `new` with a "Needs Info" tag
- **Add tags to tasks**: New `tags` table (many-to-many via `task_tags` join table), each tag has a unique name; tasks can have zero or more tags
- **Tag management in edit modal**: Add a free-form text input for tags in the task edit modal with a context-sensitive dropdown showing matching existing tags as the user types
- **Expand task data model**: Tasks gain a `description` field (nullable text) alongside the existing `title`; the API and frontend types are updated accordingly
- **Auto-generate task titles via LLM**: When a new task is created with a description longer than a few words, call LiteLLM to summarize it into a short title; if the input is only a few words, use it as the title directly and auto-apply the "Needs Info" tag
- **Update task card display**: Cards show the task title (not the full description) and any tags; **remove the status text** from cards (the column already indicates status)
- **LLM model selection setting**: Add a "Model" dropdown to the admin settings page; the dropdown is populated by calling the LiteLLM `/v1/models` endpoint; the selected model is persisted via the existing settings API with key `llm_model`; defaults to `claude-haiku-4-5-20251001` if no setting exists
- **LiteLLM environment variables**: Backend reads `LITELLM_BASE_URL` and `LITELLM_API_KEY` from environment variables for LLM proxy connectivity

## Capabilities

### New Capabilities
- `task-tags`: Tag data model, tag CRUD, many-to-many relationship with tasks, tag autocomplete endpoint
- `llm-integration`: OpenAI SDK client (pointed at LiteLLM proxy), title generation from descriptions, model listing, environment variable configuration

### Modified Capabilities
- `kanban-frontend`: Remove "Need Input" column, remove status text from cards, display tags on cards, update task input placeholder
- `task-api`: Add `description` and `tags` fields to task endpoints, remove `need-input` from valid statuses, add tag management endpoints
- `task-edit-modal`: Add tag input with autocomplete dropdown, add description field, remove `need-input` from status selector
- `admin-settings-ui`: Add LLM model selector dropdown populated from LiteLLM `/v1/models`
- `admin-settings-api`: Add endpoint to proxy LiteLLM model list (avoids exposing LiteLLM credentials to frontend)

## Impact

- **Database**: New `tags` and `task_tags` tables; `description` column added to `tasks` table; Alembic migration to remove `need-input` status and convert existing tasks
- **Backend**: OpenAI SDK client for LLM calls (pointed at LiteLLM proxy), new tag endpoints, updated task create/update logic with LLM call, new model list proxy endpoint
- **Frontend**: Updated `TaskData` type, updated `TaskCard` (tags display, no status), updated `TaskForm` (placeholder), updated `TaskEditModal` (tags + description), updated `KanbanBoard` (6 columns instead of 7), updated `SettingsPage` (model dropdown)
- **Dependencies**: `openai` Python SDK added to backend (used as the LLM client, pointed at LiteLLM's OpenAI-compatible API — gives future flexibility to swap LiteLLM for any OpenAI-compatible provider)
- **Environment**: `LITELLM_BASE_URL` and `LITELLM_API_KEY` env vars required for LLM features (passed as `base_url` and `api_key` to the OpenAI client); docker-compose and Helm values need updating
- **Breaking**: `need-input` status removed — existing tasks with this status will be migrated to `new` with "Needs Info" tag
