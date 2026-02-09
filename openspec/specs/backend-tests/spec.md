## Requirements

### Requirement: Backend test infrastructure
The backend SHALL have a pytest test suite using `pytest-asyncio` and `httpx.AsyncClient`. Tests SHALL run against an in-memory SQLite database via `aiosqlite`, with FastAPI dependency overrides for database sessions and authentication. The test database SHALL be created fresh for each test function.

#### Scenario: Test suite runs without external services
- **WHEN** a developer runs `pytest` in the backend directory
- **THEN** all tests execute without requiring PostgreSQL, Keycloak, or any external service

#### Scenario: Test isolation
- **WHEN** multiple test functions run sequentially
- **THEN** each test starts with an empty database and no shared state from previous tests

### Requirement: Test task listing
The test suite SHALL verify the `GET /api/tasks` endpoint behavior.

#### Scenario: Retrieve tasks
- **WHEN** tasks exist in the database and an authenticated client sends `GET /api/tasks`
- **THEN** the response is HTTP 200 with a JSON array containing all tasks ordered by creation time descending

#### Scenario: No tasks exist
- **WHEN** no tasks exist and an authenticated client sends `GET /api/tasks`
- **THEN** the response is HTTP 200 with an empty JSON array

### Requirement: Test task creation
The test suite SHALL verify the `POST /api/tasks` endpoint behavior.

#### Scenario: Successful creation
- **WHEN** an authenticated client sends `POST /api/tasks` with `{"title": "Run analysis"}`
- **THEN** the response is HTTP 201 with a task object containing a generated `id`, the title `"Run analysis"`, and status `"new"`

#### Scenario: Missing title
- **WHEN** an authenticated client sends `POST /api/tasks` with an empty or missing `title`
- **THEN** the response is HTTP 422 with a validation error

### Requirement: Test single task retrieval
The test suite SHALL verify the `GET /api/tasks/{id}` endpoint behavior.

#### Scenario: Task found
- **WHEN** an authenticated client sends `GET /api/tasks/{id}` for an existing task
- **THEN** the response is HTTP 200 with the task object

#### Scenario: Task not found
- **WHEN** an authenticated client sends `GET /api/tasks/{id}` for a non-existent task ID
- **THEN** the response is HTTP 404

### Requirement: Test task update
The test suite SHALL verify the `PATCH /api/tasks/{id}` endpoint behavior.

#### Scenario: Update task status
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the response is HTTP 200 with status `"scheduled"` and an updated `updated_at` timestamp

#### Scenario: Update task title
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"title": "New title"}`
- **THEN** the response is HTTP 200 with the new title

#### Scenario: Update both title and status
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"title": "New title", "status": "review"}`
- **THEN** the response is HTTP 200 with both fields updated

#### Scenario: Task not found on update
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` for a non-existent task ID
- **THEN** the response is HTTP 404

#### Scenario: Invalid status value
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"status": "invalid"}`
- **THEN** the response is HTTP 422

#### Scenario: Empty title rejected on update
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"title": ""}`
- **THEN** the response is HTTP 422

### Requirement: Test valid status enforcement
The test suite SHALL verify that all seven valid statuses are accepted and invalid statuses are rejected.

#### Scenario: All valid statuses accepted
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with each of `new`, `need-input`, `scheduled`, `pending`, `running`, `review`, `completed`
- **THEN** the response is HTTP 200 for each request

#### Scenario: Invalid status rejected
- **WHEN** an authenticated client sends `PATCH /api/tasks/{id}` with `{"status": "failed"}`
- **THEN** the response is HTTP 422

### Requirement: Test queue metrics endpoint
The test suite SHALL verify the `GET /metrics/queue` endpoint behavior.

#### Scenario: Tasks pending
- **WHEN** 5 tasks exist with status `pending`
- **THEN** `GET /metrics/queue` returns `{"queue_depth": 5}`

#### Scenario: No tasks pending
- **WHEN** no tasks have status `pending`
- **THEN** `GET /metrics/queue` returns `{"queue_depth": 0}`

#### Scenario: No authentication required for metrics
- **WHEN** a request to `/metrics/queue` has no Authorization header
- **THEN** the endpoint returns the metrics normally without a 401

### Requirement: Test health check endpoint
The test suite SHALL verify the `GET /api/health` endpoint behavior.

#### Scenario: Healthy service
- **WHEN** the backend is running and the database is reachable
- **THEN** `GET /api/health` returns HTTP 200 with `{"status": "ok"}`

### Requirement: Test authentication gating
The test suite SHALL verify that `/api/*` endpoints reject unauthenticated requests.

#### Scenario: Authenticated request succeeds
- **WHEN** a request to `GET /api/tasks` includes a valid auth context (dependency override)
- **THEN** the endpoint processes the request normally

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to `POST /api/tasks` is sent without the auth dependency override
- **THEN** the endpoint returns HTTP 401 or HTTP 403

### Requirement: Backend test script
The backend SHALL have a test script runnable via `pytest` from the `backend/` directory. Dev dependencies (`pytest`, `pytest-asyncio`, `httpx`, `aiosqlite`) SHALL be listed in a separate requirements file.

#### Scenario: Run backend tests
- **WHEN** a developer runs `pip install -r requirements-test.txt && pytest` in the backend directory
- **THEN** all backend tests execute and report results
