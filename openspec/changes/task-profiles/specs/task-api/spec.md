## ADDED Requirements

### Requirement: Task model includes profile_id
The Task model SHALL include a `profile_id` field (UUID, nullable) as a foreign key to `task_profiles.id` with `ON DELETE SET NULL`. The field SHALL be included in all task API responses. The field SHALL be writable via `PATCH /api/tasks/{id}`.

#### Scenario: New task has null profile_id
- **WHEN** a task is created via `POST /api/tasks` and the LLM does not select a profile
- **THEN** the task's `profile_id` is null in the response

#### Scenario: Task created with LLM-selected profile
- **WHEN** a task is created and the LLM selects "email-triage"
- **THEN** the task's `profile_id` is set to the email-triage profile's UUID

#### Scenario: Profile set via PATCH
- **WHEN** an editor sends `PATCH /api/tasks/{id}` with `{"profile_id": "uuid-of-coding-profile"}`
- **THEN** the task's `profile_id` is updated to the specified UUID

#### Scenario: Profile cleared via PATCH
- **WHEN** an editor sends `PATCH /api/tasks/{id}` with `{"profile_id": null}`
- **THEN** the task's `profile_id` is set to null (default profile)

#### Scenario: Invalid profile_id rejected
- **WHEN** an editor sends `PATCH /api/tasks/{id}` with `{"profile_id": "nonexistent-uuid"}`
- **THEN** the backend returns HTTP 422 (foreign key violation)

### Requirement: Task response includes profile name
Task API responses SHALL include a `profile_name` field (string, nullable) containing the associated profile's name, or null if the task uses the default profile. This is a convenience field to avoid a separate lookup.

#### Scenario: Task with profile includes name
- **WHEN** a task has `profile_id` referencing a profile named "email-triage"
- **THEN** the API response includes `"profile_name": "email-triage"`

#### Scenario: Task with default profile
- **WHEN** a task has `profile_id = null`
- **THEN** the API response includes `"profile_name": null`
