## REMOVED Requirements

### Requirement: list_skills MCP tool
**Reason**: Replaced by file-based skill injection. Skills are now written to the container filesystem by the worker and discovered via the system prompt skill manifest. The agent reads SKILL.md files directly instead of calling MCP tools.
**Migration**: No external consumers. The task runner agent now reads skills from `/workspace/skills/<name>/SKILL.md` using its execute_command tool.

### Requirement: get_skill MCP tool
**Reason**: Replaced by file-based skill injection. Full skill instructions are available as local files in the container.
**Migration**: No external consumers. The task runner agent reads `/workspace/skills/<name>/SKILL.md` directly.
