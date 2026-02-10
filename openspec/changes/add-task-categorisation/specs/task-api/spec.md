## MODIFIED Requirements

### Requirement: List all tasks
The backend SHALL expose `GET /api/tasks` returning all tasks as a JSON array. Each task object SHALL include `id`, `title`, `description`, `status`, `category`, `execute_at`, `repeat_interval`, `repeat_until`, `tags`, `created_at`, and `updated_at` fields.

#### Scenario: Retrieve tasks
- **WHEN** a client sends `GET /api/tasks`
- **THEN** the backend returns HTTP 200 with a JSON array of all tasks ordered by creation time descending, each including tags, category, execute_at, repeat_interval, and repeat_until

#### Scenario: No tasks exist
- **WHEN** a client sends `GET /api/tasks` and no tasks exist
- **THEN** the backend returns HTTP 200 with an empty JSON array

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with an `input` field. The backend SHALL count the words in the input. If the input has more than 5 words, it SHALL be stored as the `description` and the backend SHALL call the LLM to generate a short title, categorise the task, and extract timing information; if the LLM call fails, the first 5 words plus "..." SHALL be used as the title, category SHALL default to `immediate`, and a "Needs Info" tag SHALL be applied. If the input has 5 or fewer words, it SHALL be stored as the `title` (with null description) and a "Needs Info" tag SHALL be applied. After categorisation, the backend SHALL auto-route the task based on its category and tags. After successful creation, the backend SHALL publish a `task_created` event to the Valkey pub/sub channel containing the full task object including tags and categorisation fields.

#### Scenario: Long input creates task with LLM title and categorisation
- **WHEN** a client sends `POST /api/tasks` with `{"input": "The login page throws a 500 error when users with special characters try to reset"}`
- **THEN** the backend calls the LLM, stores the LLM-generated title, category, execute_at, and repeat_interval, auto-routes based on category, and returns HTTP 201 with the created task object

#### Scenario: Short input creates task with title directly
- **WHEN** a client sends `POST /api/tasks` with `{"input": "Fix login bug"}`
- **THEN** the backend stores "Fix login bug" as `title`, sets `description` to null, sets category to `immediate`, applies the "Needs Info" tag, keeps status as `new`, and returns HTTP 201

#### Scenario: Event published after creation
- **WHEN** a task is successfully created
- **THEN** the backend publishes a `task_created` event to the Valkey `task_events` channel with the serialized task object including tags and categorisation fields

#### Scenario: Missing input
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `input`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

### Requirement: Get a single task
The backend SHALL expose `GET /api/tasks/{id}` returning the task with the given ID, including `description`, `tags`, `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields.

#### Scenario: Task found
- **WHEN** a client sends `GET /api/tasks/123` and task 123 exists
- **THEN** the backend returns HTTP 200 with the task object including description, tags, category, execute_at, repeat_interval, and repeat_until

#### Scenario: Task not found
- **WHEN** a client sends `GET /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title`, `description`, `status`, `tags`, `category`, `execute_at`, `repeat_interval`, and `repeat_until` fields. The endpoint SHALL update only the provided fields and return the updated task object. If the update triggers auto-promotion (see task-categorisation spec), the status and tags SHALL be adjusted accordingly. After successful update, the backend SHALL publish a `task_updated` event to the Valkey pub/sub channel containing the full updated task object including tags and categorisation fields.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing status `scheduled`

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

### Requirement: Delete a task
The backend SHALL expose `DELETE /api/tasks/{id}` requiring authentication. The endpoint SHALL delete the task and its tag associations, publish a `task_deleted` event to the Valkey pub/sub channel, and return HTTP 204 with no body.

#### Scenario: Successful deletion
- **WHEN** a client sends `DELETE /api/tasks/{id}` and the task exists
- **THEN** the backend deletes the task and its tag associations, publishes a `task_deleted` event to Valkey, and returns HTTP 204

#### Scenario: Task not found
- **WHEN** a client sends `DELETE /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

#### Scenario: Event published after deletion
- **WHEN** a task is successfully deleted
- **THEN** the backend publishes a `task_deleted` event to the Valkey `task_events` channel with `{"event": "task_deleted", "task": {"id": "<task-id>"}}`

#### Scenario: Unauthenticated request
- **WHEN** a client sends `DELETE /api/tasks/{id}` without a valid Bearer token
- **THEN** the backend returns HTTP 401
