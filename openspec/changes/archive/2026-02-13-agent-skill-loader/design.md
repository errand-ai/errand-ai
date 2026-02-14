## Context

The task runner agent currently receives one global system prompt for all tasks. The system prompt is stored in the `Setting` table and injected into the task runner container as `/workspace/system_prompt.txt`. The agent already has access to the backend MCP server (exposing `new_task`, `task_status`, `task_output` tools) via the `/mcp` endpoint.

The goal is to let admins define reusable prompt templates ("skills") that the agent can discover and load at runtime via MCP tools, keeping the base system prompt lean while allowing specialised behaviour per task.

## Goals / Non-Goals

**Goals:**
- Admin can create, edit, and delete skills via the settings UI
- Agent can list available skills (name + description only) via an MCP tool
- Agent can load a specific skill's full instructions via an MCP tool
- System prompt tells the agent that skills exist and how to use them

**Non-Goals:**
- Per-task skill assignment at creation time (future enhancement)
- Skill versioning or change history
- Skill chaining / composition (agent can load multiple skills, but no formal dependency system)
- Skill-specific MCP server configuration (skills only provide instructions, not tool access)

## Decision: Store skills in the existing Setting table

Skills will be stored as a single JSON array under the `skills` key in the `Setting` table, following the same pattern as `mcp_servers` and `credentials`. Each skill entry contains `id` (UUID), `name`, `description`, and `instructions`.

**Why not a separate Skill model/table?** The current settings pattern (JSONB value in `Setting`) is well-established for admin-managed configuration. Skills are admin-managed prompt templates — closer to configuration than domain entities. A separate table would require a new migration, new API endpoints, and more frontend routing. The settings approach reuses existing infrastructure (`GET/PUT /api/settings`) and keeps the feature small.

**Trade-off:** No individual skill URLs or foreign-key references from tasks. Acceptable since per-task skill assignment is a non-goal.

## Decision: Two new MCP tools on the existing backend MCP server

Add `list_skills` and `get_skill` to `backend/mcp_server.py`:

- `list_skills() -> str` — Returns JSON array of `{name, description}` for all skills. Lightweight; the agent calls this to decide which skill to load.
- `get_skill(name: str) -> str` — Returns the full `instructions` text for the named skill. The agent calls this when it decides a skill is relevant.

**Why MCP tools instead of injecting into the system prompt?** This is the core design choice. Injecting all skills into the system prompt would scale poorly (each skill could be hundreds of tokens) and defeats the purpose of on-demand loading. MCP tools let the agent pull in only what it needs, similar to how Claude Code lists available skills but only expands them when invoked.

**Why on the existing MCP server?** The backend already exposes an MCP endpoint at `/mcp` with API key auth. Adding tools there requires no new infrastructure, no new auth, and no new MCP server configuration.

## Decision: Worker appends skill-awareness directive to system prompt

The worker will append a brief directive to the system prompt (after the existing Perplexity injection, if active) telling the agent that skills are available and how to use them. This follows the established pattern in `worker.py` where Perplexity instructions are conditionally appended.

The directive will only be appended if at least one skill is defined in settings. It will instruct the agent to:
1. Call `list_skills` at the start of execution to see available skills
2. Call `get_skill` if a skill seems relevant to the current task
3. Follow the loaded skill's instructions

## Decision: Skills management in the existing settings page

Add a collapsible "Skills" section to `SettingsPage.vue`, similar to the existing "MCP Server Configuration" section. The UI will allow:
- Viewing the list of skills (name + description)
- Adding a new skill (name, description, instructions textarea)
- Editing an existing skill
- Deleting a skill

This keeps all admin configuration in one place rather than introducing a new page/route.

## Risks / Trade-offs

- **Agent may not call list_skills:** The system prompt directive is advisory; the LLM might ignore it. Mitigation: keep the directive clear and concise; accept that skill loading is best-effort.
- **Skill instructions quality depends on admin:** Poorly written skills could confuse the agent. Mitigation: not a technical risk — same as the existing system prompt being admin-managed.
- **Settings JSONB size:** If many large skills are defined, the settings value grows. Mitigation: unlikely to be a practical issue; even 50 skills at 2KB each is only 100KB in JSONB. Revisit if needed.
- **No validation of skill instructions:** Skills are free-text. Mitigation: acceptable for an admin-only feature; same as the system prompt field.

## Migration Plan

- Database: No migration needed — skills are stored in the existing `Setting` table as a new key.
- Deployment: Standard deploy. The worker's skill directive is conditional (only appends if skills exist), so the feature is inert until an admin creates skills.
- Rollback: Remove the code. Skills in settings are harmless configuration that gets ignored.

## Open Questions

_(none)_
