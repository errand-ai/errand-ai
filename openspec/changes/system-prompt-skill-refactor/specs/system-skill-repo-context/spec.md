## ADDED Requirements

### Requirement: Repo context discovery system skill
A system skill SHALL exist at `/app/system-skills/repo-context/repo-context/SKILL.md` containing instructions for discovering and following project-specific context in cloned repositories. The skill SHALL cover: finding and reading CLAUDE.md files, discovering commands in `.claude/commands/`, and discovering repo-level skills in `.claude/skills/`.

#### Scenario: Skill always included
- **WHEN** the task manager prepares any task
- **THEN** the `repo-context` skill set is included in the skills archive (unconditional)

#### Scenario: SKILL.md covers CLAUDE.md discovery
- **WHEN** an agent reads `/workspace/skills/repo-context/SKILL.md`
- **THEN** the instructions explain how to find and follow CLAUDE.md project instructions

#### Scenario: SKILL.md covers commands directory
- **WHEN** an agent reads `/workspace/skills/repo-context/SKILL.md`
- **THEN** the instructions explain how to list and execute commands from `.claude/commands/`

#### Scenario: SKILL.md covers repo-level skills
- **WHEN** an agent reads `/workspace/skills/repo-context/SKILL.md`
- **THEN** the instructions explain how to discover and selectively read skills from `.claude/skills/`
