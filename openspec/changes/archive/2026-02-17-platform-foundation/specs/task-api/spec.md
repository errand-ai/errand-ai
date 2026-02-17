## MODIFIED Requirements

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
