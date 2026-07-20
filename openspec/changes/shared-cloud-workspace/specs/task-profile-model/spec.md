## ADDED Requirements

### Requirement: Shared workspace fields on TaskProfile

The `task_profiles` table SHALL gain `shared_workspace_enabled` (boolean, NOT NULL, default false) and `shared_workspace_subpath` (nullable string). `shared_workspace_subpath`, when set, confines the profile's mount to that subdirectory of the workspace folder; when NULL, the workspace root is mounted. Both fields SHALL be exposed through the existing task profile CRUD API and follow existing profile-field validation patterns (subpath MUST be a relative path without `..` traversal).

#### Scenario: Migration adds columns

- **WHEN** the Alembic migration for this change runs against an existing database
- **THEN** both columns exist, existing profiles have `shared_workspace_enabled=false`, and no data is modified

#### Scenario: Subpath validation

- **WHEN** a profile is saved with `shared_workspace_subpath` containing `..`
- **THEN** the API rejects the request with a validation error

#### Scenario: CRUD round-trip

- **WHEN** a profile is created with `shared_workspace_enabled=true` and subpath `reports/nginx`
- **THEN** the profile API returns both values on read
