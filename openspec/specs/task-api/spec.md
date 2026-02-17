## ADDED Requirements

### Requirement: Task runner_logs field
The task model SHALL include a `runner_logs` field (nullable text) for storing the captured stderr output from task runner execution. The field SHALL be included in all task API responses (`GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks`, `PATCH /api/tasks/{id}`). The field SHALL be nullable and default to null for new tasks. The field SHALL NOT be writable via the PATCH endpoint — it is set exclusively by the worker.

#### Scenario: New task has null runner_logs
- **WHEN** a task is created via `POST /api/tasks`
- **THEN** the task's `runner_logs` field is null in the response

#### Scenario: Processed task includes runner_logs
- **WHEN** a task has been executed by the worker and stderr was captured
- **THEN** the task's `runner_logs` field contains the captured stderr text in API responses

#### Scenario: runner_logs not writable via PATCH
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"runner_logs": "injected logs"}`
- **THEN** the backend ignores the `runner_logs` field and does not update it

### Requirement: Editor role required for write operations

The backend SHALL provide a `require_editor` FastAPI dependency that validates the current user has either the `editor` or `admin` role. The dependency SHALL reuse `get_current_user` logic to obtain and decode the JWT, extract roles, and check that at least one of `editor` or `admin` is present. If neither role is present, it SHALL return HTTP 403 with `{"detail": "Editor role required"}`.

The `require_editor` dependency SHALL be applied to:
- `POST /api/tasks` (create task)
- `PATCH /api/tasks/{id}` (update task)
- `DELETE /api/tasks/{id}` (soft delete task)

The `GET /api/tasks` and `GET /api/tasks/{id}` endpoints SHALL continue to use `get_current_user` (any authenticated user).

The `POST /api/tasks` endpoint SHALL extract the `email` claim from the JWT and set `created_by` on the new task. The `PATCH /api/tasks/{id}` endpoint SHALL extract the `email` claim from the JWT and set `updated_by` on the task.

#### Scenario: Editor creates a task with audit trail
- **WHEN** a user with email "rob@example.com" and the `editor` role sends `POST /api/tasks`
- **THEN** the request succeeds, the task is created, and `created_by` is "rob@example.com"

#### Scenario: Admin creates a task with audit trail
- **WHEN** a user with email "admin@example.com" and the `admin` role sends `POST /api/tasks`
- **THEN** the request succeeds and `created_by` is "admin@example.com"

#### Scenario: Viewer creates a task
- **WHEN** a user with only the `viewer` role sends `POST /api/tasks`
- **THEN** the backend returns HTTP 403 with `{"detail": "Editor role required"}`

#### Scenario: Editor updates a task with audit trail
- **WHEN** a user with email "rob@example.com" sends `PATCH /api/tasks/{id}`
- **THEN** the request succeeds and `updated_by` is set to "rob@example.com"

#### Scenario: Viewer reads tasks
- **WHEN** a user with only the `viewer` role sends `GET /api/tasks`
- **THEN** the request succeeds and tasks are returned with `created_by` and `updated_by` fields

### Requirement: Soft delete via status change

The `DELETE /api/tasks/{id}` endpoint SHALL set the task's `status` to `"deleted"` instead of removing the row from the database. The endpoint SHALL NOT delete the task's tag associations from `task_tags`. The endpoint SHALL still return HTTP 204 and emit a `task_deleted` WebSocket event. The endpoint SHALL require the `editor` or `admin` role.

#### Scenario: Delete moves task to deleted status
- **WHEN** an editor sends `DELETE /api/tasks/{id}` for a task in "review" status
- **THEN** the task's status is set to "deleted", the row and all associations persist in the database, and the endpoint returns HTTP 204

#### Scenario: Delete emits WebSocket event
- **WHEN** a task is soft-deleted via `DELETE /api/tasks/{id}`
- **THEN** a `task_deleted` WebSocket event is emitted with the task ID

#### Scenario: Deleted task data persists
- **WHEN** a task has been soft-deleted
- **THEN** the task row, its tag associations, output, runner_logs, and all metadata remain in the database

### Requirement: Task list excludes hidden statuses

The `GET /api/tasks` endpoint SHALL exclude tasks with `status` of `"deleted"` or `"archived"`. Only tasks in active workflow states (scheduled, pending, running, review, completed) SHALL be returned.

#### Scenario: Deleted task not in list
- **WHEN** a task has `status = "deleted"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Archived task not in list
- **WHEN** a task has `status = "archived"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Active tasks still returned
- **WHEN** tasks exist in scheduled, pending, running, review, and completed statuses
- **THEN** all are returned by `GET /api/tasks`

#### Scenario: Task with status new not returned
- **WHEN** a legacy task somehow has `status = "new"` in the database
- **THEN** it does not appear in `GET /api/tasks` results (not in active workflow states)

### Requirement: Archived tasks endpoint

The backend SHALL expose `GET /api/tasks/archived` requiring any authenticated user. The endpoint SHALL return tasks with hidden statuses, ordered by `updated_at` descending (most recent first). For users with the `admin` role, the endpoint SHALL return tasks with `status IN ('deleted', 'archived')`. For non-admin users, the endpoint SHALL return only tasks with `status = 'archived'`.

#### Scenario: Admin sees deleted and archived tasks
- **WHEN** an admin sends `GET /api/tasks/archived`
- **THEN** the response includes both deleted and archived tasks, ordered by `updated_at` descending

#### Scenario: Editor sees only archived tasks
- **WHEN** an editor sends `GET /api/tasks/archived`
- **THEN** the response includes only archived tasks (not deleted), ordered by `updated_at` descending

#### Scenario: Viewer sees only archived tasks
- **WHEN** a viewer sends `GET /api/tasks/archived`
- **THEN** the response includes only archived tasks (not deleted), ordered by `updated_at` descending

#### Scenario: No archived tasks
- **WHEN** no tasks have hidden statuses
- **THEN** the endpoint returns an empty array

### Requirement: Running task PATCH guard

The `PATCH /api/tasks/{id}` endpoint SHALL return HTTP 409 Conflict with `{"detail": "Cannot edit a running task"}` if the task's current status is `"running"`. This prevents manual editing of tasks being processed by the worker. The guard SHALL be checked before applying any field updates.

#### Scenario: PATCH on running task rejected
- **WHEN** an editor sends `PATCH /api/tasks/{id}` for a task with `status = "running"`
- **THEN** the backend returns HTTP 409 with `{"detail": "Cannot edit a running task"}`

#### Scenario: PATCH on non-running task allowed
- **WHEN** an editor sends `PATCH /api/tasks/{id}` for a task with `status = "review"`
- **THEN** the request proceeds normally

### Requirement: VALID_STATUSES includes hidden states

The `VALID_STATUSES` constant SHALL include `"scheduled"`, `"pending"`, `"running"`, `"review"`, `"completed"`, `"deleted"`, and `"archived"`. The status `"new"` SHALL NOT be included. The PATCH endpoint's status validation SHALL accept these values. However, setting a task to `"deleted"` via PATCH is not the intended workflow — soft delete is via the DELETE endpoint.

#### Scenario: Review status accepted in validation
- **WHEN** the PATCH endpoint validates a status value of `"review"`
- **THEN** the validation passes (the status is in VALID_STATUSES)

#### Scenario: New status rejected in validation
- **WHEN** the PATCH endpoint validates a status value of `"new"`
- **THEN** the validation fails with HTTP 422

#### Scenario: Archived status accepted in validation
- **WHEN** the PATCH endpoint validates a status value of `"archived"`
- **THEN** the validation passes (the status is in VALID_STATUSES)

### Requirement: Migration to move existing new tasks to review

An Alembic migration SHALL update all tasks with `status = 'new'` to `status = 'review'`. The migration SHALL be reversible (downgrade sets `status = 'new'` where `status = 'review'` and the task was migrated).

#### Scenario: Migration updates new tasks
- **WHEN** the migration runs against a database containing tasks with `status = 'new'`
- **THEN** those tasks are updated to `status = 'review'`

#### Scenario: Migration is idempotent
- **WHEN** the migration runs against a database with no tasks in `status = 'new'`
- **THEN** no rows are affected and the migration succeeds
