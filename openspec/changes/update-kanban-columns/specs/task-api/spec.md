## MODIFIED Requirements

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with a `title` field. The task SHALL be created with status `new`.

#### Scenario: Successful creation
- **WHEN** a client sends `POST /api/tasks` with `{"title": "Run analysis"}`
- **THEN** the backend returns HTTP 201 with the created task object including a generated `id` and status `new`

#### Scenario: Missing title
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `title`
- **THEN** the backend returns HTTP 422 with a validation error

## ADDED Requirements

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title` and `status` fields. The endpoint SHALL update only the provided fields and return the updated task object.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing status `scheduled` and an updated `updated_at` timestamp

#### Scenario: Update task title
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new title

#### Scenario: Update both title and status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title", "status": "review"}`
- **THEN** the backend returns HTTP 200 with the updated task object reflecting both changes

#### Scenario: Task not found
- **WHEN** a client sends `PATCH /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

#### Scenario: Invalid status value
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid statuses

#### Scenario: Empty title rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": ""}`
- **THEN** the backend returns HTTP 422 with a validation error

### Requirement: Valid task statuses
The backend SHALL accept only the following status values: `new`, `need-input`, `scheduled`, `pending`, `running`, `review`, `completed`. Any other status value SHALL be rejected with HTTP 422.

#### Scenario: All valid statuses accepted
- **WHEN** a client sends `PATCH /api/tasks/{id}` with each of the seven valid statuses
- **THEN** the backend returns HTTP 200 for each request

#### Scenario: Invalid status rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "failed"}`
- **THEN** the backend returns HTTP 422 with a validation error

### Requirement: Database migration for new statuses
An Alembic migration SHALL update existing task status values to the new set.

#### Scenario: Existing statuses migrated
- **WHEN** the migration runs against a database with tasks in statuses `pending`, `running`, `completed`, and `failed`
- **THEN** tasks with status `failed` are updated to `new`; tasks with `pending`, `running`, and `completed` statuses remain unchanged
