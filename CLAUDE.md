# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **content-manager** project. It is in early development — the repository uses OpenSpec (spec-driven workflow) for structured change management.

## OpenSpec Workflow

This project uses the `openspec` CLI (v1.1.1) with the `spec-driven` schema. Changes follow an artifact-driven workflow:

1. **Create a change**: `openspec new change "<name>"` — scaffolds `openspec/changes/<name>/`
2. **Create artifacts in order**: proposal → specs → design → tasks (each builds on the previous)
3. **Implement**: Work through tasks, marking `- [ ]` → `- [x]` as each is completed
4. **Archive**: Once all tasks are done, archive the change

### Key Commands

```bash
openspec new change "<name>"              # Start a new change
openspec status --change "<name>"         # Check artifact status
openspec status --change "<name>" --json  # Machine-readable status
openspec instructions <artifact> --change "<name>"        # Get artifact template/instructions
openspec instructions apply --change "<name>" --json      # Get implementation instructions
openspec list --json                      # List all active changes
openspec schemas --json                   # List available workflow schemas
```

### Slash Commands (Claude Code Skills)

- `/opsx:new` — Start a new change
- `/opsx:continue` — Create the next artifact for a change
- `/opsx:ff` — Fast-forward: create all artifacts in one go
- `/opsx:apply` — Implement tasks from a change
- `/opsx:verify` — Verify implementation matches change artifacts
- `/opsx:archive` — Archive a completed change
- `/opsx:explore` — Think through ideas before starting a change
- `/opsx:sync` — Sync delta specs to main specs

## Project Structure

```
openspec/
  config.yaml          # OpenSpec config (schema: spec-driven)
  changes/             # Active changes (created by openspec new)
```

Source code directories will be created as the project develops.

## Memory (Hindsight)

This project uses a [Hindsight](https://hindsight.vectorize.io) MCP server for persistent memory across conversations. The server is configured as `hindsight` in Claude Code's MCP settings, connected to the `claude-code` memory bank at `https://hindsight.coward.cloud/mcp/claude-code/`.

**You must use Hindsight for all memory operations in this project — do not use local auto-memory files.**

### When to store memories (retain)

- After completing a significant change or implementation
- When discovering important architectural decisions, patterns, or conventions
- When learning project-specific gotchas, workarounds, or debugging insights
- When the user explicitly asks you to remember something

### When to recall memories

- **At the start of every conversation**: recall relevant context about the project, recent changes, and conventions
- Before starting any non-trivial task: recall related past work, decisions, and patterns
- When the user references something from a previous session

### Tools

- **`mcp__hindsight__retain`** — Store a memory. Provide a clear, factual `content` string. Use `context` to categorize (e.g. `"architecture"`, `"conventions"`, `"decisions"`, `"debugging"`).
- **`mcp__hindsight__recall`** — Search memories. Provide a natural language `query`. Use `max_results` to control how many results to retrieve.

### Debugging

- Hindsight REST API is available at `https://hindsight.coward.cloud/api/` (e.g. `/api/banks` lists memory banks)
