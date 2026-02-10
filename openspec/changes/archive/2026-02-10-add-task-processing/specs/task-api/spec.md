## MODIFIED Requirements

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with an `input` field. The backend SHALL count the words in the input. If the input has more than 5 words, it SHALL be stored as the `description` and the backend SHALL call the LLM to generate a short title; if the LLM call fails, the first 5 words plus "..." SHALL be used as the title and a "Needs Info" tag SHALL be applied. If the input has 5 or fewer words, it SHALL be stored as the `title` (with null description) and a "Needs Info" tag SHALL be applied. After successful creation, the backend SHALL publish a `task_created` event to the Valkey pub/sub channel containing the full task object including tags.

#### Scenario: Long input creates task with LLM title
- **WHEN** a client sends `POST /api/tasks` with `{"input": "The login page throws a 500 error when users with special characters try to reset"}`
- **THEN** the backend calls the LLM, stores the LLM response as `title`, stores the input as `description`, and returns HTTP 201 with the created task object including tags

#### Scenario: Short input creates task with title directly
- **WHEN** a client sends `POST /api/tasks` with `{"input": "Fix login bug"}`
- **THEN** the backend stores "Fix login bug" as `title`, sets `description` to null, applies the "Needs Info" tag, and returns HTTP 201

#### Scenario: Event published after creation
- **WHEN** a task is successfully created
- **THEN** the backend publishes a `task_created` event to the Valkey `task_events` channel with the serialized task object including tags

#### Scenario: Missing input
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `input`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

### Requirement: List all tasks
The backend SHALL expose `GET /api/tasks` returning all tasks as a JSON array. Each task object SHALL include `id`, `title`, `description`, `status`, `tags`, `created_at`, and `updated_at` fields.

#### Scenario: Retrieve tasks
- **WHEN** a client sends `GET /api/tasks`
- **THEN** the backend returns HTTP 200 with a JSON array of all tasks ordered by creation time descending, each including tags

#### Scenario: No tasks exist
- **WHEN** a client sends `GET /api/tasks` and no tasks exist
- **THEN** the backend returns HTTP 200 with an empty JSON array

### Requirement: Get a single task
The backend SHALL expose `GET /api/tasks/{id}` returning the task with the given ID, including `description` and `tags` fields.

#### Scenario: Task found
- **WHEN** a client sends `GET /api/tasks/123` and task 123 exists
- **THEN** the backend returns HTTP 200 with the task object including description and tags

#### Scenario: Task not found
- **WHEN** a client sends `GET /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title`, `description`, `status`, and `tags` fields. The endpoint SHALL update only the provided fields and return the updated task object. After successful update, the backend SHALL publish a `task_updated` event to the Valkey pub/sub channel containing the full updated task object including tags.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing status `scheduled`

#### Scenario: Update task description
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"description": "Detailed info about the task"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new description

#### Scenario: Update task tags
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"tags": ["urgent", "bug"]}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new tags

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
The backend SHALL accept only the following status values: `new`, `scheduled`, `pending`, `running`, `review`, `completed`. Any other status value SHALL be rejected with HTTP 422.

#### Scenario: All valid statuses accepted
- **WHEN** a client sends `PATCH /api/tasks/{id}` with each of the six valid statuses
- **THEN** the backend returns HTTP 200 for each request

#### Scenario: Invalid status rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "need-input"}`
- **THEN** the backend returns HTTP 422 with a validation error

### Requirement: Database migration for task description and status changes
An Alembic migration SHALL add a `description` column (nullable text) to the `tasks` table, create the `tags` and `task_tags` tables, and migrate existing tasks with `need-input` status to `new` status with a "Needs Info" tag.

#### Scenario: Migration adds description column
- **WHEN** the migration runs
- **THEN** the `tasks` table gains a `description` column (nullable text)

#### Scenario: Need-input tasks migrated
- **WHEN** the migration runs against a database with tasks in status `need-input`
- **THEN** those tasks are updated to status `new` and tagged with "Needs Info"
