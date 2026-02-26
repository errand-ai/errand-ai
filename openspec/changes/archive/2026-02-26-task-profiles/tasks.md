## 1. Database Model & Migration

- [x] 1.1 Add `TaskProfile` SQLAlchemy model to `errand/models.py` with all columns: id, name, description, match_rules, model, system_prompt, max_turns, reasoning_effort, mcp_servers (JSON), litellm_mcp_servers (JSON), skill_ids (JSON), created_at, updated_at
- [x] 1.2 Add `profile_id` column (UUID, nullable, FK to task_profiles.id, ON DELETE SET NULL) to Task model
- [x] 1.3 Create Alembic migration: create `task_profiles` table and add `profile_id` column to `tasks`

## 2. Profile CRUD API

- [x] 2.1 Add `GET /api/task-profiles` endpoint (admin-only) — list all profiles ordered by name
- [x] 2.2 Add `POST /api/task-profiles` endpoint (admin-only) — create profile with validation (unique name, valid reasoning_effort)
- [x] 2.3 Add `GET /api/task-profiles/{id}` endpoint (admin-only) — get single profile
- [x] 2.4 Add `PUT /api/task-profiles/{id}` endpoint (admin-only) — update profile
- [x] 2.5 Add `DELETE /api/task-profiles/{id}` endpoint (admin-only) — delete profile (HTTP 204)
- [x] 2.6 Add backend tests for profile CRUD: create, duplicate name, update, delete, list, get non-existent, invalid reasoning_effort

## 3. Task API Changes

- [x] 3.1 Add `profile_id` and `profile_name` to TaskResponse schema and all task serialization (`_task_to_dict`, WebSocket events)
- [x] 3.2 Allow `profile_id` in PATCH /api/tasks/{id} — validate FK exists, allow null to clear
- [x] 3.3 Add backend tests for profile_id on task: create with profile, patch profile, clear profile, delete profile cascades to null

## 4. LLM Classification Enhancement

- [x] 4.1 Add `profile` field (str, nullable, default None) to `LLMResult` dataclass in `llm.py`
- [x] 4.2 Update `_parse_llm_response` to extract `profile` from LLM JSON response
- [x] 4.3 Update `generate_title` to accept a list of profiles and include them in the classifier system prompt with their match_rules
- [x] 4.4 Update task creation in `main.py` to: load profiles, pass to `generate_title`, resolve profile name to profile_id, set on task
- [x] 4.5 Update `new_task` MCP tool to include profile classification (same as API task creation)
- [x] 4.6 Add backend tests for classification: profile selected, unknown profile ignored, no profiles defined, LLM failure fallback

## 5. MCP schedule_task Enhancement

- [x] 5.1 Add optional `profile` parameter (string) to `schedule_task` MCP tool
- [x] 5.2 Implement profile name lookup: resolve name to UUID, return error if not found
- [x] 5.3 Set `profile_id` on created task when profile parameter provided
- [x] 5.4 Add backend tests: schedule with profile, schedule without profile, unknown profile name error

## 6. Worker Profile Resolution

- [x] 6.1 Add `profile_id` to the list of fields loaded during task dequeue in `worker.py`
- [x] 6.2 Add `litellm_mcp_servers` to the settings keys read in `read_settings()`
- [x] 6.3 Implement profile resolution function: load TaskProfile by id, apply inheritance rules (null=inherit, []=empty, value=override) against global settings
- [x] 6.4 Apply resolved model to `OPENAI_MODEL` env var
- [x] 6.5 Apply resolved system_prompt as base system prompt (before Hindsight/skills/repo context blocks)
- [x] 6.6 Apply resolved max_turns and reasoning_effort as container env vars
- [x] 6.7 Apply resolved mcp_servers: filter user-configured MCP server JSON to only include servers in the profile's list (or pass through all if null)
- [x] 6.8 Apply resolved litellm_mcp_servers: use profile's list for x-mcp-servers header (or inherit global setting if null)
- [x] 6.9 Apply resolved skill_ids: filter skills to only those matching the profile's UUIDs (or pass through all if null)
- [x] 6.10 Handle deleted profile gracefully: log warning, use default settings
- [x] 6.11 Update `_reschedule_if_repeating` to propagate `profile_id` to the cloned task
- [x] 6.12 Add worker tests: task with profile, task without profile, deleted profile, repeating task propagation, each override type (model, system_prompt, max_turns, reasoning_effort, mcp_servers, litellm_mcp_servers, skill_ids), null vs [] vs explicit list

## 7. Frontend — Task Profiles Settings Page

- [x] 7.1 Create `TaskProfilesPage.vue` in `frontend/src/pages/settings/`
- [x] 7.2 Add API functions for profile CRUD in `useApi.ts` composable (list, create, update, delete)
- [x] 7.3 Implement profile list view with cards showing: name, description, model, tool summary (override vs default vs none)
- [x] 7.4 Implement profile create/edit form with: name, description, match_rules (textarea), model (dropdown or blank), system_prompt (textarea or blank), max_turns (number or blank), reasoning_effort (dropdown or blank)
- [x] 7.5 Implement three-state list selection UI for MCP servers, LiteLLM MCP servers, and skills: radio group (Inherit/None/Select specific) with checkboxes for specific items
- [x] 7.6 Implement delete with confirmation dialog (warn about tasks reverting to default)
- [x] 7.7 Add empty state with "Add Profile" button
- [x] 7.8 Add route `/settings/profiles` and update settings sidebar navigation to include "Task Profiles" link
- [x] 7.9 Add frontend tests for TaskProfilesPage: list, create, edit, delete, three-state selection, empty state

## 8. Frontend — Task Profile in Task UI

- [x] 8.1 Display profile name on task cards (if not default) — small badge or label
- [x] 8.2 Add profile selector dropdown to task edit modal (list of profiles + "Default" option)
- [x] 8.3 Add frontend tests for profile display and edit
