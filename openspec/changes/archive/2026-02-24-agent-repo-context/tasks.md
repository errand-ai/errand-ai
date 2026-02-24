## Tasks

### 1. Add repo context discovery instructions to system prompt

- [x] 1.1 Add a `REPO_CONTEXT_INSTRUCTIONS` constant string in `errand/worker.py` containing the full prompt text for CLAUDE.md discovery, command discovery, and skill discovery
- [x] 1.2 Append `REPO_CONTEXT_INSTRUCTIONS` to `system_prompt` in `process_task_in_container()` after the skill manifest block (after line ~840)

### 2. Write the CLAUDE.md discovery prompt section

- [x] 2.1 Write prompt text instructing the agent: after any `git clone`, check for `CLAUDE.md` in the repo root, read it if present, and follow its instructions as project-specific guidance

### 3. Write the command discovery prompt section

- [x] 3.1 Write prompt text instructing the agent: after any `git clone`, check for `.claude/commands/` directory, list all `.md` files recursively, derive command names from relative paths (e.g. `deploy/staging.md` → `deploy:staging`), and if the user prompt references a command, read the file and execute its steps

### 4. Write the skill discovery prompt section

- [x] 4.1 Write prompt text instructing the agent: after any `git clone`, check for `.claude/skills/` directory, find all `SKILL.md` files, read YAML frontmatter (name + description), and if a skill is relevant to the task, read the full file and follow its instructions

### 5. Tests

- [x] 5.1 Add test in `errand/tests/test_worker.py` verifying that the assembled system prompt contains the repo context discovery instructions
- [x] 5.2 Add test verifying the repo context section appears after the skill manifest when skills are present
