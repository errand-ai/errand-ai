## Why

The task runner agent currently receives a single global system prompt for every task it executes. Users who want different behaviour for different kinds of work (e.g. "research this topic" vs "write code for X" vs "summarise this document") must either cram all instructions into one system prompt or manually edit it before each task. A skill library would let the admin define reusable prompt templates that the agent loads on demand at runtime — keeping context lean and instructions targeted, similar to how Claude Code loads slash-command skills only when invoked.

## What Changes

- Add a `Skill` database model to store named prompt templates with a short description (for discovery) and full instruction content (loaded on demand)
- Expose `list_skills` and `get_skill` tools on the backend MCP server so the task runner agent can discover and load skills at runtime
- Add a skills management section to the admin settings UI for creating, editing, and deleting skills
- Augment the global system prompt with a brief directive telling the agent that skills are available and how to load them via MCP tools

## Capabilities

### New Capabilities

- `skill-library`: Storage, retrieval, and management of reusable agent prompt templates (database model, API endpoints, admin UI)
- `agent-skill-loading`: MCP tools for the agent to list and retrieve skills at runtime, plus system prompt augmentation

### Modified Capabilities

_(none)_

## Impact

- Backend: New `Skill` model + Alembic migration, new API endpoints for CRUD, two new MCP tools on the existing `/mcp` endpoint
- Frontend: New skills management section on the settings page (or a dedicated page)
- Worker: Minor change to append skill-awareness instructions to the system prompt (similar to existing Perplexity injection pattern)
- Task runner: No changes — skills are loaded via existing MCP tool infrastructure
