## ADDED Requirements

### Requirement: CLAUDE.md discovery after git clone
The system prompt SHALL instruct the agent that after executing any `git clone` command, it MUST check for a `CLAUDE.md` file in the root of the cloned repository. If the file exists, the agent SHALL read its full contents and treat them as project-specific instructions that guide how the agent works within that repository. The agent SHALL follow CLAUDE.md instructions for the remainder of the task when working in that repo.

#### Scenario: Repo has CLAUDE.md
- **WHEN** the agent clones a repository and `CLAUDE.md` exists in the repo root
- **THEN** the agent reads the file and incorporates its instructions into its behaviour for that repo

#### Scenario: Repo has no CLAUDE.md
- **WHEN** the agent clones a repository and no `CLAUDE.md` exists in the repo root
- **THEN** the agent continues without repo-specific instructions

#### Scenario: CLAUDE.md contains coding conventions
- **WHEN** the agent reads a `CLAUDE.md` that specifies "always use single quotes in TypeScript"
- **THEN** the agent follows that convention when writing TypeScript code in the repo

### Requirement: Command discovery from .claude/commands/
The system prompt SHALL instruct the agent that after executing any `git clone` command, it MUST check for a `.claude/commands/` directory in the cloned repository. If the directory exists, the agent SHALL list all `.md` files within it (recursively). Each `.md` file defines a command — the relative path within `.claude/commands/` (without the `.md` extension) forms the command name (e.g., `.claude/commands/git/squash.md` defines command `git:squash`). If the user prompt references a command by name (with or without a leading `/`), the agent SHALL read the corresponding `.md` file and execute the steps described in it.

#### Scenario: User prompt invokes a command
- **WHEN** the agent clones a repo containing `.claude/commands/deploy/staging.md` and the user prompt says "run /deploy:staging"
- **THEN** the agent reads `.claude/commands/deploy/staging.md` and executes the steps described in it

#### Scenario: Command directory exists with multiple commands
- **WHEN** the agent clones a repo containing `.claude/commands/test/unit.md` and `.claude/commands/test/integration.md`
- **THEN** the agent is aware of commands `test:unit` and `test:integration` and can invoke either if referenced

#### Scenario: No commands directory
- **WHEN** the agent clones a repository and no `.claude/commands/` directory exists
- **THEN** the agent continues without registering any repo commands

#### Scenario: Command not referenced in prompt
- **WHEN** the agent discovers commands in a repo but the user prompt does not reference any of them
- **THEN** the agent does not read or execute any command files

### Requirement: Skill discovery from .claude/skills/
The system prompt SHALL instruct the agent that after executing any `git clone` command, it MUST check for a `.claude/skills/` directory in the cloned repository. If the directory exists, the agent SHALL find all `SKILL.md` files within subdirectories. For each `SKILL.md`, the agent SHALL read the YAML frontmatter (the `name` and `description` fields between `---` delimiters) to understand what the skill does. If a skill appears relevant to the current task based on its description, the agent SHALL read the full `SKILL.md` file and follow its instructions.

#### Scenario: Relevant skill found
- **WHEN** the agent clones a repo containing `.claude/skills/tdd/SKILL.md` with frontmatter `description: "Use test-driven development for all code changes"` and the user prompt asks to implement a feature
- **THEN** the agent reads the full `SKILL.md` and follows the TDD workflow described in it

#### Scenario: Multiple skills, one relevant
- **WHEN** the agent clones a repo with skills `tdd`, `code-review`, and `deployment` and the user prompt asks to review code
- **THEN** the agent reads the full `code-review/SKILL.md` and follows it, without reading the other skill files

#### Scenario: No skills directory
- **WHEN** the agent clones a repository and no `.claude/skills/` directory exists
- **THEN** the agent continues without discovering any repo skills

#### Scenario: Skills exist but none relevant
- **WHEN** the agent clones a repo with a `deployment` skill and the user prompt asks to fix a typo
- **THEN** the agent does not read the full deployment skill file
