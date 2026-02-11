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
