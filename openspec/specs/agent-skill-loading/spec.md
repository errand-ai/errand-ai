## Purpose

Worker-side injection of Agent Skills directories and a skill manifest into the task-runner container and system prompt.

## Requirements

### Requirement: Skill directories written to container
When the worker prepares a task for execution and skills exist (from any source: database, git, or system), the worker SHALL write Agent Skills directories into the container at `/workspace/skills/<name>/`. Each skill directory SHALL contain a `SKILL.md` file with YAML frontmatter (`name` and `description`) followed by the skill's instructions as the markdown body. If the skill has attached files, the worker SHALL also write them at their relative paths within the skill directory (e.g. `/workspace/skills/<name>/scripts/extract.py`). If no skills exist from any source, the worker SHALL NOT create the `/workspace/skills/` directory.

System skills (e.g., gws skills from `/app/system-skills/`) SHALL be included conditionally based on runtime conditions (e.g., Google token present) and merged with DB and git skills at the lowest precedence: DB > git > system. All skills are placed in a flat directory structure under `/workspace/skills/`.

#### Scenario: Skills with files written to container
- **WHEN** the worker prepares a task and 2 DB skills exist: "research" (with 1 file `scripts/search.py`) and "code-review" (no files)
- **THEN** the container contains `/workspace/skills/research/SKILL.md`, `/workspace/skills/research/scripts/search.py`, and `/workspace/skills/code-review/SKILL.md`

#### Scenario: SKILL.md format matches Agent Skills standard
- **WHEN** the worker writes a skill with name "research", description "Conducts web research", and instructions "## Steps\n1. Search the web..."
- **THEN** the SKILL.md file contains `---\nname: research\ndescription: Conducts web research\n---\n\n## Steps\n1. Search the web...`

#### Scenario: No skills — no directory created
- **WHEN** the worker prepares a task and no skills exist from any source (DB, git, or system)
- **THEN** no `/workspace/skills/` directory is created in the container

#### Scenario: System skills merged with DB and git skills
- **WHEN** the worker prepares a task with 1 DB skill "custom-drive", 1 git skill "analysis", and Google token is present (enabling gws system skills)
- **THEN** the container contains `/workspace/skills/custom-drive/`, `/workspace/skills/analysis/`, and `/workspace/skills/gws-*/` directories

#### Scenario: System skill name conflict resolved by precedence
- **WHEN** a DB skill is named "gws-drive" and a system gws skill is also named "gws-drive"
- **THEN** the DB skill takes precedence and the system skill is excluded

### Requirement: Skill manifest in system prompt
When the worker prepares the system prompt for a task and skills exist (from any source), the worker SHALL append a skill manifest section. The manifest SHALL list each skill's name and description in a compact format. The manifest SHALL instruct the agent that skills are installed at `/workspace/skills/`, that each skill directory contains a `SKILL.md` with full instructions and may include `scripts/`, `references/`, and `assets/` subdirectories, and that the agent should read the `SKILL.md` of any relevant skill before proceeding. If no skills exist, the worker SHALL NOT append the manifest.

#### Scenario: Skills exist — manifest appended
- **WHEN** the worker prepares the system prompt and skills exist from any source
- **THEN** the system prompt includes a "## Skills" section with a table listing all skills and a directive to read SKILL.md files from `/workspace/skills/`

#### Scenario: No skills — no manifest
- **WHEN** the worker prepares the system prompt and no skills exist from any source
- **THEN** the system prompt contains no skills section

#### Scenario: Manifest placement after other augmentations
- **WHEN** the worker prepares the system prompt and skills are enabled
- **THEN** the skill manifest appears after other system prompt augmentation blocks

### Requirement: Skills may declare Python dependencies
A skill directory MAY contain a `requirements.txt` file at its root (e.g., `/workspace/skills/<name>/requirements.txt`). This file SHALL follow standard pip requirements format. When present, the task-runner entrypoint SHALL install the declared packages before starting the agent. The `requirements.txt` file SHALL be included in the skill tar archive alongside `SKILL.md` and other skill files.

#### Scenario: Git-sourced skill with requirements.txt
- **WHEN** a git-sourced skill directory contains `SKILL.md`, `scripts/generate.py`, and `requirements.txt`
- **THEN** the skills tar archive includes all three files in the skill's directory

#### Scenario: DB-sourced skill with requirements.txt
- **WHEN** a DB-sourced skill has a file entry with path `requirements.txt` and content `google-genai\npillow\n`
- **THEN** the skills tar archive includes the `requirements.txt` file at `/workspace/skills/<name>/requirements.txt`

### Requirement: Skills may declare Node dependencies
A skill directory MAY contain a `package.json` file at its root (e.g., `/workspace/skills/<name>/package.json`). This file SHALL follow standard npm package.json format. When present, the task-runner entrypoint SHALL install the declared packages before starting the agent.

#### Scenario: Skill with package.json
- **WHEN** a skill directory contains `SKILL.md` and `package.json`
- **THEN** the skills tar archive includes both files in the skill's directory
