## ADDED Requirements

### Requirement: Migration adds runner_logs column
An Alembic migration SHALL add a `runner_logs` column to the `tasks` table. The column SHALL be of type `Text`, nullable, with no default value. The migration SHALL be backward-compatible — existing rows receive NULL and existing backend replicas continue to function.

#### Scenario: Migration adds column
- **WHEN** `alembic upgrade head` runs
- **THEN** the `tasks` table gains a `runner_logs` column of type Text, nullable

#### Scenario: Existing tasks unaffected
- **WHEN** the migration runs on a database with existing tasks
- **THEN** all existing task rows have `runner_logs` set to NULL
