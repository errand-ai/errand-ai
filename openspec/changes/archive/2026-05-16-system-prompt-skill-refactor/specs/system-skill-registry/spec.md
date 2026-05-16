## ADDED Requirements

### Requirement: System skills registry
The task manager SHALL maintain a registry that maps runtime conditions to system skill sets. Each registry entry SHALL specify a skill set name, a filesystem path relative to the system skills base directory, and a condition function that receives a task context dictionary and returns a boolean.

#### Scenario: Registry evaluated at task preparation
- **WHEN** the task manager prepares a task for execution
- **THEN** it evaluates each registry entry's condition against the current task context
- **AND** includes matching skill sets in the skills archive

#### Scenario: Multiple conditions match
- **WHEN** a task has both a Google token and cloud storage credentials
- **THEN** both the `gws` and `cloud-storage` skill sets are included

#### Scenario: No conditions match
- **WHEN** a task has no special integrations configured
- **THEN** only unconditional skill sets (e.g., `repo-context`) are included

### Requirement: System skills base directory
The task manager SHALL read system skills from `/app/system-skills/` on the server filesystem. Each skill set SHALL be a subdirectory containing one or more skill directories, each with a `SKILL.md` file.

#### Scenario: Skills read from filesystem
- **WHEN** the task manager includes a system skill set named "cloud-storage"
- **THEN** it reads skills from `/app/system-skills/cloud-storage/` and includes them in the archive

#### Scenario: Missing skill set directory
- **WHEN** a registry entry references a path that does not exist on the filesystem
- **THEN** the task manager logs a warning and skips that skill set without failing

### Requirement: Registry extensibility
Adding a new system skill set SHALL require only: (1) adding the skill files to the image build, and (2) adding a registry entry with a condition. No other code changes SHALL be needed.

#### Scenario: New skill set added
- **WHEN** a developer adds a new skill set directory and a registry entry
- **THEN** the skill set is conditionally included in tasks without modifying the prompt assembly logic
