## MODIFIED Requirements

### Requirement: TaskProfile database model
The backend SHALL have a `TaskProfile` SQLAlchemy model mapped to the `task_profiles` table with the following columns: `id` (UUID, primary key, server-default), `name` (Text, unique, not null), `description` (Text, nullable), `match_rules` (Text, nullable), `model` (Text, nullable), `system_prompt` (Text, nullable), `max_turns` (Integer, nullable), `reasoning_effort` (Text, nullable), `llm_timeout` (Integer, nullable), `mcp_servers` (JSON, nullable), `litellm_mcp_servers` (JSON, nullable), `skill_ids` (JSON, nullable), `include_git_skills` (Boolean, not null, server-default true), `created_at` (DateTime with timezone, server-default), `updated_at` (DateTime with timezone, server-default, onupdate).

#### Scenario: Create a task profile
- **WHEN** a TaskProfile row is inserted with `name="email-triage"`, `model="claude-haiku-4-5-20251001"`, `mcp_servers=["gmail"]`
- **THEN** the row is persisted with a generated UUID, timestamps, `include_git_skills` defaulting to true, and all other nullable fields default to NULL

#### Scenario: Unique name constraint
- **WHEN** a TaskProfile row is inserted with `name="email-triage"` and a row with that name already exists
- **THEN** the database raises a unique constraint violation

#### Scenario: Existing profiles get include_git_skills true
- **WHEN** the migration runs against a database with existing task profiles
- **THEN** all existing profiles have `include_git_skills = true`

#### Scenario: Existing profiles get null llm_timeout
- **WHEN** the migration that adds the `llm_timeout` column runs against a database with existing task profiles
- **THEN** all existing profiles have `llm_timeout = NULL`

### Requirement: CRUD API for task profiles
The backend SHALL expose the following admin-only endpoints:

- `GET /api/task-profiles` — list all profiles, ordered by name
- `POST /api/task-profiles` — create a new profile (body: name, description, match_rules, model, system_prompt, max_turns, reasoning_effort, llm_timeout, mcp_servers, litellm_mcp_servers, skill_ids, include_git_skills)
- `GET /api/task-profiles/{id}` — get a single profile by UUID
- `PUT /api/task-profiles/{id}` — update a profile (full replacement of provided fields)
- `DELETE /api/task-profiles/{id}` — delete a profile

All endpoints SHALL require admin role. The create and update endpoints SHALL validate that `name` is non-empty and unique. The create and update endpoints SHALL validate that `reasoning_effort`, if provided, is one of `low`, `medium`, `high`. The create and update endpoints SHALL validate that `llm_timeout`, if provided and non-null, is a positive integer (≥ 1). The `include_git_skills` field SHALL default to `true` if not provided.

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

#### Scenario: Create profile with explicit llm_timeout override
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "slow-local", "llm_timeout": 300}`
- **THEN** the profile is created with `llm_timeout = 300`

#### Scenario: Create profile with null llm_timeout (inherit)
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "default-timeout"}` and no `llm_timeout` field
- **THEN** the profile is created with `llm_timeout = NULL`

#### Scenario: Update llm_timeout to null clears override
- **WHEN** an admin calls `PUT /api/task-profiles/{id}` with `{"llm_timeout": null}` against a profile that previously had `llm_timeout = 300`
- **THEN** the profile is updated with `llm_timeout = NULL`

#### Scenario: Invalid llm_timeout (zero)
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "bad", "llm_timeout": 0}`
- **THEN** the response is HTTP 422 with a validation error

#### Scenario: Invalid llm_timeout (negative)
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "bad", "llm_timeout": -10}`
- **THEN** the response is HTTP 422 with a validation error

## ADDED Requirements

### Requirement: Alembic migration adds `llm_timeout` column to task_profiles
An Alembic migration SHALL add a nullable `llm_timeout` integer column to the `task_profiles` table. The migration SHALL be reversible.

#### Scenario: Migration adds column
- **WHEN** the migration runs
- **THEN** the `task_profiles` table gains an `llm_timeout` integer column with NULL default

#### Scenario: Existing rows unaffected
- **WHEN** the migration runs against a database with existing task profile rows
- **THEN** all existing rows have `llm_timeout = NULL`

#### Scenario: Migration is reversible
- **WHEN** the migration is downgraded
- **THEN** the `llm_timeout` column is dropped from `task_profiles`
