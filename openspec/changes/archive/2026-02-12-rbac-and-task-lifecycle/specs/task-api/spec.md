## MODIFIED Requirements

### Requirement: Editor role required for write operations

The backend SHALL provide a `require_editor` FastAPI dependency that validates the current user has either the `editor` or `admin` role. The dependency SHALL reuse `get_current_user` logic to obtain and decode the JWT, extract roles, and check that at least one of `editor` or `admin` is present. If neither role is present, it SHALL return HTTP 403 with `{"detail": "Editor role required"}`.

The `require_editor` dependency SHALL be applied to:
- `POST /api/tasks` (create task)
- `PATCH /api/tasks/{id}` (update task)
- `DELETE /api/tasks/{id}` (soft delete task)

The `GET /api/tasks` and `GET /api/tasks/{id}` endpoints SHALL continue to use `get_current_user` (any authenticated user).

#### Scenario: Editor creates a task
- **WHEN** a user with the `editor` role sends `POST /api/tasks`
- **THEN** the request succeeds and the task is created

#### Scenario: Admin creates a task
- **WHEN** a user with the `admin` role sends `POST /api/tasks`
- **THEN** the request succeeds (admin is a superset of editor)

#### Scenario: Viewer creates a task
- **WHEN** a user with only the `viewer` role sends `POST /api/tasks`
- **THEN** the backend returns HTTP 403 with `{"detail": "Editor role required"}`

#### Scenario: Viewer reads tasks
- **WHEN** a user with only the `viewer` role sends `GET /api/tasks`
- **THEN** the request succeeds and tasks are returned

### Requirement: Soft delete via status change

_(Replaces existing delete behaviour)_

The `DELETE /api/tasks/{id}` endpoint SHALL set the task's `status` to `"deleted"` instead of removing the row from the database. The endpoint SHALL NOT delete the task's tag associations from `task_tags`. The endpoint SHALL still return HTTP 204 and emit a `task_deleted` WebSocket event. The endpoint SHALL require the `editor` or `admin` role.

#### Scenario: Delete moves task to deleted status
- **WHEN** an editor sends `DELETE /api/tasks/{id}` for a task in "new" status
- **THEN** the task's status is set to "deleted", the row and all associations persist in the database, and the endpoint returns HTTP 204

#### Scenario: Delete emits WebSocket event
- **WHEN** a task is soft-deleted via `DELETE /api/tasks/{id}`
- **THEN** a `task_deleted` WebSocket event is emitted with the task ID

#### Scenario: Deleted task data persists
- **WHEN** a task has been soft-deleted
- **THEN** the task row, its tag associations, output, runner_logs, and all metadata remain in the database

### Requirement: Task list excludes hidden statuses

The `GET /api/tasks` endpoint SHALL exclude tasks with `status` of `"deleted"` or `"archived"`. Only tasks in active workflow states (new, scheduled, pending, running, review, completed) SHALL be returned.

#### Scenario: Deleted task not in list
- **WHEN** a task has `status = "deleted"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Archived task not in list
- **WHEN** a task has `status = "archived"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Active tasks still returned
- **WHEN** tasks exist in new, scheduled, pending, running, review, and completed statuses
- **THEN** all are returned by `GET /api/tasks`

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
- **WHEN** an editor sends `PATCH /api/tasks/{id}` for a task with `status = "new"`
- **THEN** the request proceeds normally

### Requirement: VALID_STATUSES includes hidden states

The `VALID_STATUSES` constant SHALL include `"deleted"` and `"archived"` in addition to the existing active statuses. The PATCH endpoint's status validation SHALL accept these values. However, setting a task to `"deleted"` via PATCH is not the intended workflow — soft delete is via the DELETE endpoint.

#### Scenario: Archived status accepted in validation
- **WHEN** the PATCH endpoint validates a status value of `"archived"`
- **THEN** the validation passes (the status is in VALID_STATUSES)
