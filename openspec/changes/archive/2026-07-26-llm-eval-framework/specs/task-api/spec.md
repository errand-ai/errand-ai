## ADDED Requirements

### Requirement: Task model includes is_eval flag
The Task model SHALL include an `is_eval` boolean column (NOT NULL, default false). At task creation, the server SHALL set `is_eval=true` when the task's resolved profile name starts with `eval--`. Clients SHALL NOT set `is_eval` directly. The field SHALL be included in task API responses.

#### Scenario: Eval task flagged at creation
- **WHEN** a task is created via `new_task` with profile `eval--job-research--gemma4`
- **THEN** the stored task has `is_eval=true`

#### Scenario: Production task unflagged
- **WHEN** a task is created with profile `job-research` or no profile
- **THEN** the stored task has `is_eval=false`

#### Scenario: Flag survives profile deletion
- **WHEN** an eval task's profile is later deleted (`profile_id` set null)
- **THEN** the task still has `is_eval=true`

### Requirement: Task list endpoints exclude eval tasks by default
`GET /api/tasks` and `GET /api/tasks/archived` SHALL exclude tasks with `is_eval=true` unless the query parameter `include_evals=true` is provided.

#### Scenario: Board never shows eval tasks
- **WHEN** the kanban frontend fetches `GET /api/tasks` while an eval run is in progress
- **THEN** no eval tasks appear in the response

#### Scenario: Eval tasks visible on request
- **WHEN** `GET /api/tasks/archived?include_evals=true` is called
- **THEN** archived eval tasks are included in the response
