## ADDED Requirements

### Requirement: Task record includes peak context usage

The `tasks` table SHALL carry the peak `input_tokens` observed for a task and the `max_context_tokens` ceiling in force while it ran. Both SHALL be nullable: rows predating the measurement SHALL remain NULL rather than be backfilled with a fabricated value.

The peak SHALL be derived from the `llm_turn_end` events the server already parses, and written on task completion rather than per turn.

The ceiling SHALL be stored alongside the peak because it is configurable. A peak without the ceiling it was measured against cannot be interpreted once the setting changes.

Both fields SHALL be included in `TaskResponse`, so the ratio is computable by any consumer without a log query.

#### Scenario: Peak recorded on completion

- **WHEN** a task completes having reported turn usage with a maximum `input_tokens` of 126,149 under a 150,000 ceiling
- **THEN** the task record carries a peak of 126,149 and a ceiling of 150,000

#### Scenario: Task with no reported usage

- **WHEN** a task completes without any turn reporting usage
- **THEN** both fields remain NULL
- **THEN** the fields are not recorded as zero, since no measurement was taken

#### Scenario: Pre-existing rows are not backfilled

- **WHEN** the migration is applied to a database containing tasks that ran before the measurement existed
- **THEN** those rows have NULL in both fields

#### Scenario: Fields exposed in the API

- **WHEN** a client requests `GET /api/tasks/{id}` for a task with a recorded peak
- **THEN** the response includes both the peak and the ceiling
