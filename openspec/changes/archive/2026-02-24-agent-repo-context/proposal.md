## Why

The task-runner agent can clone git repositories via `execute_command`, but it has no awareness of repo-level context files. Claude Code and similar tools use `CLAUDE.md` for project instructions, `.claude/commands/` for custom slash commands, and `.claude/skills/` for reusable skill definitions. When our agent clones a repo, it should automatically discover and use these files — giving it project-specific guidance, available commands, and relevant skills without the user needing to manually specify them.

## What Changes

- Add a system prompt section instructing the agent to check for `CLAUDE.md` in any cloned repo root and incorporate its contents as project instructions
- Add a system prompt section instructing the agent to discover `.claude/commands/*/*.md` files and treat them as available commands that can be invoked when the user prompt matches
- Add a system prompt section instructing the agent to discover `.claude/skills/*/SKILL.md` files, read headers to understand available skills, and process the full file when relevant
- These instructions are purely prompt-based — no code changes to the task-runner Python application, only changes to the system prompt assembled by the worker

## Capabilities

### New Capabilities
- `agent-repo-context`: Instructions added to the system prompt that direct the agent to discover and use CLAUDE.md, commands, and skills from cloned git repositories

### Modified Capabilities
- `task-worker`: The worker's system prompt assembly gains a new section for repo context discovery instructions

## Impact

- **errand/worker.py**: New block appended to the system prompt during assembly (similar to existing Perplexity/skills/Hindsight blocks)
- **No task-runner code changes**: This is entirely prompt engineering — the agent already has `execute_command` which can read files
- **No API changes**: No new endpoints or configuration
- **No database changes**: No new settings or models
