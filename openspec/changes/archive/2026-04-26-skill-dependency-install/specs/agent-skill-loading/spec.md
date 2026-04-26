## ADDED Requirements

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
