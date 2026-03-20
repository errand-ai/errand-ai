## ADDED Requirements

### Requirement: Cloud storage system skill
A system skill SHALL exist at `/app/system-skills/cloud-storage/cloud-storage/SKILL.md` containing instructions for using cloud storage tools. The skill SHALL cover: available operations (list, read, write, delete, file info, create folder, move), path-based file access syntax, ETag-based optimistic concurrency pattern, and error handling guidance (permission, not found, auth errors).

#### Scenario: Skill included when cloud storage injected
- **WHEN** the task manager prepares a task and at least one cloud storage MCP server (OneDrive) is injected
- **THEN** the `cloud-storage` skill set is included in the skills archive

#### Scenario: Skill excluded when no cloud storage
- **WHEN** the task manager prepares a task and no cloud storage MCP servers are injected
- **THEN** the `cloud-storage` skill set is not included

#### Scenario: SKILL.md contains ETag instructions
- **WHEN** an agent reads `/workspace/skills/cloud-storage/SKILL.md`
- **THEN** the file contains instructions for using ETag-based optimistic concurrency when writing files

#### Scenario: SKILL.md under 500 words
- **WHEN** the cloud-storage SKILL.md is measured
- **THEN** it contains fewer than 500 words of instructions
