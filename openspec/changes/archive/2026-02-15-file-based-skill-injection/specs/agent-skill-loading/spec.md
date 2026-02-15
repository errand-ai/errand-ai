## REMOVED Requirements

### Requirement: list_skills MCP tool
**Reason**: Replaced by file-based skill injection. The worker now writes skill directories to the container filesystem and includes a skill manifest in the system prompt. The agent reads skill files directly instead of making MCP tool calls.
**Migration**: Skills are now discovered via system prompt manifest and loaded by reading `/workspace/skills/<name>/SKILL.md` using the execute_command tool.

### Requirement: get_skill MCP tool
**Reason**: Replaced by file-based skill injection. Skill instructions are available as local files in the container at `/workspace/skills/<name>/SKILL.md`.
**Migration**: The agent reads skill instructions from the filesystem instead of calling an MCP tool.

### Requirement: Skill-awareness directive in system prompt
**Reason**: Replaced by a new skill manifest directive that references local skill files instead of MCP tools.
**Migration**: See new "Skill manifest in system prompt" requirement below.

## ADDED Requirements

### Requirement: Skill directories written to container
When the worker prepares a task for execution and skills exist in the database, the worker SHALL write Agent Skills directories into the container at `/workspace/skills/<name>/`. Each skill directory SHALL contain a `SKILL.md` file with YAML frontmatter (`name` and `description`) followed by the skill's instructions as the markdown body. If the skill has attached files, the worker SHALL also write them at their relative paths within the skill directory (e.g. `/workspace/skills/<name>/scripts/extract.py`). If no skills exist, the worker SHALL NOT create the `/workspace/skills/` directory.

#### Scenario: Skills with files written to container
- **WHEN** the worker prepares a task and 2 skills exist: "research" (with 1 file `scripts/search.py`) and "code-review" (no files)
- **THEN** the container contains `/workspace/skills/research/SKILL.md`, `/workspace/skills/research/scripts/search.py`, and `/workspace/skills/code-review/SKILL.md`

#### Scenario: SKILL.md format matches Agent Skills standard
- **WHEN** the worker writes a skill with name "research", description "Conducts web research", and instructions "## Steps\n1. Search the web..."
- **THEN** the SKILL.md file contains `---\nname: research\ndescription: Conducts web research\n---\n\n## Steps\n1. Search the web...`

#### Scenario: No skills — no directory created
- **WHEN** the worker prepares a task and no skills exist in the database
- **THEN** no `/workspace/skills/` directory is created in the container

### Requirement: Skill manifest in system prompt
When the worker prepares the system prompt for a task and skills exist in the database, the worker SHALL append a skill manifest section. The manifest SHALL list each skill's name and description in a compact format. The manifest SHALL instruct the agent that skills are installed at `/workspace/skills/`, that each skill directory contains a `SKILL.md` with full instructions and may include `scripts/`, `references/`, and `assets/` subdirectories, and that the agent should read the `SKILL.md` of any relevant skill before proceeding. If no skills exist, the worker SHALL NOT append the manifest.

#### Scenario: Skills exist — manifest appended
- **WHEN** the worker prepares the system prompt and 2 skills exist ("research" and "code-review")
- **THEN** the system prompt includes a "## Skills" section with a table listing both skills and a directive to read SKILL.md files from `/workspace/skills/`

#### Scenario: No skills — no manifest
- **WHEN** the worker prepares the system prompt and no skills exist
- **THEN** the system prompt contains no skills section

#### Scenario: Manifest placement after other augmentations
- **WHEN** the worker prepares the system prompt and both Perplexity and skills are enabled
- **THEN** the skill manifest appears after the Perplexity instruction block
