## ADDED Requirements

### Requirement: List all tasks
The backend SHALL expose `GET /api/tasks` returning all tasks as a JSON array. Each task object SHALL include `id`, `title`, `status`, `created_at`, and `updated_at` fields.

#### Scenario: Retrieve tasks
- **WHEN** a client sends `GET /api/tasks`
- **THEN** the backend returns HTTP 200 with a JSON array of all tasks ordered by creation time descending

#### Scenario: No tasks exist
- **WHEN** a client sends `GET /api/tasks` and no tasks exist
- **THEN** the backend returns HTTP 200 with an empty JSON array

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with a `title` field. The task SHALL be created with status `pending`.

#### Scenario: Successful creation
- **WHEN** a client sends `POST /api/tasks` with `{"title": "Run analysis"}`
- **THEN** the backend returns HTTP 201 with the created task object including a generated `id` and status `pending`

#### Scenario: Missing title
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `title`
- **THEN** the backend returns HTTP 422 with a validation error

### Requirement: Get a single task
The backend SHALL expose `GET /api/tasks/{id}` returning the task with the given ID.

#### Scenario: Task found
- **WHEN** a client sends `GET /api/tasks/123` and task 123 exists
- **THEN** the backend returns HTTP 200 with the task object

#### Scenario: Task not found
- **WHEN** a client sends `GET /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

### Requirement: Queue metrics endpoint for KEDA
The backend SHALL expose `GET /api/metrics/queue` returning a JSON object with `queue_depth` set to the count of tasks with status `pending`.

#### Scenario: Tasks pending
- **WHEN** there are 5 tasks with status `pending`
- **THEN** `GET /api/metrics/queue` returns `{"queue_depth": 5}`

#### Scenario: No tasks pending
- **WHEN** there are no tasks with status `pending`
- **THEN** `GET /api/metrics/queue` returns `{"queue_depth": 0}`

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
