## Why

The task-runner's system prompt is assembled by concatenating hardcoded instruction blocks in `task_manager.py`. Conditional sections (cloud storage instructions, Hindsight memory instructions, repo context discovery) are always front-loaded into the prompt regardless of whether the agent actually needs them for a given task. This wastes context tokens and creates a monolithic prompt that grows with every new integration.

With the system skills infrastructure introduced in `add-google-workspace-cli` (skills baked into the image, conditionally injected, loaded on demand by the agent), these instruction blocks can be refactored into skills that the agent reads only when relevant. This also establishes the pattern for future CLI tools and integrations to ship their own instructions as skills rather than growing the system prompt.

## What Changes

- **Extract cloud storage instructions** into a system skill (`cloud-storage`) that the agent reads when cloud storage tools are available, instead of appending a static block to the system prompt
- **Extract Hindsight memory instructions** into a system skill (`hindsight-memory`) that the agent reads when Hindsight MCP is configured, instead of embedding usage instructions in the prompt
- **Extract repo context discovery instructions** into a system skill (`repo-context`) loaded on demand, instead of unconditionally appending ~1.2KB of navigation instructions
- **Slim the system prompt** to a lean core: base user prompt, output format instructions, and a skill discovery directive pointing agents to `/workspace/skills/`
- **Convert pre-loaded Hindsight recall** from a server-side prefetch into a skill instruction that directs the agent to recall relevant context at task start — the agent has the Hindsight MCP tool and can do this itself
- **Establish a system skills registry** pattern in `task_manager.py` that maps conditions (env vars, credentials, MCP configs) to skill sets, making it trivial to add future system skills

## Capabilities

### New Capabilities

- `system-skill-registry`: Registry pattern in task_manager.py that maps runtime conditions to system skill sets, enabling conditional inclusion of skills based on available integrations and configuration
- `system-skill-cloud-storage`: Cloud storage usage instructions packaged as a system skill (SKILL.md) with ETag concurrency patterns, path-based access, and error handling guidance
- `system-skill-hindsight`: Hindsight memory usage instructions packaged as a system skill, including directives for the agent to recall context at task start and retain learnings at task end
- `system-skill-repo-context`: Repository context discovery instructions (CLAUDE.md, commands, repo-level skills) packaged as a system skill

### Modified Capabilities

- `cloud-storage-worker-injection`: Cloud storage instructions moved from inline system prompt constant to a system skill; system prompt no longer appends `CLOUD_STORAGE_INSTRUCTIONS`
- `agent-skill-loading`: System prompt augmentation simplified — lean core prompt with skill discovery directive replaces multiple conditional instruction blocks
- `task-runner-agent`: Agent behavior changes from receiving pre-loaded instructions to discovering and reading relevant skills on demand; Hindsight recall becomes agent-initiated rather than server-prefetched

## Impact

- **Backend**: `task_manager.py` significantly simplified — conditional prompt-building logic replaced by system skill registry lookups; `CLOUD_STORAGE_INSTRUCTIONS`, `REPO_CONTEXT_INSTRUCTIONS` constants removed; `recall_from_hindsight()` server-side prefetch removed
- **Task-runner image**: New system skill files added alongside gws skills at `/opt/system-skills/`; also bundled in server image at `/app/system-skills/`
- **Token usage**: Reduced baseline system prompt size; instructions loaded on demand only when the agent determines relevance
- **Agent behavior**: Agents must read skill files before using integrations — slight increase in tool calls, but better context relevance
- **No API changes**: This is an internal refactor of how instructions reach the agent
