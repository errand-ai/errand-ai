## MODIFIED Requirements

### Requirement: List all tasks
The backend SHALL expose `GET /api/tasks` returning all tasks as a JSON array. Each task object SHALL include `id`, `title`, `description`, `status`, `position`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `tags`, `output`, `created_at`, and `updated_at` fields. Tasks SHALL be ordered by `position` ascending, with ties broken by `created_at` ascending.

#### Scenario: Retrieve tasks
- **WHEN** a client sends `GET /api/tasks`
- **THEN** the backend returns HTTP 200 with a JSON array of all tasks ordered by position ascending then created_at ascending, each including position, tags, category, execute_at, repeat_interval, repeat_until, and output

#### Scenario: No tasks exist
- **WHEN** a client sends `GET /api/tasks` and no tasks exist
- **THEN** the backend returns HTTP 200 with an empty JSON array

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title`, `description`, `status`, `position`, `tags`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, and `output` fields. The endpoint SHALL update only the provided fields and return the updated task object. When `status` is changed, the task SHALL be assigned a new position at the bottom of the target column. When `position` is provided (without a status change), the backend SHALL reorder tasks within the same status column: all tasks in that status with position >= the new value SHALL have their position incremented by 1, and the task SHALL be set to the new position. After successful update, the backend SHALL publish a `task_updated` event to the Valkey pub/sub channel containing the full updated task object including tags, categorisation fields, position, and output.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend assigns a new position at the bottom of the Scheduled column and returns HTTP 200 with the updated task object showing status `scheduled` and the new position

#### Scenario: Reorder task within column
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"position": 2}` and the task is currently at position 5 in the New column
- **THEN** the backend shifts tasks in the New column with position >= 2 up by 1, sets the task's position to 2, and returns HTTP 200 with the updated task object

#### Scenario: Update task description
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"description": "Detailed info about the task"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new description

#### Scenario: Update task tags
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"tags": ["urgent", "bug"]}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new tags

#### Scenario: Update task category
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"category": "scheduled", "execute_at": "2026-02-15T17:00:00Z"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new category and execute_at

#### Scenario: Update task repeat_interval
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"repeat_interval": "1d"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new repeat_interval

#### Scenario: Update task repeat_until
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"repeat_until": "2026-03-01T00:00:00Z"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new repeat_until

#### Scenario: Update task output
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"output": "Task completed successfully"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new output

#### Scenario: Task not found
- **WHEN** a client sends `PATCH /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404 and no event is published

#### Scenario: Invalid status value
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid statuses and no event is published

#### Scenario: Empty title rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": ""}`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

#### Scenario: Invalid category value
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"category": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid categories and no event is published

## ADDED Requirements

### Requirement: Task output field
The task model SHALL include an `output` field (nullable text) for storing the captured stdout/stderr from task execution. The field SHALL be included in all task API responses. The field SHALL be nullable and default to null for new tasks.

#### Scenario: New task has null output
- **WHEN** a task is created via `POST /api/tasks`
- **THEN** the task's `output` field is null in the response

#### Scenario: Task with output
- **WHEN** a task has been executed and output was captured
- **THEN** the task's `output` field contains the captured text in API responses
