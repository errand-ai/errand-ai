## Requirements

### Requirement: List all tasks
The backend SHALL expose `GET /api/tasks` returning all tasks as a JSON array. Each task object SHALL include `id`, `title`, `status`, `created_at`, and `updated_at` fields.

#### Scenario: Retrieve tasks
- **WHEN** a client sends `GET /api/tasks`
- **THEN** the backend returns HTTP 200 with a JSON array of all tasks ordered by creation time descending

#### Scenario: No tasks exist
- **WHEN** a client sends `GET /api/tasks` and no tasks exist
- **THEN** the backend returns HTTP 200 with an empty JSON array

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with a `title` field. The task SHALL be created with status `new`. After successful creation, the backend SHALL publish a `task_created` event to the Valkey pub/sub channel containing the full task object.

#### Scenario: Successful creation
- **WHEN** a client sends `POST /api/tasks` with `{"title": "Run analysis"}`
- **THEN** the backend returns HTTP 201 with the created task object including a generated `id` and status `new`

#### Scenario: Event published after creation
- **WHEN** a task is successfully created
- **THEN** the backend publishes a `task_created` event to the Valkey `task_events` channel with the serialized task object

#### Scenario: Missing title
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `title`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

### Requirement: Get a single task
The backend SHALL expose `GET /api/tasks/{id}` returning the task with the given ID.

#### Scenario: Task found
- **WHEN** a client sends `GET /api/tasks/123` and task 123 exists
- **THEN** the backend returns HTTP 200 with the task object

#### Scenario: Task not found
- **WHEN** a client sends `GET /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title` and `status` fields. The endpoint SHALL update only the provided fields and return the updated task object. After successful update, the backend SHALL publish a `task_updated` event to the Valkey pub/sub channel containing the full updated task object.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing status `scheduled` and an updated `updated_at` timestamp

#### Scenario: Event published after update
- **WHEN** a task is successfully updated
- **THEN** the backend publishes a `task_updated` event to the Valkey `task_events` channel with the serialized updated task object

#### Scenario: Update task title
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new title

#### Scenario: Update both title and status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title", "status": "review"}`
- **THEN** the backend returns HTTP 200 with the updated task object reflecting both changes

#### Scenario: Task not found
- **WHEN** a client sends `PATCH /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404 and no event is published

#### Scenario: Invalid status value
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid statuses and no event is published

#### Scenario: Empty title rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": ""}`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

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

### Requirement: Queue metrics endpoint for KEDA
The backend SHALL expose `GET /metrics/queue` returning a JSON object with `queue_depth` set to the count of tasks with status `pending`. This endpoint SHALL NOT require authentication and SHALL NOT be prefixed with `/api`.

#### Scenario: Tasks pending
- **WHEN** there are 5 tasks with status `pending`
- **THEN** `GET /metrics/queue` returns `{"queue_depth": 5}`

#### Scenario: No tasks pending
- **WHEN** there are no tasks with status `pending`
- **THEN** `GET /metrics/queue` returns `{"queue_depth": 0}`

#### Scenario: No authentication required
- **WHEN** a request to `/metrics/queue` has no Authorization header
- **THEN** the endpoint returns the metrics normally

### Requirement: Health check endpoint
The backend SHALL expose `GET /api/health` returning HTTP 200 with `{"status": "ok"}` when the service is running and can connect to the database.

#### Scenario: Healthy service
- **WHEN** the backend is running and the database is reachable
- **THEN** `GET /api/health` returns HTTP 200 with `{"status": "ok"}`

#### Scenario: Database unreachable
- **WHEN** the backend cannot connect to the database
- **THEN** `GET /api/health` returns HTTP 503

### Requirement: Backend is stateless
The backend SHALL store all state in PostgreSQL. No in-memory state SHALL be shared between requests. Multiple backend replicas MUST be able to serve requests concurrently without coordination.

#### Scenario: Multiple replicas serve requests
- **WHEN** two backend replicas are running
- **THEN** both can serve `GET /api/tasks` and return identical results

### Requirement: All /api/* endpoints require authentication
All endpoints under `/api/*` (except `/api/health`) SHALL require a valid Bearer token in the Authorization header. Requests without a valid token SHALL receive HTTP 401.

#### Scenario: Authenticated request succeeds
- **WHEN** a request to `GET /api/tasks` includes a valid Bearer token
- **THEN** the endpoint processes the request normally

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to `POST /api/tasks` has no Authorization header
- **THEN** the endpoint returns HTTP 401
