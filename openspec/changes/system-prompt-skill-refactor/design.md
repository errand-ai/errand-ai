## Context

The task-runner system prompt is currently built by concatenating a base prompt with multiple conditional instruction blocks in `task_manager.py`. Each integration (cloud storage, Hindsight, repo context) appends its own static text to the prompt. The `add-google-workspace-cli` change introduces system skills — SKILL.md files baked into the image and conditionally injected. This refactor extends that pattern to replace the hardcoded prompt sections with on-demand skills.

Current system prompt assembly (~2.5KB–20KB):
1. Base system prompt (user-provided) — **keep**
2. Relevant Context from Memory (~2KB, prefetched) — **convert to agent-initiated recall**
3. Persistent Memory Instructions (~200B) — **extract to skill**
4. Cloud Storage Instructions (~600B) — **extract to skill**
5. Skills Manifest (~150–500B) — **keep** (simplified)
6. Repo Context Discovery (~1.2KB) — **extract to skill**
7. Tool Catalog (~2–10KB, task-runner side) — **keep** (already lazy-loaded)
8. Output Format Instructions (~500B, task-runner side) — **keep**

After refactor, the server-written system prompt contains only: base prompt + lean skill discovery directive + skills manifest.

## Goals / Non-Goals

**Goals:**

- Extract cloud storage, Hindsight, and repo context instructions into system skill SKILL.md files
- Establish a system skills registry that maps conditions to skill sets
- Remove server-side Hindsight prefetch — agent recalls context itself
- Reduce baseline system prompt to ~1KB (base prompt + discovery directive + manifest)
- Make it trivial to add future integration instructions as skills

**Non-Goals:**

- Changing how the tool catalog works (already lazy-loaded)
- Modifying the output format instructions (critical for structured output parsing)
- Changing the base system prompt content (user-configured)
- Extracting MCP server-specific tool documentation into skills (future work)

## Decisions

### D1: System skills registry — condition-to-skills mapping

A simple registry in `task_manager.py` maps conditions to system skill directories:

```python
SYSTEM_SKILL_REGISTRY = [
    {
        "name": "gws",
        "path": "gws",
        "condition": lambda ctx: ctx.get("google_token"),
    },
    {
        "name": "cloud-storage",
        "path": "cloud-storage",
        "condition": lambda ctx: ctx.get("cloud_storage_injected"),
    },
    {
        "name": "hindsight",
        "path": "hindsight",
        "condition": lambda ctx: ctx.get("hindsight_url"),
    },
    {
        "name": "repo-context",
        "path": "repo-context",
        "condition": lambda ctx: True,  # always included
    },
]
```

At task preparation time, the task manager evaluates conditions against the current task context and includes matching system skills. This is simple, explicit, and easy to extend.

**Alternative considered:** A plugin/discovery system that scans `/app/system-skills/` for metadata files describing conditions. Rejected as over-engineered — the registry is a few lines of code and conditions are known at compile time.

### D2: Agent-initiated Hindsight recall replaces server prefetch

Currently, `recall_from_hindsight()` runs server-side before the task starts, fetching relevant memories and embedding them in the system prompt. This is wasteful when the agent doesn't need memory context, and the query (task title + description) may not be the best recall query.

Instead, the `hindsight` system skill will instruct the agent to:
1. Recall relevant context at the start of the task using the Hindsight MCP tools
2. Use its own judgment about what to query (the agent understands the task better than a simple title+description query)
3. Retain learnings at the end of the task

This removes the `recall_from_hindsight()` function and its HTTP dependency from `task_manager.py`.

**Trade-off:** The agent makes an extra MCP call at task start. But the recall is more targeted (agent-chosen query) and the system prompt is smaller. Net improvement.

### D3: Skill content — concise instructions, not full documentation

Each system skill SKILL.md should contain:
- What the integration does (1–2 lines)
- Key operations/commands available
- Important patterns (e.g., ETag concurrency for cloud storage)
- Common pitfalls and error handling

Keep each skill under ~500 words. The agent has access to MCP tool schemas and `--help` commands for detailed reference — the skill just needs to orient the agent.

### D4: Repo context skill — always included

The repo context discovery instructions (CLAUDE.md, commands directory, repo-level skills) are applicable to every task that involves a cloned repository. Rather than making this conditional, it's always included as a system skill. The agent reads it when it encounters a repo.

### D5: Lean system prompt core

After extraction, the system prompt written by the server contains:

```
{base_system_prompt}

## Skills

Available skills are installed at /workspace/skills/. Each skill directory
contains a SKILL.md file with full instructions.

| Skill | Description |
|-------|-------------|
| ... | ... |

Read the SKILL.md of any relevant skill before using the associated tools
or capabilities.
```

The manifest table is the agent's discovery mechanism. It scans the table, identifies relevant skills, and reads their SKILL.md files on demand.

## Risks / Trade-offs

**[Agent may skip reading skills]** → An agent could ignore the manifest and attempt to use tools without reading instructions. Mitigation: The manifest directive is clear. MCP tool schemas provide basic usage, so the agent won't be completely lost. Integration-specific patterns (like ETag handling) would be missed, but this is recoverable.

**[Extra tool calls at task start]** → Agent reads 1–3 SKILL.md files at the beginning of each task. Mitigation: Each file is <500 words. The cost is minimal compared to the context saved by not front-loading everything.

**[Hindsight recall quality may change]** → Agent-initiated recall might query differently than the server prefetch. Mitigation: This is likely an improvement — the agent can formulate better queries based on task understanding. If recall quality drops, the skill instructions can be tuned.

**[Dependency on add-google-workspace-cli]** → This change assumes the system skills infrastructure (registry, `/app/system-skills/`, conditional injection) from the first change exists. Must be implemented after that change is merged.

## Open Questions

- Should the skills manifest be grouped by category (system vs user vs git) or kept flat? Flat is simpler but a large manifest (40+ gws skills + user skills) could benefit from grouping.
