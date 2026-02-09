## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: All /api/* endpoints require authentication
All endpoints under `/api/*` (except `/api/health`) SHALL require a valid Bearer token in the Authorization header. Requests without a valid token SHALL receive HTTP 401.

#### Scenario: Authenticated request succeeds
- **WHEN** a request to `GET /api/tasks` includes a valid Bearer token
- **THEN** the endpoint processes the request normally

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to `POST /api/tasks` has no Authorization header
- **THEN** the endpoint returns HTTP 401
