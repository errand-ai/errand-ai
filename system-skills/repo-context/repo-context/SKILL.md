---
name: repo-context
description: After cloning any git repository, discover and follow project-specific context — CLAUDE.md project instructions, .claude/commands/ command files, and .claude/skills/ repo-level skills.
---

After cloning any git repository, you MUST check for the following context files and use them.

## CLAUDE.md (Project Instructions)

After any `git clone`, check if `CLAUDE.md` exists in the repository root. If it does, read the file and treat its contents as project-specific instructions. Follow these instructions when working within that repository — they may contain coding conventions, architecture guidance, tool preferences, or workflow rules.

## Commands (`.claude/commands/`)

After any `git clone`, check if a `.claude/commands/` directory exists. If it does, list all `.md` files within it recursively. Each `.md` file defines a command:

- The relative path within `.claude/commands/` (without the `.md` extension) forms the command name
- Directory separators become colons (e.g. `.claude/commands/deploy/staging.md` → command `deploy:staging`)
- If the user prompt references a command by name (with or without a leading `/`), read the corresponding `.md` file and execute the steps described in it
- Do not read command files unless the user prompt references them

## Repo-Level Skills (`.claude/skills/`)

After any `git clone`, check if a `.claude/skills/` directory exists. If it does, find all `SKILL.md` files in subdirectories. For each `SKILL.md`:

- Read only the YAML frontmatter (between `---` delimiters) to get the `name` and `description` fields
- If a skill's description indicates it is relevant to the current task, read the full `SKILL.md` file and follow its instructions
- Do not read the full file for skills that are not relevant to the task
