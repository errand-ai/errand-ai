## Context

The task-runner agent already has `execute_command` which can run `git clone`, `cat`, `find`, `ls`, etc. The agent can already read files from cloned repos — but it doesn't know it *should*. This change adds system prompt instructions telling the agent to automatically discover and use repo context files (CLAUDE.md, commands, skills) after cloning.

The system prompt is assembled in `errand/worker.py` in the `process_task_in_container()` function. It already has several prompt augmentation blocks (Perplexity, Hindsight, Playwright, Skills). This change adds one more block.

## Goals

- Instruct the agent to read `CLAUDE.md` from any cloned repo and follow its instructions
- Instruct the agent to discover `.claude/commands/` and make them available as invocable commands
- Instruct the agent to discover `.claude/skills/` and use relevant ones
- Keep it purely prompt-based — no task-runner code changes needed

## Non-Goals

- Automatically cloning repos (the user/task still drives that)
- Injecting repo context files into the container at build time
- Modifying the task-runner Python code or adding new tools
- Supporting nested CLAUDE.md files (only repo root)

## Approach

Add a new system prompt section in `worker.py` that is always appended (like the output instructions). The section instructs the agent on three behaviours:

1. **CLAUDE.md**: After any `git clone`, check for `CLAUDE.md` in the repo root. If found, read it and treat it as project-specific instructions that constrain how the agent works in that repo.

2. **Commands** (`.claude/commands/*/*.md`): After any `git clone`, check for `.claude/commands/` directory. If it exists, list all `.md` files within. Each file defines a command — the filename (without `.md`) is the command name. If the user prompt references a command by name, read the file and execute its steps.

3. **Skills** (`.claude/skills/*/SKILL.md`): After any `git clone`, check for `.claude/skills/` directory. If it exists, list all `SKILL.md` files. Read just the YAML frontmatter (name + description) of each. If a skill is relevant to the current task, read the full file and follow its instructions.

The prompt text lives as a constant string in `worker.py`, appended after the skills manifest block (line ~840). It uses the same pattern as existing augmentation blocks.

## Decisions

- **Always appended**: The repo context instructions are always included in the system prompt, even if the task doesn't involve git. The instructions are conditional ("after any git clone...") so they're no-ops when no repo is cloned. This keeps the logic simple — no settings or feature flags.
- **Prompt-only**: The agent uses `execute_command` to read files. No new Python tools needed.
- **Root CLAUDE.md only**: Only check the repo root, not subdirectories. This matches Claude Code's behaviour.
- **Command format**: Commands are `.md` files under `.claude/commands/<group>/<name>.md`. The full path structure gives the command its name (e.g., `.claude/commands/git/squash.md` → command "git:squash" or "/git/squash"). We instruct the agent to parse the filename as the command name.
