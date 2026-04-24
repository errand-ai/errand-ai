## ADDED Requirements

### Requirement: Per-task encrypted environment variables via MCP
The `new_task` and `schedule_task` MCP tools SHALL accept an optional `env` parameter (typed as `dict | None` for correct MCP JSON schema generation) containing key/value pairs to be injected as environment variables into the task-runner container.

#### Scenario: Task created with env vars
- **WHEN** `new_task` is called with `env={"PAPERCLIP_TOKEN": "eyJ...", "CALLBACK_URL": "https://..."}`
- **THEN** the values SHALL be encrypted with the Fernet cipher and stored in the task's `encrypted_env` column
- **AND** the task SHALL be created normally

#### Scenario: Task created without env vars
- **WHEN** `new_task` is called without the `env` parameter
- **THEN** the task SHALL be created normally with `encrypted_env` as null (backward compatible)

#### Scenario: Encryption key not configured
- **WHEN** `new_task` is called with `env` but `CREDENTIAL_ENCRYPTION_KEY` is not set
- **THEN** the tool SHALL return an error: `"Error: Cannot store encrypted env vars — encryption key not configured."`

#### Scenario: Env vars injected at runtime
- **WHEN** the task manager executes a task that has `encrypted_env` set
- **THEN** the values SHALL be decrypted and merged into the container's environment variables
- **AND** per-task env vars SHALL override global credentials with the same key name

### Requirement: Task model encrypted_env column
The Task model SHALL have an `encrypted_env` column for storing Fernet-encrypted environment variable JSON.

#### Scenario: Database migration
- **WHEN** the migration is applied
- **THEN** a nullable `encrypted_env` Text column SHALL be added to the `tasks` table
- **AND** existing tasks SHALL have `encrypted_env` as null
