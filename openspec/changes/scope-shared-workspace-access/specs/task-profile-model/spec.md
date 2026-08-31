## ADDED Requirements

### Requirement: TaskProfile shared_workspace_read_only column

The `task_profiles` table SHALL gain `shared_workspace_read_only` (boolean, NOT NULL, default `false`). When `true`, the profile's shared-workspace mount SHALL be attached read-only, so that no process in the task container can modify the user's workspace.

The field SHALL be exposed through the existing task profile CRUD API alongside `shared_workspace_enabled` and `shared_workspace_subpath`, following the same field-handling patterns.

The field SHALL be meaningful only when `shared_workspace_enabled` is `true`. Setting it on a profile with the workspace disabled SHALL be accepted and persisted rather than rejected, so that enabling the workspace later does not silently grant write access.

#### Scenario: Profile created with a read-only workspace

- **WHEN** a profile is created with `shared_workspace_enabled=true` and `shared_workspace_read_only=true`
- **THEN** the profile persists both values and the CRUD API returns them

#### Scenario: Default is read-write

- **WHEN** a profile is created without specifying `shared_workspace_read_only`
- **THEN** the stored value is `false` and the profile's mount behaviour is unchanged

#### Scenario: Read-only persists while the workspace is disabled

- **WHEN** a profile has `shared_workspace_enabled=false` and `shared_workspace_read_only=true`
- **THEN** the value is persisted
- **AND** later enabling the workspace yields a read-only mount rather than a writable one

### Requirement: Alembic migration adds shared_workspace_read_only to task_profiles

An Alembic migration SHALL add the `shared_workspace_read_only` column to `task_profiles` with a server default of `false` and NOT NULL. The migration SHALL NOT modify any existing row's other values.

#### Scenario: Migration applied to a populated table

- **WHEN** the migration runs against a database containing existing profiles
- **THEN** the column exists, every existing profile has `shared_workspace_read_only=false`, and no other profile data is modified
