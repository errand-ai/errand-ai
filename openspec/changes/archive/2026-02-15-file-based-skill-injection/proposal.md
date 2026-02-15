## Why

The current skill delivery mechanism requires the task runner agent to make two MCP round-trips (`list_skills` then `get_skill`) over the network to discover and load skill instructions. This introduces latency, a network dependency from the container back to the backend, and relies on the agent obeying a system prompt directive ("call `list_skills` FIRST") which it can ignore. Research into OpenAI's native skills feature confirmed it targets a different use case (executable bundles in OpenAI-hosted containers via the ShellTool/Responses API) and would lock us into a single provider, but the underlying pattern — pre-mount skill files so the agent can read them locally — is exactly what we should adopt.

The open [Agent Skills standard](https://agentskills.io/specification) defines a portable, vendor-neutral format for packaging agent skills as directories. By adopting this standard fully, we gain progressive disclosure (metadata at startup, instructions on activation, resources on demand), portability between agent platforms, and a clear extension path for skills that include scripts, templates, and reference material alongside instructions.

## What Changes

- **Adopt the Agent Skills directory format end-to-end.** Each skill becomes a directory (`/workspace/skills/<name>/`) containing a required `SKILL.md` manifest (YAML frontmatter + markdown body) and optional subdirectories (`scripts/`, `references/`, `assets/`). The worker assembles these directories from the database and writes them into the container via `put_archive()`.
- **Support optional subdirectories from the start.** Skills can include files in `scripts/`, `references/`, and `assets/` subdirectories alongside the `SKILL.md`. These files are stored in the database as part of the skill data and written into the container. This enables skills that bundle executable scripts, reference documentation, templates, and static assets.
- **Dedicated skills API.** Move skills out of the flat settings key-value store into a dedicated data model and API. Skills with attached files don't fit well in a single JSONB settings value. A `Skill` model with a `SkillFile` child model provides proper structure. New REST endpoints: `GET/POST /api/skills`, `GET/PUT/DELETE /api/skills/{id}`, `POST/DELETE /api/skills/{id}/files`.
- **Revamped Skills UI.** Elevate Skills from a collapsible settings section to a first-class always-visible section. The skill form includes the SKILL.md editor (name, description as frontmatter; instructions as markdown body) plus a file manager for uploading/viewing/deleting files in `scripts/`, `references/`, and `assets/`. Each file is assigned to a subdirectory via a dropdown or path prefix.
- **System prompt skill manifest.** The worker injects a compact skill manifest into the system prompt listing each skill's name and description (~100 tokens total). The agent decides which skills are relevant and reads the full `SKILL.md` and any referenced files via `execute_command`. This follows the spec's progressive disclosure model.
- **Remove the MCP-based skill injection path** from the worker: no more automatic `content-manager` MCP server entry in `mcp.json` for skills, no more `BACKEND_MCP_URL` / `mcp_api_key` requirement for skill-only scenarios.
- **Remove `list_skills` and `get_skill` MCP tools** from the backend MCP server (the remaining tools — `new_task`, `task_status`, `task_output`, `post_tweet` — are unaffected).
- **Reorganise the settings page** into logical groups: "Agent Configuration" (system prompt, skills, LLM models), "Task Management" (archiving, task runner, timezone), "Integrations & Security" (MCP API key, Git SSH key, MCP server config).

## Capabilities

### New Capabilities
- `skills-api`: Dedicated REST API for skill CRUD and file management. Endpoints: `GET/POST /api/skills`, `GET/PUT/DELETE /api/skills/{id}`, `POST/DELETE /api/skills/{id}/files`. Validates Agent Skills naming rules. Stores skill metadata + SKILL.md body + attached files.

### Modified Capabilities
- `agent-skill-loading`: Replace MCP-based skill discovery/loading with Agent Skills directory format. Worker writes `/workspace/skills/<name>/SKILL.md` (and any attached files in `scripts/`, `references/`, `assets/`) into the container. System prompt includes skill manifest and directs the agent to read `SKILL.md` for relevant skills. Remove `list_skills`/`get_skill` MCP tools.
- `task-worker`: Worker assembles Agent Skills directories from the skills API/DB and writes them to the container via `put_archive()`. Remove automatic backend MCP server injection for skills. Replace system prompt directive with skill manifest.
- `skill-library`: Align data model with Agent Skills standard. New `Skill` model (id, name, description, instructions) and `SkillFile` model (id, skill_id, path, content). Enforce naming rules (lowercase + hyphens, no leading/trailing/consecutive hyphens, max 64 chars). Description max 1024 chars. File paths must be within `scripts/`, `references/`, or `assets/` subdirectories. Migrate existing skills from the settings JSONB to the new model.
- `admin-settings-ui`: Elevate Skills section to always-visible first-class section. Add file management (upload, view, delete files per skill with subdirectory assignment). Reorganise page into grouped sections (Agent Configuration / Task Management / Integrations & Security). Add name validation hints and character counters. Update description text to reference Agent Skills standard.
- `mcp-server-endpoint`: Remove `list_skills` and `get_skill` tools. Remaining tools unchanged.

## Impact

- **backend/models.py**: New `Skill` and `SkillFile` models. Skill has id (UUID), name (unique, validated), description, instructions (SKILL.md body), timestamps. SkillFile has id (UUID), skill_id (FK), path (e.g. `scripts/extract.py`), content (text), timestamps.
- **backend/alembic/**: Migration to create `skills` and `skill_files` tables. Data migration to move existing skills from `Setting(key="skills")` to the new tables.
- **backend/main.py**: New skill API endpoints. Remove skills handling from settings API.
- **backend/worker.py**: Replace MCP-based skill injection block with logic to query skills + files from DB, assemble Agent Skills directories, and write via `put_archive()`. Update system prompt.
- **backend/mcp_server.py**: Remove `list_skills` and `get_skill` tool definitions.
- **frontend/src/pages/SettingsPage.vue**: Reorganise into grouped sections. Replace inline skills CRUD with calls to the new skills API. Add file upload/management UI per skill.
- **Tests**: New skills API tests, updated worker tests, remove MCP skill tool tests, frontend tests for file management.
- **No task runner changes**: The agent already has `execute_command` to read files; no code changes to `task-runner/main.py`.
