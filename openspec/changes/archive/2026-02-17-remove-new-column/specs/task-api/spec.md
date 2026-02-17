## MODIFIED Requirements

### Requirement: VALID_STATUSES includes hidden states

The `VALID_STATUSES` constant SHALL include `"scheduled"`, `"pending"`, `"running"`, `"review"`, `"completed"`, `"deleted"`, and `"archived"`. The status `"new"` SHALL NOT be included. The PATCH endpoint's status validation SHALL accept these values.

#### Scenario: Review status accepted in validation

- **WHEN** the PATCH endpoint validates a status value of `"review"`
- **THEN** the validation passes (the status is in VALID_STATUSES)

#### Scenario: New status rejected in validation

- **WHEN** the PATCH endpoint validates a status value of `"new"`
- **THEN** the validation fails with HTTP 422

#### Scenario: Archived status accepted in validation

- **WHEN** the PATCH endpoint validates a status value of `"archived"`
- **THEN** the validation passes (the status is in VALID_STATUSES)

### Requirement: Task list excludes hidden statuses

The `GET /api/tasks` endpoint SHALL exclude tasks with `status` of `"deleted"` or `"archived"`. Only tasks in active workflow states (scheduled, pending, running, review, completed) SHALL be returned.

#### Scenario: Deleted task not in list

- **WHEN** a task has `status = "deleted"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Archived task not in list

- **WHEN** a task has `status = "archived"`
- **THEN** it does not appear in `GET /api/tasks` results

#### Scenario: Active tasks still returned

- **WHEN** tasks exist in scheduled, pending, running, review, and completed statuses
- **THEN** all are returned by `GET /api/tasks`

#### Scenario: Task with status new not returned

- **WHEN** a legacy task somehow has `status = "new"` in the database
- **THEN** it does not appear in `GET /api/tasks` results (not in active workflow states)

## ADDED Requirements

### Requirement: Migration to move existing new tasks to review

An Alembic migration SHALL update all tasks with `status = 'new'` to `status = 'review'`. The migration SHALL be reversible (downgrade sets `status = 'new'` where `status = 'review'` and the task was migrated).

#### Scenario: Migration updates new tasks

- **WHEN** the migration runs against a database containing tasks with `status = 'new'`
- **THEN** those tasks are updated to `status = 'review'`

#### Scenario: Migration is idempotent

- **WHEN** the migration runs against a database with no tasks in `status = 'new'`
- **THEN** no rows are affected and the migration succeeds
