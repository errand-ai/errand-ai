## MODIFIED Requirements

### Requirement: Worker assembles system prompt for task execution
The worker SHALL construct a system prompt by starting with the base system prompt from settings, then appending augmentation blocks in the following order: (1) pre-loaded Hindsight memories, (2) Perplexity web search instructions (if enabled), (3) Hindsight memory tool instructions (if configured), (4) agent skill manifest (if skills exist), (5) **repo context discovery instructions**. The repo context discovery block SHALL always be appended and SHALL instruct the agent to check for `CLAUDE.md`, `.claude/commands/`, and `.claude/skills/` after any `git clone` operation.

#### Scenario: System prompt includes repo context instructions
- **WHEN** the worker assembles the system prompt for any task
- **THEN** the system prompt includes a "Repo Context Discovery" section instructing the agent to check cloned repos for CLAUDE.md, commands, and skills

#### Scenario: Repo context instructions placed after skill manifest
- **WHEN** the worker assembles the system prompt with both skills and repo context
- **THEN** the repo context instructions appear after the skill manifest section
