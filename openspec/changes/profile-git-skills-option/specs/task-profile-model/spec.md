## MODIFIED Requirements

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

### Requirement: CRUD API for task profiles
The backend SHALL expose the following admin-only endpoints:

- `GET /api/task-profiles` — list all profiles, ordered by name
- `POST /api/task-profiles` — create a new profile (body: name, description, match_rules, model, system_prompt, max_turns, reasoning_effort, mcp_servers, litellm_mcp_servers, skill_ids, include_git_skills)
- `GET /api/task-profiles/{id}` — get a single profile by UUID
- `PUT /api/task-profiles/{id}` — update a profile (full replacement of provided fields)
- `DELETE /api/task-profiles/{id}` — delete a profile

All endpoints SHALL require admin role. The create and update endpoints SHALL validate that `name` is non-empty and unique. The create and update endpoints SHALL validate that `reasoning_effort`, if provided, is one of `low`, `medium`, `high`. The `include_git_skills` field SHALL default to `true` if not provided.

#### Scenario: Create profile with include_git_skills false
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "no-git", "skill_ids": ["uuid-1"], "include_git_skills": false}`
- **THEN** the profile is created with `include_git_skills = false`

#### Scenario: Create profile without include_git_skills
- **WHEN** an admin calls `POST /api/task-profiles` with `{"name": "default-git"}` and no `include_git_skills` field
- **THEN** the profile is created with `include_git_skills = true`

#### Scenario: Update include_git_skills
- **WHEN** an admin calls `PUT /api/task-profiles/{id}` with `{"include_git_skills": false}`
- **THEN** the profile's `include_git_skills` is updated to false
