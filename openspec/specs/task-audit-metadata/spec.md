## Purpose

Audit trail for task mutations — tracks who created and last updated each task via `created_by` and `updated_by` fields.

## Requirements

### Requirement: Task audit fields
The Task model SHALL include `created_by` (Text, nullable) and `updated_by` (Text, nullable) columns. These fields store the email address of the user who created or last updated the task. An Alembic migration SHALL add these columns to the existing `tasks` table. Existing rows SHALL have `NULL` for both fields.

#### Scenario: Migration adds columns
- **WHEN** the Alembic migration runs
- **THEN** `created_by` and `updated_by` nullable text columns are added to the `tasks` table

#### Scenario: Existing tasks have null audit fields
- **WHEN** the migration runs on a database with existing tasks
- **THEN** all existing tasks have `created_by = NULL` and `updated_by = NULL`

#### Scenario: Migration is reversible
- **WHEN** the Alembic migration is downgraded
- **THEN** the `created_by` and `updated_by` columns are removed

### Requirement: Audit fields populated on task creation via web UI
When a task is created via `POST /api/tasks`, the backend SHALL extract the `email` claim from the authenticated user's JWT and set `created_by` to that email address. If the JWT does not contain an `email` claim, `created_by` SHALL be set to `NULL`.

#### Scenario: Task created by authenticated user
- **WHEN** a user with email "rob@example.com" creates a task via `POST /api/tasks`
- **THEN** the task's `created_by` is "rob@example.com"

#### Scenario: JWT missing email claim
- **WHEN** a user whose JWT lacks an `email` claim creates a task
- **THEN** the task's `created_by` is `NULL`

### Requirement: Audit fields populated on task update via web UI
When a task is updated via `PATCH /api/tasks/{id}`, the backend SHALL set `updated_by` to the authenticated user's email address (from JWT `email` claim).

#### Scenario: Task updated by authenticated user
- **WHEN** a user with email "rob@example.com" updates a task via `PATCH /api/tasks/{id}`
- **THEN** the task's `updated_by` is "rob@example.com"

### Requirement: Audit fields in API responses
The task API responses (`GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks`, `PATCH /api/tasks/{id}`) SHALL include `created_by` and `updated_by` fields. The fields SHALL be nullable strings.

#### Scenario: Task response includes audit fields
- **WHEN** a task with `created_by = "rob@example.com"` is retrieved via `GET /api/tasks/{id}`
- **THEN** the response includes `"created_by": "rob@example.com"` and `"updated_by": null` (if never updated)

#### Scenario: Task list includes audit fields
- **WHEN** tasks are listed via `GET /api/tasks`
- **THEN** each task in the response includes `created_by` and `updated_by` fields

### Requirement: System actions use "system" as actor
When the worker or task runner modifies a task (e.g., setting status to "running" or "completed", writing output), the `updated_by` field SHALL be set to `"system"`.

#### Scenario: Worker updates task status
- **WHEN** the worker sets a task's status to "running"
- **THEN** the task's `updated_by` is "system"

#### Scenario: Worker writes task output
- **WHEN** the worker writes output to a completed task
- **THEN** the task's `updated_by` is "system"
