## Purpose

TaskProfile database model and Alembic migration for custom agent configuration profiles.

## Requirements

### Requirement: TaskProfile database model
The backend SHALL have a `TaskProfile` SQLAlchemy model mapped to the `task_profiles` table with the following columns: `id` (UUID, primary key, server-default), `name` (Text, unique, not null), `description` (Text, nullable), `match_rules` (Text, nullable), `model` (Text, nullable), `system_prompt` (Text, nullable), `max_turns` (Integer, nullable), `reasoning_effort` (Text, nullable), `mcp_servers` (JSON, nullable), `litellm_mcp_servers` (JSON, nullable), `skill_ids` (JSON, nullable), `include_git_skills` (Boolean, not null, server-default true), `created_at` (DateTime with timezone, server-default), `updated_at` (DateTime with timezone, server-default, onupdate).

#### Scenario: Create a task profile
- **WHEN** a TaskProfile row is inserted with `name="email-triage"`, `model="claude-haiku-4-5-20251001"`, `mcp_servers=["gmail"]`
- **THEN** the row is persisted with a generated UUID, timestamps, `include_git_skills` defaulting to true, and all other nullable fields default to NULL

#### Scenario: Unique name constraint
- **WHEN** a TaskProfile row is inserted with `name="email-triage"` and a row with that name already exists
- **THEN** the database raises a unique constraint violation

#### Scenario: Existing profiles get include_git_skills true
- **WHEN** the migration runs against a database with existing task profiles
- **THEN** all existing profiles have `include_git_skills = true`

### Requirement: Alembic migration for task_profiles table and profile_id column
An Alembic migration SHALL create the `task_profiles` table with all columns defined in the model. The same migration SHALL add a `profile_id` column (UUID, nullable) to the `tasks` table with a foreign key to `task_profiles.id` and `ON DELETE SET NULL`. The migration SHALL be reversible.

#### Scenario: Migration creates table and column
- **WHEN** the migration runs
- **THEN** the `task_profiles` table is created and the `tasks` table gains a `profile_id` column

#### Scenario: Existing tasks get null profile_id
- **WHEN** the migration runs against a database with existing tasks
- **THEN** all existing tasks have `profile_id = NULL`

#### Scenario: Migration is reversible
- **WHEN** the migration is downgraded
- **THEN** the `profile_id` column is dropped from `tasks` and the `task_profiles` table is dropped

### Requirement: Profile deletion sets task profile_id to NULL
When a task profile is deleted, any tasks referencing that profile SHALL have their `profile_id` set to NULL (reverting to the default profile). This SHALL be enforced by the `ON DELETE SET NULL` foreign key constraint.

#### Scenario: Delete profile with referencing tasks
- **WHEN** a task profile is deleted and 3 tasks have `profile_id` pointing to it
- **THEN** those 3 tasks have `profile_id` set to NULL

### Requirement: CRUD API for task profiles
The backend SHALL expose the following admin-only endpoints:

- `GET /api/task-profiles` — list all profiles, ordered by name
- `POST /api/task-profiles` — create a new profile (body: name, description, match_rules, model, system_prompt, max_turns, reasoning_effort, mcp_servers, litellm_mcp_servers, skill_ids, include_git_skills)
- `GET /api/task-profiles/{id}` — get a single profile by UUID
- `PUT /api/task-profiles/{id}` — update a profile (full replacement of provided fields)
- `DELETE /api/task-profiles/{id}` — delete a profile

All endpoints SHALL require admin role. The create and update endpoints SHALL validate that `name` is non-empty and unique. The create and update endpoints SHALL validate that `reasoning_effort`, if provided, is one of `low`, `medium`, `high`. The `include_git_skills` field SHALL default to `true` if not provided.

#### Scenario: List profiles
- **WHEN** an admin calls `GET /api/task-profiles` with 2 profiles in the database
- **THEN** the response is a JSON array of 2 profile objects ordered by name

#### Scenario: Create a profile
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "email-triage", "model": "claude-haiku-4-5-20251001", "match_rules": "Tasks about email"}`
- **THEN** the profile is created and returned with a generated UUID

#### Scenario: Create profile with duplicate name
- **WHEN** an admin calls `POST /api/task-profiles` with a name that already exists
- **THEN** the response is HTTP 409 Conflict

#### Scenario: Update a profile
- **WHEN** an admin calls `PUT /api/task-profiles/{id}` with `{"model": "claude-sonnet-4-5-20250929"}`
- **THEN** the profile's model is updated and other fields remain unchanged

#### Scenario: Delete a profile
- **WHEN** an admin calls `DELETE /api/task-profiles/{id}`
- **THEN** the profile is deleted, referencing tasks have profile_id set to NULL, response is HTTP 204

#### Scenario: Get non-existent profile
- **WHEN** an admin calls `GET /api/task-profiles/{id}` with an unknown UUID
- **THEN** the response is HTTP 404

#### Scenario: Invalid reasoning_effort
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "test", "reasoning_effort": "maximum"}`
- **THEN** the response is HTTP 422 with a validation error

#### Scenario: Create profile with include_git_skills false
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "no-git", "skill_ids": ["uuid-1"], "include_git_skills": false}`
- **THEN** the profile is created with `include_git_skills = false`

#### Scenario: Create profile without include_git_skills
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "default-git"}` and no `include_git_skills` field
- **THEN** the profile is created with `include_git_skills = true`

#### Scenario: Update include_git_skills
- **WHEN** an admin calls `PUT /api/task-profiles/{id}` with `{"include_git_skills": false}`
- **THEN** the profile's `include_git_skills` is updated to false

### Requirement: Three-state list field semantics
For JSON list fields (`mcp_servers`, `litellm_mcp_servers`, `skill_ids`), the API SHALL accept three states: `null` (or field omitted) means inherit from default settings, `[]` (empty array) means explicitly none, and a non-empty array means use only those specific values. The database SHALL store SQL NULL for inherit and a JSON array (empty or populated) for explicit values.

#### Scenario: Null means inherit
- **WHEN** a profile is created with `mcp_servers: null`
- **THEN** the database stores SQL NULL for `mcp_servers`, and resolution at execution time inherits all default MCP servers

#### Scenario: Empty array means none
- **WHEN** a profile is created with `mcp_servers: []`
- **THEN** the database stores an empty JSON array, and resolution at execution time provides no user-configured MCP servers

#### Scenario: Explicit array means subset
- **WHEN** a profile is created with `mcp_servers: ["gmail", "errand"]`
- **THEN** the database stores `["gmail", "errand"]`, and resolution at execution time provides only those MCP servers
