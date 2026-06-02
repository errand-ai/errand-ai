## ADDED Requirements

### Requirement: TaskProfile enabled_plugins column
The `task_profiles` table SHALL include an `enabled_plugins` column (JSON, nullable). The column SHALL store a JSON array of plugin UUID strings. A null value SHALL be treated identically to an empty array (no plugins enabled). The CRUD API for task profiles SHALL accept and return this field. Pre-existing profile rows SHALL have `enabled_plugins=null` after the migration.

#### Scenario: Create profile with enabled_plugins
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "research", "enabled_plugins": ["abc-123", "def-456"]}`
- **THEN** the profile is persisted with `enabled_plugins = ["abc-123", "def-456"]`

#### Scenario: Create profile without enabled_plugins
- **WHEN** an admin calls `POST /api/task-profiles` with no `enabled_plugins` field
- **THEN** the profile is created with `enabled_plugins = null`

#### Scenario: Update enabled_plugins
- **WHEN** an admin calls `PUT /api/task-profiles/<id>` with `{"enabled_plugins": ["xyz-789"]}`
- **THEN** the profile is updated with the new plugin list

#### Scenario: Set enabled_plugins to empty array
- **WHEN** an admin calls `PUT /api/task-profiles/<id>` with `{"enabled_plugins": []}`
- **THEN** the profile is persisted with an empty JSON array, semantically equivalent to null

#### Scenario: Invalid enabled_plugins type
- **WHEN** an admin calls `POST /api/task-profiles` with `{"enabled_plugins": "not-a-list"}`
- **THEN** the response is HTTP 422 with a validation error

### Requirement: Alembic migration adds enabled_plugins column to task_profiles
An Alembic migration SHALL add a nullable `enabled_plugins` JSON column to the `task_profiles` table. The migration SHALL be reversible.

#### Scenario: Migration adds column
- **WHEN** the migration runs
- **THEN** the `task_profiles` table gains an `enabled_plugins` JSON column with NULL default

#### Scenario: Existing rows unaffected
- **WHEN** the migration runs against a database with existing task profile rows
- **THEN** all existing rows have `enabled_plugins = NULL`

#### Scenario: Migration is reversible
- **WHEN** the migration is downgraded
- **THEN** the `enabled_plugins` column is dropped from `task_profiles`
