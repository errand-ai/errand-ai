## Why

Every task currently runs with the same agent configuration — same model, same MCP servers, same skills, same system prompt. A simple email-triage task costs the same as a complex coding task because both use the most capable (and expensive) model. Task profiles let users define named agent configurations with different models, tool selections, and instructions, so tasks can be matched to the right (and most cost-effective) configuration.

## What Changes

- New `TaskProfile` database model storing named agent configuration presets: model, system prompt, max turns, reasoning effort, MCP server selection, LiteLLM MCP server selection, skill selection, and free-form match rules for LLM classification.
- New CRUD API endpoints for task profiles (`/api/task-profiles`).
- New `profile_id` foreign key on the Task model (nullable, null = default profile). The "default" profile is virtual — composed from existing global settings.
- Enhanced LLM classification in `llm.py` to include task profile selection alongside the existing category classification, using each profile's `match_rules` text in the classifier prompt.
- Worker resolves the task's profile at execution time, applying the inheritance chain: profile field overrides global setting, `null` inherits from default, `[]` explicitly clears list fields.
- New "Task Profiles" settings sub-page for managing profiles.
- MCP `schedule_task` tool gains an optional `profile` parameter for source-based profile assignment.
- Repeating task rescheduling propagates `profile_id` to the next occurrence.

## Capabilities

### New Capabilities
- `task-profile-model`: Database model, CRUD API, and inheritance resolution logic for task profiles.
- `task-profile-classification`: LLM-based automatic profile assignment during task creation using match rules.
- `task-profile-settings-ui`: Frontend settings sub-page for creating, editing, and deleting task profiles.
- `task-profile-worker-resolution`: Worker-side profile resolution at execution time, applying overrides to global settings.

### Modified Capabilities
- `task-api`: Task model gains `profile_id` FK, task responses include profile info, PATCH allows setting profile.
- `task-categorisation`: LLM classification prompt extended to include profile selection alongside category.
- `task-worker`: Worker reads task profile and resolves agent configuration with inheritance before building container config.
- `mcp-schedule-task`: `schedule_task` MCP tool gains optional `profile` parameter.
- `admin-settings-ui`: Settings navigation gains a "Task Profiles" sub-page.

## Impact

- **Database**: New `task_profiles` table, new `profile_id` column on `tasks` table (Alembic migration).
- **Backend**: New CRUD endpoints in `main.py`, enhanced `generate_title` in `llm.py`, profile resolution logic in `worker.py`, updated `schedule_task` in `mcp_server.py`.
- **Frontend**: New `TaskProfilesPage.vue` settings sub-page, profile selector in task edit modal, updated settings navigation.
- **No breaking changes**: Existing tasks have `profile_id = null` (default profile). All current behavior preserved.
