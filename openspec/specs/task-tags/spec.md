## Requirements

### Requirement: Tags database table
The backend SHALL have a `tags` table with columns: `id` (UUID, primary key, auto-generated) and `name` (text, unique, not null). An Alembic migration SHALL create this table.

#### Scenario: Migration creates tags table
- **WHEN** the Alembic migration runs
- **THEN** a `tags` table is created with columns `id` (UUID PK) and `name` (unique text)

### Requirement: Task-tags join table
The backend SHALL have a `task_tags` table with columns: `task_id` (UUID, FK to `tasks.id`) and `tag_id` (UUID, FK to `tags.id`), forming a composite primary key. Deleting a task SHALL cascade-delete its `task_tags` rows.

#### Scenario: Migration creates task_tags table
- **WHEN** the Alembic migration runs
- **THEN** a `task_tags` table is created with foreign keys to `tasks` and `tags` and a composite primary key

#### Scenario: Deleting a task removes its tag associations
- **WHEN** a task with tags is deleted
- **THEN** the corresponding `task_tags` rows are removed but the `tags` rows remain

### Requirement: Tag autocomplete endpoint
The backend SHALL expose `GET /api/tags` accepting an optional query parameter `q`. When `q` is provided, the endpoint SHALL return tags whose names match the prefix (case-insensitive), limited to 10 results, ordered alphabetically. When `q` is omitted, the endpoint SHALL return all tags (limited to 10, ordered alphabetically).

#### Scenario: Search tags by prefix
- **WHEN** a client sends `GET /api/tags?q=bug`
- **THEN** the backend returns HTTP 200 with a JSON array of tag objects whose names start with "bug" (case-insensitive), limited to 10

#### Scenario: No matching tags
- **WHEN** a client sends `GET /api/tags?q=xyz` and no tags match
- **THEN** the backend returns HTTP 200 with an empty JSON array

#### Scenario: No query parameter
- **WHEN** a client sends `GET /api/tags` without a `q` parameter
- **THEN** the backend returns HTTP 200 with up to 10 tags ordered alphabetically

### Requirement: Tags included in task responses
All task API responses SHALL include a `tags` field containing an array of tag name strings associated with the task. This applies to `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks`, and `PATCH /api/tasks/{id}`.

#### Scenario: Task with tags
- **WHEN** a task has tags "urgent" and "bug"
- **THEN** the task response includes `"tags": ["bug", "urgent"]` (alphabetically sorted)

#### Scenario: Task with no tags
- **WHEN** a task has no tags
- **THEN** the task response includes `"tags": []`

### Requirement: Update task tags via PATCH
The `PATCH /api/tasks/{id}` endpoint SHALL accept an optional `tags` field containing an array of tag name strings. When provided, the endpoint SHALL replace all existing tags for the task with the specified tags. Tag names that do not exist in the `tags` table SHALL be created automatically.

#### Scenario: Set tags on a task
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"tags": ["urgent", "bug"]}`
- **THEN** the task's tags are set to "urgent" and "bug", creating any tags that don't exist

#### Scenario: Remove all tags
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"tags": []}`
- **THEN** all tags are removed from the task

#### Scenario: Tags field omitted
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title"}` (no tags field)
- **THEN** the task's existing tags are unchanged
