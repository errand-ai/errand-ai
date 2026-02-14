## 1. Backend — Settings & MCP Tools

- [x] 1.1 Update `GET /api/settings` in `backend/main.py` to include `skills` (read from the `Setting` table with key `skills`, default to empty array if not set). Update `PUT /api/settings` to accept and persist the `skills` field.
- [x] 1.2 Add `list_skills` and `get_skill` MCP tools to `backend/mcp_server.py`. `list_skills` returns `[{name, description}]` for all skills. `get_skill(name)` returns the full instructions text, or an error if not found. Both read from the `skills` setting.

## 2. Backend — Worker

- [x] 2.1 Update `process_task_in_container` in `backend/worker.py` to read the `skills` setting. If at least one skill is defined, append a skill-awareness directive to the system prompt (after any Perplexity block) instructing the agent to call `list_skills` and `get_skill` as needed.

## 3. Frontend — Skills UI

- [x] 3.1 Add a collapsible "Skills" section to `frontend/src/pages/SettingsPage.vue` with a list of existing skills (name + description), add/edit/delete functionality, and a textarea for instructions. Save via the existing `PUT /api/settings` endpoint.

## 4. Tests

- [x] 4.1 Add backend tests for the `skills` field in `GET/PUT /api/settings` (returns empty array when unset, round-trips correctly)
- [x] 4.2 Add backend tests for `list_skills` and `get_skill` MCP tools (returns correct data, handles missing skill)
- [x] 4.3 Add a backend test for the worker skill-awareness directive (appended when skills exist, omitted when none)
- [x] 4.4 Add a frontend test for the skills section on the settings page (renders skills, add/edit/delete interactions)

## 5. Verification

- [x] 5.1 Rebuild with `docker compose up --build` and verify: create a skill in settings UI, create a task, confirm the agent calls `list_skills` and loads the skill via `get_skill` (check runner logs)
