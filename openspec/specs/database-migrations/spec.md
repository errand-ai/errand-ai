## ADDED Requirements

### Requirement: Migrations managed by Alembic
The application SHALL use Alembic to manage PostgreSQL schema migrations. Migration scripts SHALL be stored in the backend source tree.

#### Scenario: Initial migration creates tasks table
- **WHEN** `alembic upgrade head` runs against an empty database
- **THEN** the `tasks` table is created with columns: `id` (UUID primary key), `title` (text, not null), `status` (text, not null, default `pending`), `created_at` (timestamp with timezone), `updated_at` (timestamp with timezone)

### Requirement: Migrations run as a Kubernetes Job
Migrations SHALL execute as a Helm pre-upgrade hook Job using the backend Docker image with `alembic upgrade head` as the entrypoint. The Job MUST complete successfully before backend and worker pods start.

#### Scenario: Successful migration before deployment
- **WHEN** a Helm upgrade is performed
- **THEN** the migration Job runs and completes before new backend/worker pods are created

#### Scenario: Migration failure blocks deployment
- **WHEN** the migration Job fails
- **THEN** the Helm upgrade is blocked and no new pods are created

### Requirement: Migrations are backward-compatible
All migrations SHALL be additive (new tables, new columns with defaults, new indexes). Destructive changes (drop column, rename column) MUST NOT be performed without a multi-phase migration plan.

#### Scenario: Additive migration
- **WHEN** a migration adds a new column with a default value
- **THEN** existing backend replicas running the previous version continue to function

### Requirement: Database connection via environment variable
The database connection string SHALL be read from the `DATABASE_URL` environment variable. Alembic, the backend, and the worker MUST all use this same variable.

#### Scenario: Connection configuration
- **WHEN** `DATABASE_URL` is set to a PostgreSQL connection string
- **THEN** Alembic, backend, and worker all connect to that database
