## 1. Data Model & Migration

- [x] 1.1 Add `Skill` model to `backend/models.py` (id, name, description, instructions, created_at, updated_at)
- [x] 1.2 Add `SkillFile` model to `backend/models.py` (id, skill_id FK, path, content, created_at) with unique constraint on (skill_id, path)
- [x] 1.3 Create Alembic migration: create `skills` and `skill_files` tables, migrate existing skills from `Setting(key="skills")` with auto-slugification, remove the settings key
- [x] 1.4 Write tests for the migration (empty DB, existing skills, name conflict slugification)

## 2. Skills API

- [x] 2.1 Add skill name validation helper: lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens, max 64 chars
- [x] 2.2 Add skill file path validation helper: must be in `scripts/`, `references/`, or `assets/`, one level deep
- [x] 2.3 Implement `GET /api/skills` — list all skills with file metadata (no content)
- [x] 2.4 Implement `POST /api/skills` — create skill with name/description/instructions validation, admin required
- [x] 2.5 Implement `GET /api/skills/{id}` — get single skill with files including content
- [x] 2.6 Implement `PUT /api/skills/{id}` — update skill fields, validate name/description, admin required
- [x] 2.7 Implement `DELETE /api/skills/{id}` — delete skill with cascade, admin required
- [x] 2.8 Implement `POST /api/skills/{id}/files` — add file to skill with path validation, admin required
- [x] 2.9 Implement `DELETE /api/skills/{id}/files/{file_id}` — remove file from skill, admin required
- [x] 2.10 Remove skills handling from `PUT /api/settings` (ignore skills field in request body)
- [x] 2.11 Remove skills from `GET /api/settings` response
- [x] 2.12 Write backend tests for all skills API endpoints (CRUD, validation, auth, edge cases)

## 3. Worker — File-Based Skill Injection

- [x] 3.1 Update `read_settings()` to query `skills` and `skill_files` tables instead of `Setting(key="skills")`
- [x] 3.2 Add function to assemble Agent Skills tar archive: for each skill, create `<name>/SKILL.md` (YAML frontmatter + body) and `<name>/<path>` for each attached file
- [x] 3.3 Update `process_task_in_container()` to write skills archive to `/workspace/skills/` via `put_archive()`
- [x] 3.4 Replace the system prompt "call list_skills" directive with the skill manifest (table of name + description, directive to read SKILL.md files)
- [x] 3.5 Remove the automatic backend MCP server injection for skills (the block that adds `content-manager` to mcp_config when skills exist)
- [x] 3.6 Write worker tests for skill directory assembly (SKILL.md format, file paths, empty skills, manifest in system prompt)

## 4. MCP Server Cleanup

- [x] 4.1 Remove `list_skills` tool from `backend/mcp_server.py`
- [x] 4.2 Remove `get_skill` tool from `backend/mcp_server.py`
- [x] 4.3 Update MCP server tests to remove skill tool test cases

## 5. Frontend — Skills UI

- [x] 5.1 Reorganise settings page into three groups with headers: "Agent Configuration", "Task Management", "Integrations & Security"
- [x] 5.2 Move Skills section to always-visible (not collapsible), positioned after System Prompt in the Agent Configuration group
- [x] 5.3 Replace skills CRUD to use new `/api/skills` endpoints instead of settings API
- [x] 5.4 Add Agent Skills name validation to the skill form (lowercase + hyphens, inline error, real-time feedback)
- [x] 5.5 Add character counter to description field (max 1024)
- [x] 5.6 Update description text from MCP reference to "Agent Skills standard" language
- [x] 5.7 Add file manager UI per skill: list attached files grouped by subdirectory (scripts/, references/, assets/), with delete button per file
- [x] 5.8 Add "Add File" form to skill: subdirectory selector (scripts/references/assets), filename input, content textarea, path validation
- [x] 5.9 Write frontend tests for skills section (CRUD, validation, file management, grouped layout)

## 6. Integration Testing

- [x] 6.1 Verify end-to-end: create skill with files via API → worker assembles Agent Skills directory → container receives correct files at `/workspace/skills/<name>/`
- [x] 6.2 Verify migration: existing skills in settings are correctly migrated to new tables on deploy
- [x] 6.3 Verify MCP server still works for remaining tools (new_task, task_status, task_output, post_tweet) after skill tool removal
